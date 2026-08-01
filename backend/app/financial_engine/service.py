from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.financial_engine.engine import ENGINE_VERSION, calculate_financials
from app.models import (
    CalculatedMetric,
    CalculationVersion,
    FinancialPeriod,
    ForecastResult,
    MetricEvidence,
    Upload,
    ValidationResult,
    utcnow,
)


def _fingerprint(upload: Upload) -> str:
    payload = json.dumps(
        {"checksum": upload.checksum, "engine_version": ENGINE_VERSION},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def calculate_upload(db: Session, *, user_id: int, upload_id: int) -> CalculationVersion:
    upload = db.scalar(select(Upload).where(Upload.id == upload_id, Upload.user_id == user_id))
    if upload is None:
        raise LookupError("Upload not found.")
    fingerprint = _fingerprint(upload)
    existing = db.scalar(select(CalculationVersion).where(CalculationVersion.user_id == user_id, CalculationVersion.fingerprint == fingerprint))
    if existing is not None:
        return existing

    source = upload.normalized_data or {}
    result = calculate_financials(source.get("records", []), source.get("columns", []))
    calculation = CalculationVersion(
        user_id=user_id,
        upload_id=upload.id,
        engine_version=ENGINE_VERSION,
        fingerprint=fingerprint,
        status=result["status"],
        input_summary=result["input_summary"],
        completed_at=utcnow(),
    )
    db.add(calculation)
    db.flush()
    period_models: dict[str, FinancialPeriod] = {}
    for period in result["periods"]:
        model = FinancialPeriod(
            calculation_id=calculation.id,
            period_key=period["key"],
            start_date=period["start_date"],
            end_date=period["end_date"],
            currency=(source.get("metadata", {}).get("currency") or None),
            status=period["status"],
        )
        db.add(model)
        db.flush()
        period_models[period["key"]] = model
    source_location = source.get("metadata", {}).get("source_location") or ("PDF document" if upload.file_type == "pdf" else "data")
    for metric in result["metrics"]:
        dimensions_key = json.dumps(metric["dimensions"], sort_keys=True, separators=(",", ":"))
        model = CalculatedMetric(
            calculation_id=calculation.id,
            metric_key=metric["key"],
            dimensions_key=dimensions_key,
            value=metric["value"],
            unit=metric["unit"],
            status=metric["status"],
            breakdown=metric["breakdown"],
        )
        db.add(model)
        db.flush()
        evidence = metric["evidence"]
        db.add(MetricEvidence(
            metric_id=model.id,
            upload_id=upload.id,
            source_file=upload.filename,
            source_location=source_location,
            included_records=evidence["included_records"],
            excluded_records=evidence["excluded_records"],
            formula=evidence["formula"],
            mappings=evidence["mappings"],
            adjustments=evidence["adjustments"],
            engine_version=ENGINE_VERSION,
        ))
    for validation in result["validations"]:
        db.add(ValidationResult(calculation_id=calculation.id, **validation))
    forecast = result["forecast"]
    db.add(ForecastResult(calculation_id=calculation.id, **forecast))
    db.flush()
    return calculation


def _iso(value: date | datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def calculation_payload(db: Session, calculation: CalculationVersion, *, include_evidence: bool = False) -> dict[str, Any]:
    upload = db.scalar(select(Upload).where(Upload.id == calculation.upload_id, Upload.user_id == calculation.user_id))
    metrics = db.scalars(select(CalculatedMetric).where(CalculatedMetric.calculation_id == calculation.id).order_by(CalculatedMetric.id)).all()
    validations = db.scalars(select(ValidationResult).where(ValidationResult.calculation_id == calculation.id).order_by(ValidationResult.id)).all()
    periods = db.scalars(select(FinancialPeriod).where(FinancialPeriod.calculation_id == calculation.id).order_by(FinancialPeriod.start_date)).all()
    forecast = db.scalar(select(ForecastResult).where(ForecastResult.calculation_id == calculation.id))
    metric_payload = []
    for metric in metrics:
        item = {"id": metric.id, "key": metric.metric_key, "dimensions": json.loads(metric.dimensions_key or "{}"), "value": metric.value, "unit": metric.unit, "status": metric.status, "breakdown": metric.breakdown}
        if include_evidence:
            evidence = db.scalars(select(MetricEvidence).where(MetricEvidence.metric_id == metric.id)).all()
            item["evidence"] = [{"id": row.id, "source_file": row.source_file, "source_location": row.source_location, "included_records": row.included_records, "excluded_records": row.excluded_records, "formula": row.formula, "mappings": row.mappings, "adjustments": row.adjustments, "calculated_at": _iso(row.calculated_at), "engine_version": row.engine_version} for row in evidence]
        metric_payload.append(item)
    return {
        "id": calculation.id,
        "upload": {"id": upload.id, "filename": upload.filename} if upload else None,
        "engine_version": calculation.engine_version,
        "fingerprint": calculation.fingerprint,
        "status": calculation.status,
        "created_at": _iso(calculation.created_at),
        "completed_at": _iso(calculation.completed_at),
        "input_summary": calculation.input_summary,
        "periods": [{"id": row.id, "key": row.period_key, "start_date": _iso(row.start_date), "end_date": _iso(row.end_date), "currency": row.currency, "status": row.status} for row in periods],
        "metrics": metric_payload,
        "validations": [{"code": row.code, "status": row.status, "message": row.message, "row_ids": row.row_ids, "details": row.details} for row in validations],
        "forecast": None if forecast is None else {"horizon_days": forecast.horizon_days, "status": forecast.status, "opening_cash": forecast.opening_cash, "projected_inflow": forecast.projected_inflow, "projected_outflow": forecast.projected_outflow, "projected_closing_cash": forecast.projected_closing_cash, "shortage_date": _iso(forecast.shortage_date), "inputs": forecast.inputs, "daily_results": forecast.daily_results},
    }


def latest_calculation_payload(db: Session, *, user_id: int, include_evidence: bool = False) -> dict[str, Any] | None:
    calculation = db.scalar(select(CalculationVersion).where(CalculationVersion.user_id == user_id).order_by(CalculationVersion.created_at.desc(), CalculationVersion.id.desc()))
    return None if calculation is None else calculation_payload(db, calculation, include_evidence=include_evidence)
