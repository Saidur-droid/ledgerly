from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import ReportShare


def auth(client, email="owner@example.com"):
    response = client.post("/api/v1/auth/register", json={"email": email, "full_name": "Owner", "password": "strong-password"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def upload(client, headers, filename="month.csv"):
    data = b"date,revenue,cogs,operating expenses,debit,credit,opening cash,closing cash,receivables,due date,category,product\n2026-06-01,1000,400,100,0,1000,500,1500,,,Sales,A\n2026-06-30,500,100,50,300,0,,1200,200,2026-05-01,Expense,A\n"
    return client.post("/api/v1/uploads", headers=headers, files={"file": (filename, data, "text/csv")})


def test_dashboard_uses_persisted_metrics_alerts_and_lineage(client):
    headers = auth(client); upload(client, headers)
    dashboard = client.get("/api/v1/dashboard", headers=headers).json()
    keys = {m["key"] for m in dashboard["metrics"]}
    assert {"revenue", "gross_profit", "net_profit", "gross_margin", "net_margin", "closing_cash", "receivables", "payables"} <= keys
    assert all(item["evidence_url"] for item in dashboard["metrics"])
    overdue = next(item for item in dashboard["attention"] if item["type"] == "overdue_invoices")
    assert client.get(overdue["evidence_url"], headers=headers).status_code == 200


def test_saved_rules_period_changes_idempotency_and_blocking(client):
    headers = auth(client); upload(client, headers); upload_id = client.get("/api/v1/uploads", headers=headers).json()[0]["id"]
    saved = client.put("/api/v1/closing/settings", headers=headers, json={"customer_aliases": {"ACME Ltd": "ACME"}, "bank_rules": [{"contains": "fee", "category": "Bank fees"}], "fiscal_period": {"year_start": 1}})
    assert saved.json()["customer_aliases"]["ACME Ltd"] == "ACME"
    body = {"period": "2026-06", "upload_ids": [upload_id], "idempotency_key": "close-june"}
    first = client.post("/api/v1/closing/runs", headers=headers, json=body)
    second = client.post("/api/v1/closing/runs", headers=headers, json=body)
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["rules_snapshot"]["bank_rules"]
    july = client.post("/api/v1/closing/runs", headers=headers, json={**body, "period": "2026-07", "idempotency_key": "close-july"})
    assert july.json()["id"] != first.json()["id"]
    assert client.post(f"/api/v1/closing/runs/{first.json()['id']}/reopen", headers=headers).json()["audit_log"][-1]["action"] == "reopened"
    client.post("/api/v1/uploads", headers=headers, files={"file": ("bad.csv", b"foo\nbar\n", "text/csv")})
    bad = client.get("/api/v1/uploads", headers=headers).json()[0]["id"]
    blocked = client.post("/api/v1/closing/runs", headers=headers, json={"period": "2026-08", "upload_ids": [bad], "idempotency_key": "bad"}).json()
    assert blocked["status"] == "blocked" and blocked["completed_at"] is None


def test_templates_multilingual_exports_and_secure_shares(client):
    owner = auth(client); other = auth(client, "other@example.com"); upload(client, owner)
    calc = client.get("/api/v1/financials/latest", headers=owner).json()
    template = client.post("/api/v1/report-templates", headers=owner, json={"title": "تقرير شهري", "business_name": "Ledgerly", "language": "ar", "brand_color": "#6043D2", "selected_kpis": ["revenue", "net_profit"]}).json()
    assert client.get("/api/v1/report-templates", headers=owner).json()[0]["language"] == "ar"
    assert client.get("/api/v1/report-templates", headers=other).json() == []
    report = client.post("/api/v1/reports", headers=owner, json={"template_id": template["id"], "calculation_id": calc["id"], "period": "2026-06"}).json()
    assert report["direction"] == "rtl" and all("evidence_ref" in m for m in report["metrics"])
    pdf = client.get(f"/api/v1/reports/{report['id']}.pdf", headers=owner)
    xlsx = client.get(f"/api/v1/reports/{report['id']}.xlsx", headers=owner)
    assert pdf.content.startswith(b"%PDF") and xlsx.content.startswith(b"PK")
    assert client.get(f"/api/v1/reports/{report['id']}.pdf", headers=other).status_code == 404
    share = client.post(f"/api/v1/reports/{report['id']}/shares", headers=owner, json={"expires_in_hours": 2}).json()
    public = client.get(share["url"])
    assert public.status_code == 200 and 'dir="rtl"' in public.text and "date,revenue" not in public.text
    assert client.delete(f"/api/v1/reports/shares/{share['id']}", headers=other).status_code == 404
    assert client.delete(f"/api/v1/reports/shares/{share['id']}", headers=owner).status_code == 200
    assert client.get(share["url"]).status_code == 404
    second = client.post(f"/api/v1/reports/{report['id']}/shares", headers=owner, json={}).json()
    with SessionLocal() as db:
        row = db.scalar(select(ReportShare).where(ReportShare.id == second["id"]))
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1); db.commit()
    assert client.get(second["url"]).status_code == 404
