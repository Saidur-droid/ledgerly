"""Pure, deterministic financial calculations. No model or network calls."""

from __future__ import annotations

import calendar
import math
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

ENGINE_VERSION = "ledgerly-financial-engine/1.0.0"
STATUS_RANK = {"valid": 0, "warning": 1, "blocked": 2}

ALIASES = {
    "date": ("date", "transaction date", "posting date", "invoice date", "period", "month"),
    "due_date": ("due date", "payment due", "maturity date"),
    "amount": ("amount", "value", "actual"),
    "debit": ("debit", "withdrawal", "money out"),
    "credit": ("credit", "deposit", "money in"),
    "revenue": ("revenue", "sales", "income", "turnover", "gross sales"),
    "cogs": ("cogs", "cost of goods sold", "cost of sales", "direct cost"),
    "operating_expenses": ("operating expenses", "opex", "operating expense", "expenses", "expense"),
    "profit": ("profit", "net profit", "net income"),
    "opening_cash": ("opening cash", "opening balance", "beginning cash"),
    "closing_cash": ("closing cash", "closing balance", "cash balance", "cash"),
    "receivables": ("receivables", "accounts receivable", "ar", "amount receivable"),
    "payables": ("payables", "accounts payable", "ap", "amount payable"),
    "outstanding": ("outstanding", "open balance", "balance due"),
    "budget": ("budget", "budget amount", "planned"),
    "actual": ("actual", "actual amount"),
    "category": ("category", "account category", "account", "type"),
    "product": ("product", "item", "sku", "service"),
    "transaction_id": ("transaction id", "id", "reference", "invoice", "invoice number"),
}

FORMULAS = {
    "revenue": "sum(revenue records)",
    "cogs": "sum(cost of goods sold records)",
    "gross_profit": "revenue - COGS",
    "operating_expenses": "sum(operating expense records)",
    "net_profit": "revenue - COGS - operating expenses",
    "cash_inflow": "sum(positive signed cash movements)",
    "cash_outflow": "sum(abs(negative signed cash movements))",
    "opening_cash": "earliest explicit opening cash balance",
    "closing_cash": "latest explicit closing cash balance; otherwise opening cash + inflow - outflow",
    "receivables": "sum(open receivable balances as of period end)",
    "payables": "sum(open payable balances as of period end)",
    "overdue_receivables": "sum(receivables with due date before period end)",
    "overdue_payables": "sum(payables with due date before period end)",
    "budget_variance": "actual - budget",
    "period_change": "current period value - previous period value",
    "period_change_percent": "(current - previous) / abs(previous) * 100",
    "forecast_closing_cash": "closing cash + 30 * trailing average daily inflow - 30 * trailing average daily outflow",
}


def _key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()


def _mapping(columns: list[str]) -> dict[str, str]:
    normalized = {_key(column): column for column in columns}
    result: dict[str, str] = {}
    for canonical, aliases in ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                result[canonical] = normalized[alias]
                break
        if canonical not in result:
            for alias in aliases:
                match = next((source for name, source in normalized.items() if len(alias) > 2 and alias in name), None)
                if match is not None:
                    result[canonical] = match
                    break
    return result


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    text = str(value).strip().replace(",", "").replace("$", "")
    if text.startswith("(") and text.endswith(")"):
        text = f"-{text[1:-1]}"
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None
    return round(value, 2) if math.isfinite(value) else None


def _date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value in (None, ""):
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y", "%Y-%m", "%b %Y", "%B %Y"):
        try:
            parsed = datetime.strptime(text, fmt).date()
            if fmt in {"%Y-%m", "%b %Y", "%B %Y"}:
                return parsed.replace(day=calendar.monthrange(parsed.year, parsed.month)[1])
            return parsed
        except ValueError:
            pass
    return None


def _status(*statuses: str) -> str:
    return max(statuses or ("valid",), key=lambda item: STATUS_RANK[item])


def _metric(key: str, value: float | None, included: list[str], excluded: list[str], mappings: dict[str, str], *, status: str = "valid", breakdown: dict[str, Any] | None = None, formula: str | None = None, dimensions: dict[str, str] | None = None) -> dict[str, Any]:
    if value is None:
        status = "blocked"
    return {
        "key": key,
        "value": None if value is None else round(value, 2),
        "status": status,
        "unit": "percent" if key.endswith("percent") else "currency",
        "dimensions": dimensions or {},
        "breakdown": breakdown or {},
        "evidence": {
            "included_records": included,
            "excluded_records": excluded,
            "formula": formula or FORMULAS.get(key, "deterministic aggregation of mapped source records"),
            "mappings": mappings,
            "adjustments": [],
        },
    }


