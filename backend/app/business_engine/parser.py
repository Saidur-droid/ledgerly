import io
import json
import re
from dataclasses import dataclass
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


@dataclass(frozen=True)
class ParsedBusinessData:
    records: list[dict[str, Any]]
    columns: list[str]
    metrics: dict[str, float]
    confidence: float
    warnings: list[str]


def _numeric_total(frame: pd.DataFrame, aliases: tuple[str, ...]) -> float | None:
    normalized = {str(column).strip().lower(): column for column in frame.columns}
    for alias in aliases:
        match = next((original for name, original in normalized.items() if alias in name), None)
        if match is not None:
            values = pd.to_numeric(frame[match], errors="coerce").dropna()
            if not values.empty:
                return round(float(values.sum()), 2)
    return None


def _frame_result(frame: pd.DataFrame) -> ParsedBusinessData:
    frame = frame.dropna(how="all").replace({float("nan"): None})
    metrics = {
        name: value
        for name, aliases in METRIC_ALIASES.items()
        if (value := _numeric_total(frame, aliases)) is not None
    }
    if "profit" not in metrics and {"revenue", "expenses"} <= metrics.keys():
        metrics["profit"] = round(metrics["revenue"] - metrics["expenses"], 2)
    confidence = min(0.98, 0.42 + len(metrics) * 0.12 + min(len(frame), 100) / 1000)
    warnings = [] if metrics else ["No standard financial KPI columns were detected."]
    safe_frame = frame.head(500).copy()
    safe_frame.columns = [str(column) for column in safe_frame.columns]
    return ParsedBusinessData(
        records=safe_frame.to_dict(orient="records"),
        columns=list(safe_frame.columns),
        metrics=metrics,
        confidence=round(confidence, 2),
        warnings=warnings,
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
    )


def parse_business_file(filename: str, content: bytes) -> ParsedBusinessData:
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError("Unsupported file type. Use CSV, XLSX, PDF, or JSON.")
    if extension == ".csv":
        return _frame_result(pd.read_csv(io.BytesIO(content)))
    if extension == ".xlsx":
        return _frame_result(pd.read_excel(io.BytesIO(content)))
    if extension == ".json":
        payload = json.loads(content)
        rows = payload if isinstance(payload, list) else [payload]
        return _frame_result(pd.json_normalize(rows))
    return _parse_pdf(content)
