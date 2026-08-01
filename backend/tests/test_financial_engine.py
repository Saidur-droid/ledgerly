from datetime import date

import pytest
from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.financial_engine.engine import ENGINE_VERSION, calculate_financials
from app.models import CalculationVersion, MetricEvidence


def metric(result, key, **dimensions):
    return next(item for item in result["metrics"] if item["key"] == key and item["dimensions"] == dimensions)


@pytest.fixture
def complete_records():
    return [
        {"id": "t1", "date": "2026-06-01", "revenue": 1000, "cogs": 400, "operating expenses": 200, "debit": 0, "credit": 1000, "opening cash": 500, "category": "Widgets", "product": "A"},
        {"id": "t2", "date": "2026-06-30", "revenue": 500, "cogs": 150, "operating expenses": 100, "debit": 400, "credit": 0, "closing cash": 1100, "category": "Widgets", "product": "A"},
        {"id": "ar1", "date": "2026-06-10", "due date": "2026-06-20", "receivables": 300, "category": "Receivable"},
        {"id": "ar2", "date": "2026-06-12", "due date": "2026-05-15", "receivables": 200, "category": "Receivable"},
        {"id": "ap1", "date": "2026-06-11", "due date": "2026-04-01", "payables": 250, "category": "Payable"},
        {"id": "b1", "date": "2026-06-01", "budget": 1400, "actual": 1500},
    ]


def test_all_core_formulas_breakdowns_and_product_profitability(complete_records):
    result = calculate_financials(complete_records, as_of=date(2026, 6, 30))
    assert metric(result, "revenue")["value"] == 1500
    assert metric(result, "cogs")["value"] == 550
    assert metric(result, "gross_profit")["value"] == 950
    assert metric(result, "operating_expenses")["value"] == 300
    assert metric(result, "net_profit")["value"] == 650
    assert metric(result, "cash_inflow")["value"] == 1000
    assert metric(result, "cash_outflow")["value"] == 400
    assert metric(result, "opening_cash")["value"] == 500
    assert metric(result, "closing_cash")["value"] == 1100
    assert metric(result, "budget_variance")["value"] == 100
    assert metric(result, "product_profit", product="A")["value"] == 950


def test_aging_overdue_and_missing_due_date_are_not_invented(complete_records):
    complete_records.append({"id": "ar-missing", "date": "2026-06-15", "receivables": 50})
    result = calculate_financials(complete_records, as_of=date(2026, 6, 30))
    assert metric(result, "receivables")["value"] == 550
    assert metric(result, "overdue_receivables")["value"] == 500
    assert metric(result, "receivables_aging_1_30")["value"] == 300
    assert metric(result, "receivables_aging_31_60")["value"] == 200
    assert metric(result, "payables_aging_61_90")["value"] == 250
    assert metric(result, "overdue_receivables")["status"] == "warning"
    assert "ar-missing" in metric(result, "overdue_receivables")["evidence"]["excluded_records"]


def test_period_comparison_and_zero_denominator(complete_records):
    complete_records.insert(0, {"id": "may", "date": "2026-05-31", "revenue": 0, "cogs": 0, "operating expenses": 20})
    result = calculate_financials(complete_records)
    assert metric(result, "revenue_period_change")["value"] == 1500
    assert metric(result, "revenue_period_change_percent")["value"] is None
    assert metric(result, "revenue_period_change_percent")["status"] == "blocked"


def test_validation_blocks_inconsistent_rows_and_flags_balance_variance():
    result = calculate_financials([{"id": "bad", "date": "not-a-date", "debit": 10, "credit": 20, "opening cash": 100, "closing cash": 50}])
    codes = {item["code"] for item in result["validations"]}
    assert {"invalid_period", "debit_credit_both_set", "unbalanced_debits_credits", "missing_period"} <= codes
    assert result["status"] == "blocked"
    assert metric(result, "revenue")["value"] is None


def test_empty_and_partial_inputs_never_create_values():
    empty = calculate_financials([])
    assert empty["status"] == "blocked"
    assert all(item["value"] is None for item in empty["metrics"])
    partial = calculate_financials([{"date": "2026-01-01", "revenue": 10}])
    assert metric(partial, "revenue")["value"] == 10
    assert metric(partial, "gross_profit")["value"] is None
    assert metric(partial, "net_profit")["value"] is None


def test_30_day_forecast_and_shortage_date_are_deterministic():
    result = calculate_financials([
        {"id": "d1", "date": "2026-01-01", "debit": 200, "credit": 0, "closing cash": 100},
        {"id": "d2", "date": "2026-01-10", "debit": 0, "credit": 0},
    ])
    forecast = result["forecast"]
    assert forecast["projected_inflow"] == 0
    assert forecast["projected_outflow"] == 600
    assert forecast["projected_closing_cash"] == -500
    assert forecast["shortage_date"].isoformat() == "2026-01-16"
    assert len(forecast["daily_results"]) == 30


def _register(client, email):
    response = client.post("/api/v1/auth/register", json={"email": email, "full_name": "Engine User", "password": "strong-password"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _upload(client, headers, filename="engine.csv"):
    return client.post("/api/v1/uploads", headers=headers, files={"file": (filename, b"date,revenue,cogs,operating expenses,debit,credit,opening cash,closing cash\n2026-01-01,1000,400,200,0,1000,500,1500\n", "text/csv")})


def test_evidence_is_complete_tenant_isolated_and_recalculation_is_idempotent(client):
    owner = _register(client, "engine-owner@example.com")
    other = _register(client, "engine-other@example.com")
    assert _upload(client, owner).status_code == 201
    latest = client.get("/api/v1/financials/latest", headers=owner)
    assert latest.status_code == 200
    payload = latest.json()
    revenue = next(item for item in payload["metrics"] if item["key"] == "revenue")
    evidence = client.get(f"/api/v1/financials/metrics/{revenue['id']}/evidence", headers=owner)
    assert evidence.status_code == 200
    lineage = evidence.json()["evidence"][0]
    assert lineage["source_file"] == "engine.csv"
    assert lineage["source_location"] == "CSV data"
    assert lineage["included_records"]
    assert lineage["formula"]
    assert lineage["mappings"]
    assert lineage["adjustments"] == []
    assert lineage["calculated_at"]
    assert lineage["engine_version"] == ENGINE_VERSION
    assert client.get(f"/api/v1/financials/metrics/{revenue['id']}/evidence", headers=other).status_code == 404
    upload_id = payload["upload"]["id"]
    first = client.post(f"/api/v1/financials/uploads/{upload_id}/calculate", headers=owner).json()
    second = client.post(f"/api/v1/financials/uploads/{upload_id}/calculate", headers=owner).json()
    assert first["id"] == second["id"] == payload["id"]
    assert client.post(f"/api/v1/financials/uploads/{upload_id}/calculate", headers=other).status_code == 404
    with SessionLocal() as session:
        assert session.scalar(select(func.count()).select_from(CalculationVersion)) == 1
        assert session.scalar(select(func.count()).select_from(MetricEvidence)) > 0
