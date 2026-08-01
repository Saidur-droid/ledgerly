from __future__ import annotations

import hashlib
import html
import json
import secrets
from datetime import UTC, datetime, timedelta
from io import BytesIO
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.financial_engine.service import calculate_upload
from app.models import (CalculatedMetric, CalculationVersion, ForecastResult,
    MonthlyClosingAuditEvent, MonthlyClosingRun, ReconciliationMatch, ReconciliationRun,
    ReportShare, ReportSnapshot, ReportTemplate, Upload, User, ValidationResult,
    WorkspaceClosingSettings, utcnow)

router = APIRouter(prefix="/api/v1")
LANGUAGES = {"en", "bn", "ar", "hi", "es"}
LABELS = {
    "en": {"report": "Financial report", "metric": "Metric", "value": "Value", "evidence": "Evidence"},
    "bn": {"report": "আর্থিক প্রতিবেদন", "metric": "পরিমাপ", "value": "মান", "evidence": "প্রমাণ"},
    "ar": {"report": "التقرير المالي", "metric": "المؤشر", "value": "القيمة", "evidence": "الدليل"},
    "hi": {"report": "वित्तीय रिपोर्ट", "metric": "मेट्रिक", "value": "मान", "evidence": "साक्ष्य"},
    "es": {"report": "Informe financiero", "metric": "Métrica", "value": "Valor", "evidence": "Evidencia"},
}


def _model(row: Any) -> dict[str, Any]:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def _settings_payload(row: WorkspaceClosingSettings) -> dict[str, Any]:
    data = _model(row)
    data["updated_at"] = row.updated_at.isoformat() if row.updated_at else None
    return data


