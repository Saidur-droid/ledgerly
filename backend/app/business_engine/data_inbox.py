import math
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

CANONICAL_ALIASES = {
    "date": ("date", "transaction date", "posting date"),
    "amount": ("amount", "transaction amount", "value"),
    "debit": ("debit", "withdrawal", "money out"),
    "credit": ("credit", "deposit", "money in"),
    "description": ("description", "details", "memo", "narration"),
    "reference": ("reference", "invoice", "transaction id", "check number"),
    "balance": ("balance", "running balance", "closing balance"),
    "currency": ("currency", "ccy"),
    "category": ("category", "account", "type"),
}


def _normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def suggest_mapping(columns: list[str]) -> tuple[dict[str, str], float]:
    mapping: dict[str, str] = {}
    for column in columns:
        name = _normalized(column)
        for canonical, aliases in CANONICAL_ALIASES.items():
            if canonical not in mapping and (name in aliases or any(alias in name for alias in aliases)):
                mapping[canonical] = column
                break
    required = {"date", "amount"}
    if "amount" not in mapping and {"debit", "credit"} & mapping.keys():
        required = {"date"}
    confidence = min(0.98, 0.35 + len(mapping) * 0.08 + len(required & mapping.keys()) * 0.12)
    return mapping, round(confidence, 2)


def detect_profile(filename: str, records: list[dict[str, Any]], columns: list[str]) -> dict[str, Any]:
    mapping, confidence = suggest_mapping(columns)
    words = _normalized(Path(filename).stem + " " + " ".join(columns))
    role = "bank_statement" if any(word in words for word in ("bank", "statement", "withdrawal", "deposit")) else "ledger"
    currencies = []
    currency_column = mapping.get("currency")
    if currency_column:
        currencies = [str(row.get(currency_column, "")).upper() for row in records if row.get(currency_column)]
    symbols = " ".join(str(value) for row in records[:50] for value in row.values())
    currency = Counter(currencies).most_common(1)[0][0] if currencies else ("USD" if "$" in symbols else None)
    dates = []
    date_column = mapping.get("date")
    if date_column:
        for row in records:
            parsed = pd.to_datetime(row.get(date_column), errors="coerce")
            if not pd.isna(parsed):
                dates.append(parsed)
    period = None
    if dates:
        period = f"{min(dates).date().isoformat()} to {max(dates).date().isoformat()}"
    return {"role": role, "period": period, "currency": currency, "column_mapping": mapping, "mapping_confidence": confidence}


