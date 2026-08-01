import io
import json
import math
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pandas as pd
from pypdf import PdfReader

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".pdf", ".json"}
METRIC_ALIASES = {
    "revenue": ("revenue", "sales", "income", "turnover", "gross sales"),
    "expenses": ("expense", "expenses", "cost", "costs", "spend", "outflow"),
    "profit": ("profit", "net income", "net profit"),
    "cash": ("cash", "balance", "cash balance"),
}
DATE_ALIASES = ("date", "month", "period")


@dataclass(frozen=True)
class ParsedBusinessData:
    records: list[dict[str, Any]]
    columns: list[str]
    metrics: dict[str, float]
    confidence: float
    warnings: list[str]
    metadata: dict[str, Any]


def _find_column(frame: pd.DataFrame, aliases: tuple[str, ...]) -> Any | None:
    normalized = {
        re.sub(r"[_\-]+", " ", str(column).strip().lower()): column
        for column in frame.columns
    }
    for alias in aliases:
        if alias in normalized:
            return normalized[alias]
    for alias in aliases:
        match = next(
            (original for name, original in normalized.items() if alias in name),
            None,
        )
        if match is not None:
            return match
    return None


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(str(value).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _period_sort_value(value: Any, position: int) -> tuple[int, Any]:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return 1, position
    return 0, parsed


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        return value
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    item = getattr(value, "item", None)
    return item() if callable(item) else value


def _normalized_period_records(
    frame: pd.DataFrame,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    safe_frame = frame.head(500).copy()
    safe_frame.columns = [str(column) for column in safe_frame.columns]
    column_map = {
        name: _find_column(safe_frame, aliases)
        for name, aliases in METRIC_ALIASES.items()
    }
    date_column = _find_column(safe_frame, DATE_ALIASES)
    records: list[dict[str, Any]] = []
    for position, source in enumerate(safe_frame.to_dict(orient="records")):
        record = {
            str(name): _json_safe_value(value)
            for name, value in source.items()
        }
        if date_column is not None:
            record["date"] = record.get(str(date_column))
        for name, column in column_map.items():
            if column is not None:
                record[name] = _number(record.get(str(column)))
        if record.get("profit") is None:
            revenue = record.get("revenue")
            expenses = record.get("expenses")
            if revenue is not None and expenses is not None:
                record["profit"] = round(revenue - expenses, 2)
        revenue = record.get("revenue")
        profit = record.get("profit")
        record["net_margin"] = (
            round(profit / revenue * 100, 2)
            if revenue not in (None, 0) and profit is not None
            else None
        )
        record["revenue_growth"] = None
        record["_position"] = position
        records.append(record)

    chronological = sorted(
        records,
        key=lambda item: _period_sort_value(
            item.get("date"),
            int(item["_position"]),
        ),
    )
    previous_revenue: float | None = None
    for record in chronological:
        revenue = record.get("revenue")
        if revenue is not None and previous_revenue not in (None, 0):
            record["revenue_growth"] = round(
                (revenue - previous_revenue) / previous_revenue * 100,
                2,
            )
        if revenue is not None:
            previous_revenue = revenue
    for record in records:
        record.pop("_position", None)

    cash_column = column_map["cash"]
    cash_values = [
        float(record["cash"])
        for record in chronological
        if record.get("cash") is not None
    ]
    normalized_cash_column = (
        re.sub(r"[_\-]+", " ", str(cash_column).strip().lower())
        if cash_column is not None
        else ""
    )
    cash_is_flow = "flow" in normalized_cash_column
    cash_metadata: dict[str, Any] = {}
    if cash_values:
        cash_metadata = {
            "semantic": (
                "period_cash_flow" if cash_is_flow else "period_ending_balance"
            ),
            "headline_calculation": "sum" if cash_is_flow else "latest",
            "assumption": (
                "Cash is summed because the source column explicitly identifies "
                "period cash flow."
                if cash_is_flow
                else "Cash is treated as a period-ending balance; the latest "
                "dated value is the headline and balances are not summed."
            ),
            "latest": round(cash_values[-1], 2),
            "average": round(sum(cash_values) / len(cash_values), 2),
            "minimum": round(min(cash_values), 2),
            "maximum": round(max(cash_values), 2),
            "change": round(cash_values[-1] - cash_values[0], 2),
        }
    return records, {"cash": cash_metadata} if cash_metadata else {}


def _frame_result(frame: pd.DataFrame) -> ParsedBusinessData:
    frame = frame.dropna(how="all")
    records, metadata = _normalized_period_records(frame)
    metrics: dict[str, float] = {}
    for name in ("revenue", "expenses", "profit"):
        values = [
            float(record[name])
            for record in records
            if record.get(name) is not None
        ]
        if values:
            metrics[name] = round(sum(values), 2)
    if "profit" not in metrics and {"revenue", "expenses"} <= metrics.keys():
        metrics["profit"] = round(metrics["revenue"] - metrics["expenses"], 2)
    cash_values = [
        float(record["cash"])
        for record in records
        if record.get("cash") is not None
    ]
    if cash_values:
        cash_semantic = metadata["cash"]["semantic"]
        metrics["cash"] = round(
            sum(cash_values)
            if cash_semantic == "period_cash_flow"
            else metadata["cash"]["latest"],
            2,
        )
    confidence = min(0.98, 0.42 + len(metrics) * 0.12 + min(len(frame), 100) / 1000)
    warnings = [] if metrics else ["No standard financial KPI columns were detected."]
    return ParsedBusinessData(
        records=records,
        columns=[str(column) for column in frame.columns],
        metrics=metrics,
        confidence=round(confidence, 2),
        warnings=warnings,
        metadata=metadata,
    )


def _parse_pdf(content: bytes) -> ParsedBusinessData:
    text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(content)).pages)
    metrics: dict[str, float] = {}
    for name, aliases in METRIC_ALIASES.items():
        for alias in aliases:
            match = re.search(rf"{re.escape(alias)}\s*[:\-]?\s*\$?\s*([\d,]+(?:\.\d+)?)", text, re.I)
            if match:
                metrics[name] = float(match.group(1).replace(",", ""))
                break
    if "profit" not in metrics and {"revenue", "expenses"} <= metrics.keys():
        metrics["profit"] = metrics["revenue"] - metrics["expenses"]
    return ParsedBusinessData(
        records=[{"text": text[:12000]}],
        columns=["text"],
        metrics=metrics,
        confidence=round(min(0.9, 0.35 + len(metrics) * 0.13), 2),
        warnings=[] if text else ["The PDF did not contain extractable text."],
        metadata={},
    )


def parse_business_file(filename: str, content: bytes) -> ParsedBusinessData:
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError("Unsupported file type. Use CSV, XLSX, PDF, or JSON.")
    if extension == ".csv":
        try:
            result = _frame_result(pd.read_csv(io.BytesIO(content)))
            return replace(result, metadata={**result.metadata, "source_location": "CSV data"})
        except pd.errors.EmptyDataError as error:
            raise ValueError(
                "The CSV is empty or does not contain readable columns."
            ) from error
        except pd.errors.ParserError as error:
            raise ValueError(
                "The CSV is malformed and could not be parsed."
            ) from error
    if extension == ".xlsx":
        workbook = pd.ExcelFile(io.BytesIO(content))
        sheet_name = workbook.sheet_names[0]
        result = _frame_result(pd.read_excel(workbook, sheet_name=sheet_name))
        return replace(result, metadata={**result.metadata, "source_location": sheet_name})
    if extension == ".json":
        payload = json.loads(content)
        rows = payload if isinstance(payload, list) else [payload]
        result = _frame_result(pd.json_normalize(rows))
        return replace(result, metadata={**result.metadata, "source_location": "JSON root"})
    result = _parse_pdf(content)
    return replace(result, metadata={**result.metadata, "source_location": "PDF document"})