@router.get("/closing/settings")
def get_closing_settings(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    row = db.get(WorkspaceClosingSettings, user.id)
    if row is None:
        row = WorkspaceClosingSettings(user_id=user.id)
        db.add(row); db.commit(); db.refresh(row)
    return _settings_payload(row)


@router.put("/closing/settings")
def save_closing_settings(payload: dict = Body(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    row = db.get(WorkspaceClosingSettings, user.id) or WorkspaceClosingSettings(user_id=user.id)
    allowed = {"source_mappings", "customer_aliases", "vendor_aliases", "categories", "bank_rules", "fiscal_period", "calculation_preferences", "approval_preferences", "selected_report_template_id"}
    if payload.get("selected_report_template_id") is not None and not db.scalar(select(ReportTemplate).where(ReportTemplate.id == payload["selected_report_template_id"], ReportTemplate.user_id == user.id)):
        raise HTTPException(404, "Report template not found.")
    for key in allowed & payload.keys(): setattr(row, key, payload[key])
    db.add(row); db.commit(); db.refresh(row)
    return _settings_payload(row)


def _run_payload(db: Session, run: MonthlyClosingRun) -> dict:
    audits = db.scalars(select(MonthlyClosingAuditEvent).where(MonthlyClosingAuditEvent.run_id == run.id).order_by(MonthlyClosingAuditEvent.id)).all()
    data = _model(run)
    for key in ("created_at", "completed_at"):
        if data[key]: data[key] = data[key].isoformat()
    data["audit_log"] = [{**_model(row), "created_at": row.created_at.isoformat()} for row in audits]
    return data


@router.post("/closing/runs", status_code=201)
def run_monthly_closing(payload: dict = Body(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    period = str(payload.get("period", ""))
    upload_ids = sorted(set(payload.get("upload_ids") or []))
    key = str(payload.get("idempotency_key") or "")
    if len(period) != 7 or period[4] != "-" or not upload_ids or not key:
        raise HTTPException(422, "period, upload_ids and idempotency_key are required.")
    existing = db.scalar(select(MonthlyClosingRun).where(MonthlyClosingRun.user_id == user.id, MonthlyClosingRun.idempotency_key == key))
    if existing: return _run_payload(db, existing)
    uploads = db.scalars(select(Upload).where(Upload.user_id == user.id, Upload.id.in_(upload_ids))).all()
    if len(uploads) != len(upload_ids): raise HTTPException(404, "One or more files were not found.")
    settings = db.get(WorkspaceClosingSettings, user.id) or WorkspaceClosingSettings(user_id=user.id)
    snapshot = _settings_payload(settings) if settings.updated_at else {"user_id": user.id}
    run = MonthlyClosingRun(user_id=user.id, period=period, upload_ids=upload_ids, idempotency_key=key,
        rules_snapshot=snapshot, progress={"clean": "complete", "reconcile": "pending", "calculate": "pending", "validate": "pending"})
    db.add(run); db.flush()
    db.add(MonthlyClosingAuditEvent(run_id=run.id, actor_user_id=user.id, action="started", details={"period": period, "upload_ids": upload_ids, "reused_approved_rules": True}))
    calculation = calculate_upload(db, user_id=user.id, upload_id=upload_ids[0])
    run.calculation_id = calculation.id
    validations = db.scalars(select(ValidationResult).where(ValidationResult.calculation_id == calculation.id)).all()
    exceptions = [{"type": "validation", "code": v.code, "status": v.status, "message": v.message, "state": "unresolved" if v.status == "blocked" else "new"} for v in validations if v.status != "valid"]
    if len(upload_ids) > 1:
        unmatched = db.scalars(select(ReconciliationMatch).join(ReconciliationRun, ReconciliationRun.id == ReconciliationMatch.run_id).where(ReconciliationRun.user_id == user.id, ReconciliationMatch.exception_status == "pending")).all()
        exceptions += [{"type": "reconciliation", "match_id": item.id, "status": "warning", "message": item.exception_type, "state": "unresolved"} for item in unmatched]
    blocked = any(item["status"] == "blocked" for item in exceptions)
    run.exceptions = exceptions
    run.progress = {"clean": "complete", "reconcile": "complete" if len(upload_ids) > 1 else "not_required", "calculate": "complete", "validate": "blocked" if blocked else "complete"}
    run.status = "blocked" if blocked else "completed"
    run.completed_at = None if blocked else utcnow()
    db.add(MonthlyClosingAuditEvent(run_id=run.id, actor_user_id=user.id, action=run.status, details={"exception_count": len(exceptions)}))
    db.commit(); db.refresh(run)
    return _run_payload(db, run)


@router.get("/closing/runs")
def list_closing_runs(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    return [_run_payload(db, row) for row in db.scalars(select(MonthlyClosingRun).where(MonthlyClosingRun.user_id == user.id).order_by(MonthlyClosingRun.id.desc())).all()]


@router.post("/closing/runs/{run_id}/reopen")
def reopen_closing(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    run = db.scalar(select(MonthlyClosingRun).where(MonthlyClosingRun.id == run_id, MonthlyClosingRun.user_id == user.id))
    if not run: raise HTTPException(404, "Closing run not found.")
    run.status = "review"; run.completed_at = None
    db.add(MonthlyClosingAuditEvent(run_id=run.id, actor_user_id=user.id, action="reopened", details={}))
    db.commit(); return _run_payload(db, run)


@router.get("/dashboard")
def owner_dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    calc = db.scalar(select(CalculationVersion).where(CalculationVersion.user_id == user.id).order_by(CalculationVersion.id.desc()))
    if not calc: raise HTTPException(404, "Run a financial calculation first.")
    metrics = db.scalars(select(CalculatedMetric).where(CalculatedMetric.calculation_id == calc.id)).all()
    validations = db.scalars(select(ValidationResult).where(ValidationResult.calculation_id == calc.id)).all()
    forecast = db.scalar(select(ForecastResult).where(ForecastResult.calculation_id == calc.id))
    items = [{"id": m.id, "key": m.metric_key, "value": m.value, "unit": m.unit, "status": m.status, "dimensions": json.loads(m.dimensions_key or "{}"), "breakdown": m.breakdown, "evidence_url": f"/api/v1/financials/metrics/{m.id}/evidence"} for m in metrics]
    by_key = {m.metric_key: m for m in metrics if m.dimensions_key in ("", "{}")}
    alerts = []
    def alert(kind: str, title: str, metric: CalculatedMetric | None, severity: str = "warning"):
        alerts.append({"type": kind, "title": title, "severity": severity, "metric_id": metric.id if metric else None, "evidence_url": f"/api/v1/financials/metrics/{metric.id}/evidence" if metric else None})
    if by_key.get("overdue_receivables") and (by_key["overdue_receivables"].value or 0) > 0: alert("overdue_invoices", "Overdue invoices require follow-up", by_key["overdue_receivables"])
    for m in metrics:
        if m.metric_key == "abnormal_expense": alert("abnormal_expenses", f"Abnormal expense: {json.loads(m.dimensions_key).get('category','category')}", m)
    fallback = by_key.get("revenue") or (metrics[0] if metrics else None)
    for v in validations:
        if v.status != "valid": alert("validation_warning" if v.status == "warning" else "missing_data", v.message, fallback, v.status)
    unmatched = db.scalar(select(ReconciliationMatch).join(ReconciliationRun, ReconciliationRun.id == ReconciliationMatch.run_id).where(ReconciliationRun.user_id == user.id, ReconciliationMatch.exception_status == "pending"))
    if unmatched: alert("unmatched_reconciliation", "Unmatched reconciliation items need review", fallback)
    if forecast and forecast.shortage_date: alert("cash_risk", f"Cash shortage projected on {forecast.shortage_date.isoformat()}", by_key.get("forecast_closing_cash"), "blocked")
    return {"calculation_id": calc.id, "status": calc.status, "metrics": items, "attention": alerts, "forecast": {"shortage_date": forecast.shortage_date.isoformat() if forecast and forecast.shortage_date else None}}


def _template(db: Session, user_id: int, template_id: int) -> ReportTemplate:
    row = db.scalar(select(ReportTemplate).where(ReportTemplate.id == template_id, ReportTemplate.user_id == user_id))
    if not row: raise HTTPException(404, "Report template not found.")
    return row


@router.post("/report-templates", status_code=201)
def create_template(payload: dict = Body(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    language = payload.get("language", "en")
    if language not in LANGUAGES: raise HTTPException(422, "Unsupported language.")
    row = ReportTemplate(user_id=user.id, title=payload.get("title") or "Monthly report", business_name=payload.get("business_name") or user.full_name, logo_data=payload.get("logo_data"), brand_color=payload.get("brand_color", "#7357FF"), language=language, sections=payload.get("sections") or ["executive_summary", "profit_loss", "cash_flow", "receivables_payables", "risks", "notes"], selected_kpis=payload.get("selected_kpis") or [], selected_charts=payload.get("selected_charts") or [], notes=payload.get("notes"))
    db.add(row); db.commit(); db.refresh(row); return _model(row)


@router.get("/report-templates")
def list_templates(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    return [_model(row) for row in db.scalars(select(ReportTemplate).where(ReportTemplate.user_id == user.id)).all()]


@router.put("/report-templates/{template_id}")
def update_template(template_id: int, payload: dict = Body(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    row = _template(db, user.id, template_id)
    if payload.get("language", row.language) not in LANGUAGES: raise HTTPException(422, "Unsupported language.")
    for key in {"title","business_name","logo_data","brand_color","language","sections","selected_kpis","selected_charts","notes"} & payload.keys(): setattr(row, key, payload[key])
    db.commit(); db.refresh(row); return _model(row)


def _report(db: Session, user_id: int, report_id: int) -> ReportSnapshot:
    row = db.scalar(select(ReportSnapshot).where(ReportSnapshot.id == report_id, ReportSnapshot.user_id == user_id))
    if not row: raise HTTPException(404, "Report not found.")
    return row


@router.post("/reports", status_code=201)
def create_report(payload: dict = Body(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    template = _template(db, user.id, int(payload.get("template_id", 0)))
    calc = db.scalar(select(CalculationVersion).where(CalculationVersion.id == payload.get("calculation_id"), CalculationVersion.user_id == user.id))
    if not calc: raise HTTPException(404, "Calculation not found.")
    if calc.status == "blocked": raise HTTPException(409, "Blocking validation prevents report generation.")
    metrics = db.scalars(select(CalculatedMetric).where(CalculatedMetric.calculation_id == calc.id, CalculatedMetric.status != "blocked")).all()
    validations = db.scalars(select(ValidationResult).where(ValidationResult.calculation_id == calc.id, ValidationResult.status != "valid")).all()
    selected = set(template.selected_kpis)
    content_metrics = [{"id": m.id, "key": m.metric_key, "value": m.value, "unit": m.unit, "dimensions": json.loads(m.dimensions_key or "{}"), "evidence_ref": f"metric:{m.id}"} for m in metrics if not selected or m.metric_key in selected]
    metric_map = {m["key"]: m for m in content_metrics if not m["dimensions"]}
    def refs(*keys: str) -> list[dict]: return [metric_map[key] for key in keys if key in metric_map]
    content = {"title": template.title, "business_name": template.business_name, "logo_data": template.logo_data, "brand_color": template.brand_color, "language": template.language, "direction": "rtl" if template.language == "ar" else "ltr", "sections": template.sections, "selected_charts": template.selected_charts, "notes": template.notes, "date_range": payload.get("date_range") or {"period": payload.get("period", "")}, "period": payload.get("period", ""), "currency": db.scalar(select(Upload).where(Upload.id == calc.upload_id)).normalized_data.get("metadata", {}).get("currency"), "metrics": content_metrics,
        "executive_summary": {"calculation_status": calc.status, "metric_refs": refs("revenue", "gross_profit", "net_profit", "closing_cash")},
        "profit_loss": refs("revenue", "cogs", "gross_profit", "operating_expenses", "net_profit", "gross_margin", "net_margin"),
        "cash_flow": refs("opening_cash", "cash_inflow", "cash_outflow", "closing_cash", "forecast_closing_cash"),
        "receivables_payables": refs("receivables", "overdue_receivables", "payables", "overdue_payables"),
        "risks": [{"code": v.code, "status": v.status, "message": v.message} for v in validations],
        "evidence_references": [m["evidence_ref"] for m in content_metrics]}
    report = ReportSnapshot(user_id=user.id, template_id=template.id, calculation_id=calc.id, period=content["period"], content=content)
    db.add(report); db.commit(); db.refresh(report); return {"id": report.id, **content}


def _pdf(content: dict) -> bytes:
    out = BytesIO(); doc = SimpleDocTemplate(out, pagesize=A4); styles = getSampleStyleSheet(); lang = LABELS[content["language"]]
    story = [Paragraph(content["title"], styles["Title"]), Paragraph(content["business_name"], styles["Heading2"]), Paragraph(f"{lang['report']} · {content['period']}", styles["BodyText"]), Paragraph(f"Calculation status: {content['executive_summary']['calculation_status']}", styles["BodyText"]), Spacer(1, 12)]
    rows = [[lang["metric"], lang["value"], lang["evidence"]]] + [[m["key"].replace("_", " ").title(), "—" if m["value"] is None else f"{m['value']:,.2f}", m["evidence_ref"]] for m in content["metrics"]]
    table = Table(rows); table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor(content["brand_color"])),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),.3,colors.grey)])); story.append(table); doc.build(story); return out.getvalue()


def _xlsx(content: dict) -> bytes:
    workbook = Workbook(); sheet = workbook.active; sheet.title = "Ledgerly Report"; labels = LABELS[content["language"]]
    sheet.append([content["title"]]); sheet.append([content["business_name"], content["period"]]); sheet.append([labels["metric"], labels["value"], labels["evidence"]])
    for metric in content["metrics"]: sheet.append([metric["key"], metric["value"], metric["evidence_ref"]])
    risks = workbook.create_sheet("Risks")
    risks.append(["Code", "Status", "Message"])
    for risk in content["risks"]: risks.append([risk["code"], risk["status"], risk["message"]])
    out = BytesIO(); workbook.save(out); return out.getvalue()


@router.get("/reports/{report_id}.{kind}")
def export_report(report_id: int, kind: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> StreamingResponse:
    report = _report(db, user.id, report_id)
    if kind not in {"pdf", "xlsx"}: raise HTTPException(404, "Export type not found.")
    data = _pdf(report.content) if kind == "pdf" else _xlsx(report.content)
    media = "application/pdf" if kind == "pdf" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return StreamingResponse(BytesIO(data), media_type=media, headers={"Content-Disposition": f'attachment; filename="ledgerly-report.{kind}"'})


@router.post("/reports/{report_id}/shares", status_code=201)
def share_report(report_id: int, payload: dict = Body(default={}), user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    _report(db, user.id, report_id); token = secrets.token_urlsafe(32); expires = datetime.now(UTC) + timedelta(hours=max(1, min(int(payload.get("expires_in_hours", 168)), 24*90)))
    row = ReportShare(user_id=user.id, report_id=report_id, token_hash=hashlib.sha256(token.encode()).hexdigest(), expires_at=expires)
    db.add(row); db.commit(); db.refresh(row); return {"id": row.id, "token": token, "url": f"/api/v1/public/reports/{token}", "expires_at": expires.isoformat()}


@router.delete("/reports/shares/{share_id}")
def revoke_share(share_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    row = db.scalar(select(ReportShare).where(ReportShare.id == share_id, ReportShare.user_id == user.id))
    if not row: raise HTTPException(404, "Share not found.")
    row.revoked_at = utcnow(); db.commit(); return {"status": "revoked"}


@router.get("/public/reports/{token}", response_class=HTMLResponse)
def public_report(token: str, db: Session = Depends(get_db)) -> str:
    row = db.scalar(select(ReportShare).where(ReportShare.token_hash == hashlib.sha256(token.encode()).hexdigest()))
    now = datetime.now(UTC)
    if not row or row.revoked_at or row.expires_at.replace(tzinfo=UTC) <= now: raise HTTPException(404, "This report link is unavailable.")
    report = db.get(ReportSnapshot, row.report_id); content = report.content; labels = LABELS[content["language"]]
    rows = "".join(f"<tr><td>{html.escape(m['key'].replace('_',' ').title())}</td><td>{html.escape(str(m['value']))}</td><td>{html.escape(m['evidence_ref'])}</td></tr>" for m in content["metrics"])
    risks = "".join(f"<li>{html.escape(r['message'])}</li>" for r in content["risks"])
    return f'''<!doctype html><html lang="{content['language']}" dir="{content['direction']}"><head><meta charset="utf-8"><meta name="robots" content="noindex"><title>{html.escape(content['title'])}</title></head><body><main><h1>{html.escape(content['title'])}</h1><h2>{html.escape(content['business_name'])}</h2><p>{html.escape(content['period'])}</p><p>Calculation status: {html.escape(content['executive_summary']['calculation_status'])}</p><table><thead><tr><th>{labels['metric']}</th><th>{labels['value']}</th><th>{labels['evidence']}</th></tr></thead><tbody>{rows}</tbody></table><ul>{risks}</ul></main></body></html>'''