def find_cleaning_issues(records: list[dict[str, Any]], mapping: dict[str, str]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    fingerprints: dict[str, int] = {}
    for index, row in enumerate(records, start=2):
        fingerprint = repr(sorted((key, str(value).strip()) for key, value in row.items()))
        if fingerprint in fingerprints:
            issues.append({"row_number": index, "issue_type": "duplicate_row", "severity": "error", "original_value": row, "suggested_value": None, "explanation": f"Duplicates source row {fingerprints[fingerprint]}."})
        else:
            fingerprints[fingerprint] = index
        for canonical, column in mapping.items():
            value = row.get(column)
            if value is None or str(value).strip() == "":
                if canonical in {"date", "amount"}:
                    issues.append({"row_number": index, "column_name": column, "issue_type": "missing_value", "severity": "error", "original_value": value, "suggested_value": None, "explanation": f"Required {canonical} value is missing."})
                continue
            if canonical == "date" and pd.isna(pd.to_datetime(value, errors="coerce")):
                issues.append({"row_number": index, "column_name": column, "issue_type": "bad_date", "severity": "error", "original_value": value, "suggested_value": None, "explanation": "Date cannot be parsed deterministically."})
            if canonical in {"amount", "debit", "credit", "balance"} and isinstance(value, str):
                cleaned = re.sub(r"[^0-9.()\-]", "", value).replace("(", "-").replace(")", "")
                try:
                    number = float(cleaned)
                    if math.isfinite(number):
                        issues.append({"row_number": index, "column_name": column, "issue_type": "number_as_text", "severity": "warning", "original_value": value, "suggested_value": number, "explanation": "Numeric value is stored as text; review before conversion."})
                except ValueError:
                    issues.append({"row_number": index, "column_name": column, "issue_type": "invalid_number", "severity": "error", "original_value": value, "suggested_value": None, "explanation": "Financial value cannot be parsed as a number."})
    return issues[:1000]


def canonical_transactions(records: list[dict[str, Any]], mapping: dict[str, str]) -> list[dict[str, Any]]:
    transactions = []
    for row_number, row in enumerate(records, start=2):
        def value(name: str) -> Any:
            return row.get(mapping[name]) if name in mapping else None
        raw_amount = value("amount")
        direction = 1
        if raw_amount is None:
            credit, debit = value("credit"), value("debit")
            raw_amount = credit if credit not in (None, "") else debit
            direction = -1 if debit not in (None, "") and credit in (None, "") else 1
        try:
            signed_amount = float(re.sub(r"[^0-9.\-]", "", str(raw_amount))) * direction
            amount = abs(signed_amount)
        except (TypeError, ValueError):
            amount = signed_amount = None
        parsed_date = pd.to_datetime(value("date"), errors="coerce")
        transactions.append({"row": row_number, "date": None if pd.isna(parsed_date) else parsed_date.date().isoformat(), "amount": amount, "signed_amount": signed_amount, "reference": str(value("reference") or "").strip().lower(), "description": str(value("description") or "").strip()})
    return transactions


def exact_matches(bank: list[dict[str, Any]], ledger: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matches = []
    used_ledger: set[int] = set()
    for bank_tx in bank:
        candidates = [tx for tx in ledger if tx["row"] not in used_ledger and tx["amount"] is not None and tx["amount"] == bank_tx["amount"] and tx["date"] == bank_tx["date"]]
        if bank_tx["reference"]:
            reference_matches = [tx for tx in candidates if tx["reference"] == bank_tx["reference"]]
            if reference_matches:
                candidates = reference_matches
        if len(candidates) == 1:
            ledger_tx = candidates[0]
            used_ledger.add(ledger_tx["row"])
            reference_used = bool(bank_tx["reference"] and bank_tx["reference"] == ledger_tx["reference"])
            state = {"bank_row": bank_tx["row"], "ledger_row": ledger_tx["row"], "match_type": "exact"}
            matches.append({"bank_row": bank_tx["row"], "ledger_row": ledger_tx["row"], "match_type": "exact", "score": 1.0 if reference_used else 0.95, "rule": "same date + amount + reference" if reference_used else "same date + amount; unique candidate", "amount": bank_tx["amount"], "transaction_date": bank_tx["date"], "status": "pending", "evidence": {"bank": bank_tx, "ledger": ledger_tx}, "original_state": state, "suggested_state": state})
        else:
            match_type = "possible" if candidates else "unmatched"
            exception = detect_exception(bank_tx, candidates, ledger)
            state = {"bank_row": bank_tx["row"], "ledger_row": None, "match_type": match_type}
            matches.append({"bank_row": bank_tx["row"], "ledger_row": None, "match_type": match_type, "score": 0.6 if candidates else 0.0, "rule": "multiple same-date/amount candidates require review" if candidates else "no same-date/amount ledger transaction", "amount": bank_tx["amount"], "transaction_date": bank_tx["date"], "status": "pending", "evidence": {"bank": bank_tx, "candidate_rows": [tx["row"] for tx in candidates]}, "exception_type": exception, "exception_status": "pending", "original_state": state, "suggested_state": state})
    for ledger_tx in ledger:
        if ledger_tx["row"] not in used_ledger:
            state = {"bank_row": None, "ledger_row": ledger_tx["row"], "match_type": "unmatched"}
            matches.append({"bank_row": None, "ledger_row": ledger_tx["row"], "match_type": "unmatched", "score": 0.0, "rule": "no exact bank transaction", "amount": ledger_tx["amount"], "transaction_date": ledger_tx["date"], "status": "pending", "evidence": {"ledger": ledger_tx}, "exception_type": "unmatched_ledger_transaction", "exception_status": "pending", "original_state": state, "suggested_state": state})
    return matches


def detect_exception(bank_tx: dict[str, Any], candidates: list[dict[str, Any]], ledger: list[dict[str, Any]]) -> str:
    """Conservative deterministic labels: these are review possibilities, never allegations."""
    description = bank_tx.get("description", "").lower()
    if any(word in description for word in ("fee", "service charge", "bank charge")):
        return "bank_fee"
    if any(word in description for word in ("refund", "returned payment")):
        return "refund"
    if any(word in description for word in ("reversal", "reversed")):
        return "reversal"
    same_amount = [tx for tx in ledger if tx.get("amount") == bank_tx.get("amount")]
    if len(same_amount) > 1 or len(candidates) > 1:
        return "duplicate_payment"
    same_reference = [tx for tx in ledger if bank_tx.get("reference") and tx.get("reference") == bank_tx.get("reference")]
    if same_reference:
        return "amount_date_reference_mismatch"
    if bank_tx.get("amount", 0) > 0 and any(word in description for word in ("deposit", "credit")):
        return "missing_deposit"
    return "unmatched_bank_transaction"