def calculate_financials(records: list[dict[str, Any]], columns: list[str] | None = None, *, as_of: date | None = None) -> dict[str, Any]:
    """Return metrics, validations, periods and forecast without mutating inputs."""
    columns = list(dict.fromkeys([*(columns or []), *(str(key) for row in records for key in row)]))
    mapping = _mapping(columns)
    validations: list[dict[str, Any]] = []
    normalized: list[dict[str, Any]] = []
    invalid_rows: list[str] = []
    for position, source in enumerate(records, start=2):
        row_id = str(source.get(mapping.get("transaction_id", "")) or f"row:{position}")
        tx_date = _date(source.get(mapping.get("date", "")))
        if "date" in mapping and source.get(mapping["date"]) not in (None, "") and tx_date is None:
            validations.append({"code": "invalid_period", "status": "blocked", "message": "A source period/date cannot be parsed deterministically.", "row_ids": [row_id], "details": {"value": str(source.get(mapping["date"]))}})
        debit = _number(source.get(mapping.get("debit", "")))
        credit = _number(source.get(mapping.get("credit", "")))
        if debit is not None and credit is not None and debit != 0 and credit != 0:
            validations.append({"code": "debit_credit_both_set", "status": "blocked", "message": "Debit and credit are both populated on one transaction.", "row_ids": [row_id], "details": {}})
            invalid_rows.append(row_id)
        if (debit is not None and debit < 0) or (credit is not None and credit < 0):
            validations.append({"code": "negative_debit_credit", "status": "warning", "message": "Debit/credit columns should contain non-negative magnitudes.", "row_ids": [row_id], "details": {}})
        normalized.append({
            "id": row_id, "date": tx_date, "due_date": _date(source.get(mapping.get("due_date", ""))),
            "amount": _number(source.get(mapping.get("amount", ""))), "debit": debit, "credit": credit,
            **{name: _number(source.get(mapping.get(name, ""))) for name in ("revenue", "cogs", "operating_expenses", "profit", "opening_cash", "closing_cash", "receivables", "payables", "outstanding", "budget", "actual")},
            "category": str(source.get(mapping.get("category", "")) or "").strip(),
            "product": str(source.get(mapping.get("product", "")) or "").strip(),
        })

    if not records:
        validations.append({"code": "empty_input", "status": "blocked", "message": "The source contains no records.", "row_ids": [], "details": {}})
    dated = [row["date"] for row in normalized if row["date"] is not None]
    effective_as_of = as_of or (max(dated) if dated else None)
    if effective_as_of is None:
        validations.append({"code": "missing_period", "status": "blocked", "message": "At least one valid date or explicit calculation period is required.", "row_ids": [], "details": {}})

    debit_total = round(sum(abs(row["debit"] or 0) for row in normalized), 2)
    credit_total = round(sum(abs(row["credit"] or 0) for row in normalized), 2)
    if "debit" in mapping and "credit" in mapping and abs(debit_total - credit_total) > 0.01:
        validations.append({"code": "unbalanced_debits_credits", "status": "warning", "message": "Debit and credit totals do not balance.", "row_ids": [row["id"] for row in normalized], "details": {"debits": debit_total, "credits": credit_total, "variance": round(debit_total-credit_total, 2)}})

    valid_rows = [row for row in normalized if row["id"] not in invalid_rows]
    excluded = list(dict.fromkeys(invalid_rows))
    all_ids = [row["id"] for row in valid_rows]
    category_words = lambda row: _key(row["category"])

    def explicit_sum(field: str) -> tuple[float | None, list[str]]:
        selected = [row for row in valid_rows if row[field] is not None]
        return (round(sum(row[field] for row in selected), 2), [row["id"] for row in selected]) if selected else (None, [])

    revenue, revenue_ids = explicit_sum("revenue")
    cogs, cogs_ids = explicit_sum("cogs")
    opex, opex_ids = explicit_sum("operating_expenses")
    reported_profit, reported_profit_ids = explicit_sum("profit")
    if revenue is None:
        selected = [row for row in valid_rows if row["amount"] is not None and any(word in category_words(row) for word in ("revenue", "sales", "income"))]
        revenue, revenue_ids = (round(sum(abs(row["amount"]) for row in selected), 2), [row["id"] for row in selected]) if selected else (None, [])
    if cogs is None:
        selected = [row for row in valid_rows if row["amount"] is not None and any(word in category_words(row) for word in ("cogs", "cost of goods", "cost of sales", "direct cost"))]
        cogs, cogs_ids = (round(sum(abs(row["amount"]) for row in selected), 2), [row["id"] for row in selected]) if selected else (None, [])
    if opex is None:
        selected = [row for row in valid_rows if row["amount"] is not None and any(word in category_words(row) for word in ("expense", "opex", "rent", "payroll", "utilities")) and not any(word in category_words(row) for word in ("cogs", "cost of goods", "cost of sales"))]
        opex, opex_ids = (round(sum(abs(row["amount"]) for row in selected), 2), [row["id"] for row in selected]) if selected else (None, [])
    if reported_profit is None and revenue is not None and opex is not None and cogs is None:
        reported_profit = round(revenue - opex, 2)
        reported_profit_ids = list(dict.fromkeys(revenue_ids + opex_ids))

    cash_rows = [row for row in valid_rows if row["debit"] is not None or row["credit"] is not None]
    inflow = round(sum(abs(row["credit"] or 0) for row in cash_rows), 2) if cash_rows else None
    outflow = round(sum(abs(row["debit"] or 0) for row in cash_rows), 2) if cash_rows else None
    if not cash_rows:
        signed = [row for row in valid_rows if row["amount"] is not None and any(word in category_words(row) for word in ("cash", "bank"))]
        if signed:
            inflow = round(sum(row["amount"] for row in signed if row["amount"] > 0), 2)
            outflow = round(sum(abs(row["amount"]) for row in signed if row["amount"] < 0), 2)
            cash_rows = signed

    opening_values = [(row["date"] or date.min, row["opening_cash"], row["id"]) for row in valid_rows if row["opening_cash"] is not None]
    closing_values = [(row["date"] or date.min, row["closing_cash"], row["id"]) for row in valid_rows if row["closing_cash"] is not None]
    opening = min(opening_values)[1] if opening_values else None
    closing = max(closing_values)[1] if closing_values else (round(opening + inflow - outflow, 2) if None not in (opening, inflow, outflow) else None)
    if opening_values and closing_values and None not in (inflow, outflow):
        expected = round(opening + inflow - outflow, 2)
        if abs(expected - closing) > 0.01:
            validations.append({"code": "cash_balance_mismatch", "status": "warning", "message": "Opening cash plus net movement does not equal closing cash.", "row_ids": [item[2] for item in opening_values + closing_values], "details": {"expected": expected, "reported": closing, "variance": round(closing-expected, 2)}})

    metrics = [
        _metric("revenue", revenue, revenue_ids, excluded, mapping),
        _metric("cogs", cogs, cogs_ids, excluded, mapping),
        _metric("gross_profit", None if revenue is None or cogs is None else revenue-cogs, list(dict.fromkeys(revenue_ids+cogs_ids)), excluded, mapping, breakdown={"revenue": revenue, "cogs": cogs}),
        _metric("operating_expenses", opex, opex_ids, excluded, mapping),
        _metric("net_profit", None if None in (revenue, cogs, opex) else revenue-cogs-opex, list(dict.fromkeys(revenue_ids+cogs_ids+opex_ids)), excluded, mapping, breakdown={"revenue": revenue, "cogs": cogs, "operating_expenses": opex}),
        _metric("reported_profit", reported_profit, reported_profit_ids, excluded, mapping, formula="sum(explicit source-reported profit records; not substituted for calculated net profit)"),
        _metric("cash_inflow", inflow, [row["id"] for row in cash_rows], excluded, mapping),
        _metric("cash_outflow", outflow, [row["id"] for row in cash_rows], excluded, mapping),
        _metric("opening_cash", opening, [item[2] for item in opening_values], excluded, mapping),
        _metric("closing_cash", closing, [item[2] for item in closing_values] or [row["id"] for row in cash_rows], excluded, mapping, breakdown={"opening_cash": opening, "cash_inflow": inflow, "cash_outflow": outflow}),
    ]

    ar_rows: list[dict[str, Any]] = []
    ap_rows: list[dict[str, Any]] = []
    for row in valid_rows:
        amount = row["outstanding"]
        if row["receivables"] is not None:
            amount = row["receivables"]
            ar_rows.append({**row, "open": abs(amount)})
        elif row["payables"] is not None:
            amount = row["payables"]
            ap_rows.append({**row, "open": abs(amount)})
        elif amount is not None and any(word in category_words(row) for word in ("receivable", "accounts receivable", " ar ")):
            ar_rows.append({**row, "open": abs(amount)})
        elif amount is not None and any(word in category_words(row) for word in ("payable", "accounts payable", " ap ")):
            ap_rows.append({**row, "open": abs(amount)})
    for key, rows in (("receivables", ar_rows), ("payables", ap_rows)):
        total = round(sum(row["open"] for row in rows), 2) if rows else None
        metrics.append(_metric(key, total, [row["id"] for row in rows], excluded, mapping))
        overdue = [row for row in rows if effective_as_of and row["due_date"] and row["due_date"] < effective_as_of]
        missing_due = [row["id"] for row in rows if row["due_date"] is None]
        overdue_key = f"overdue_{key}"
        overdue_status = "warning" if missing_due else "valid"
        metrics.append(_metric(overdue_key, round(sum(row["open"] for row in overdue), 2) if rows else None, [row["id"] for row in overdue], excluded+missing_due, mapping, status=overdue_status))
        for label, low, high in (("current", -10**9, 0), ("1_30", 1, 30), ("31_60", 31, 60), ("61_90", 61, 90), ("90_plus", 91, 10**9)):
            bucket = [row for row in rows if effective_as_of and row["due_date"] is not None and low <= (effective_as_of-row["due_date"]).days <= high]
            metrics.append(_metric(f"{key}_aging_{label}", round(sum(row["open"] for row in bucket), 2) if rows else None, [row["id"] for row in bucket], excluded+missing_due, mapping, status=overdue_status, formula=f"sum({key} where days overdue is in {label.replace('_', '-')} bucket)"))

    groups: dict[tuple[str, str], dict[str, Any]] = defaultdict(lambda: {"revenue": 0.0, "cogs": 0.0, "ids": []})
    for row in valid_rows:
        dimension = row["product"] or row["category"]
        kind = "product" if row["product"] else "category"
        if not dimension:
            continue
        row_revenue = row["revenue"] or (abs(row["amount"]) if any(word in category_words(row) for word in ("revenue", "sales")) and row["amount"] is not None else 0)
        row_cost = row["cogs"] or (abs(row["amount"]) if any(word in category_words(row) for word in ("cogs", "cost of goods", "direct cost")) and row["amount"] is not None else 0)
        if row_revenue or row_cost:
            groups[(kind, dimension)]["revenue"] += row_revenue
            groups[(kind, dimension)]["cogs"] += row_cost
            groups[(kind, dimension)]["ids"].append(row["id"])
    for (kind, dimension), values in groups.items():
        metrics.append(_metric(f"{kind}_profit", values["revenue"]-values["cogs"], values["ids"], excluded, mapping, dimensions={kind: dimension}, breakdown={"revenue": round(values["revenue"], 2), "cogs": round(values["cogs"], 2)}, formula="dimension revenue - dimension COGS"))

    budget_rows = [row for row in valid_rows if row["budget"] is not None and (row["actual"] is not None or row["amount"] is not None)]
    if budget_rows:
        budget = round(sum(row["budget"] for row in budget_rows), 2)
        actual = round(sum(row["actual"] if row["actual"] is not None else row["amount"] for row in budget_rows), 2)
        metrics.extend([_metric("budget", budget, [row["id"] for row in budget_rows], excluded, mapping), _metric("actual", actual, [row["id"] for row in budget_rows], excluded, mapping), _metric("budget_variance", actual-budget, [row["id"] for row in budget_rows], excluded, mapping, breakdown={"actual": actual, "budget": budget})])
    else:
        metrics.append(_metric("budget_variance", None, [], excluded, mapping))

    periods: list[dict[str, Any]] = []
    period_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in valid_rows:
        if row["date"]:
            period_rows[row["date"].strftime("%Y-%m")].append(row)
    for period_key, rows in sorted(period_rows.items()):
        year, month = map(int, period_key.split("-"))
        periods.append({"key": period_key, "start_date": date(year, month, 1), "end_date": date(year, month, calendar.monthrange(year, month)[1]), "status": "valid", "row_ids": [row["id"] for row in rows]})
    if len(periods) >= 2:
        previous_rows, current_rows = period_rows[periods[-2]["key"]], period_rows[periods[-1]["key"]]
        for field in ("revenue", "cogs", "operating_expenses"):
            previous_values = [row[field] for row in previous_rows if row[field] is not None]
            current_values = [row[field] for row in current_rows if row[field] is not None]
            if previous_values and current_values:
                previous_value, current_value = sum(previous_values), sum(current_values)
                metrics.append(_metric(f"{field}_period_change", current_value-previous_value, [row["id"] for row in previous_rows+current_rows], excluded, mapping, breakdown={"previous": round(previous_value, 2), "current": round(current_value, 2)}, formula=FORMULAS["period_change"]))
                percent = None if previous_value == 0 else (current_value-previous_value)/abs(previous_value)*100
                metrics.append(_metric(f"{field}_period_change_percent", percent, [row["id"] for row in previous_rows+current_rows], excluded, mapping, breakdown={"previous": round(previous_value, 2), "current": round(current_value, 2)}, formula=FORMULAS["period_change_percent"]))

    forecast: dict[str, Any] = {"horizon_days": 30, "status": "blocked", "opening_cash": closing, "projected_inflow": None, "projected_outflow": None, "projected_closing_cash": None, "shortage_date": None, "inputs": {}, "daily_results": []}
    dated_cash = [row for row in cash_rows if row["date"] is not None]
    if closing is not None and dated_cash:
        start, end = min(row["date"] for row in dated_cash), max(row["date"] for row in dated_cash)
        observed_days = max(1, (end-start).days+1)
        daily_inflow = (inflow or 0)/observed_days
        daily_outflow = (outflow or 0)/observed_days
        daily_results, balance, shortage = [], closing, None
        for offset in range(1, 31):
            balance = round(balance+daily_inflow-daily_outflow, 2)
            forecast_date = effective_as_of + timedelta(days=offset) if effective_as_of else end+timedelta(days=offset)
            daily_results.append({"date": forecast_date.isoformat(), "closing_cash": balance})
            if shortage is None and balance < 0:
                shortage = forecast_date
        forecast.update({"status": "warning", "projected_inflow": round(daily_inflow*30, 2), "projected_outflow": round(daily_outflow*30, 2), "projected_closing_cash": balance, "shortage_date": shortage, "inputs": {"method": "trailing observed daily cash run-rate", "observed_days": observed_days, "source_rows": [row["id"] for row in dated_cash]}, "daily_results": daily_results})
        metrics.append(_metric("forecast_closing_cash", balance, [row["id"] for row in dated_cash]+[item[2] for item in closing_values], excluded, mapping, status="warning", breakdown={"opening_cash": closing, "projected_inflow": round(daily_inflow*30, 2), "projected_outflow": round(daily_outflow*30, 2)}))
    else:
        metrics.append(_metric("forecast_closing_cash", None, [], excluded, mapping))
        validations.append({"code": "forecast_inputs_missing", "status": "blocked", "message": "A closing cash balance and dated cash movements are required for the 30-day forecast.", "row_ids": [], "details": {}})

    if not validations:
        validations.append({"code": "input_checks_passed", "status": "valid", "message": "Required signs, totals, balances and periods passed deterministic checks.", "row_ids": all_ids, "details": {}})
    analysis_records = []
    for row in valid_rows:
        calculated_profit = (
            row["revenue"] - row["cogs"] - row["operating_expenses"]
            if None not in (row["revenue"], row["cogs"], row["operating_expenses"])
            else row["profit"] if row["profit"] is not None
            else row["revenue"] - row["operating_expenses"] if None not in (row["revenue"], row["operating_expenses"])
            else None
        )
        analysis_records.append({"transaction_id": row["id"], "date": row["date"].isoformat() if row["date"] else None, "revenue": row["revenue"], "expenses": row["operating_expenses"], "profit": calculated_profit, "cash": row["closing_cash"]})
    overall = _status(*(item["status"] for item in validations))
    return {"engine_version": ENGINE_VERSION, "status": overall, "as_of": effective_as_of, "mappings": mapping, "periods": periods, "metrics": metrics, "validations": validations, "forecast": forecast, "input_summary": {"record_count": len(records), "included_count": len(valid_rows), "excluded_count": len(excluded), "analysis_records": analysis_records}}
