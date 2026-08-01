def register(client, email="owner@example.com"):
    response = client.post("/api/v1/auth/register", json={"email": email, "full_name": "Test Owner", "password": "secure-pass-123"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def upload(client, headers, filename, content):
    response = client.post("/api/v1/uploads", headers=headers, files={"file": (filename, content, "text/csv")})
    assert response.status_code == 201, response.text


def test_data_inbox_detects_mapping_and_preserves_cleaning_audit(client):
    headers = register(client)
    upload(client, headers, "bank-july.csv", "Date,Amount,Reference\n2026-07-01,$100.00,A-1\n2026-07-01,$100.00,A-1\nbad,$25.00,A-2\n")
    upload_id = client.get("/api/v1/uploads", headers=headers).json()[0]["id"]

    detail = client.get(f"/api/v1/data-inbox/{upload_id}", headers=headers)
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["profile"]["role"] == "bank_statement"
    assert payload["profile"]["column_mapping"]["date"] == "Date"
    assert {issue["issue_type"] for issue in payload["issues"]} >= {"duplicate_row", "bad_date", "number_as_text"}

    issue = next(item for item in payload["issues"] if item["issue_type"] == "number_as_text")
    reviewed = client.patch(f"/api/v1/data-inbox/{upload_id}/issues/{issue['id']}", headers=headers, json={"status": "approved", "final_value": issue["suggested_value"]})
    assert reviewed.status_code == 200
    assert reviewed.json()["original_value"] == "$100.00"
    assert reviewed.json()["final_value"] == 100.0


def test_exact_reconciliation_is_explainable_and_tenant_isolated(client):
    headers = register(client)
    upload(client, headers, "bank.csv", "Date,Amount,Reference\n2026-07-01,100,A-1\n2026-07-02,75,A-2\n")
    bank_id = client.get("/api/v1/uploads", headers=headers).json()[0]["id"]
    upload(client, headers, "ledger.csv", "Date,Amount,Reference\n2026-07-01,100,A-1\n2026-07-03,20,L-3\n")
    ledger_id = client.get("/api/v1/uploads", headers=headers).json()[0]["id"]

    result = client.post("/api/v1/reconciliations", headers=headers, json={"bank_upload_id": bank_id, "ledger_upload_id": ledger_id})
    assert result.status_code == 201, result.text
    payload = result.json()
    exact = next(match for match in payload["matches"] if match["match_type"] == "exact")
    assert exact["score"] == 1.0
    assert exact["rule"] == "same date + amount + reference"
    assert payload["completion_percent"] == 50.0

    other_headers = register(client, "other@example.com")
    assert client.get(f"/api/v1/reconciliations/{payload['id']}", headers=other_headers).status_code == 404


def test_manual_match_notes_audit_and_idempotency(client):
    headers = register(client)
    upload(client, headers, "bank.csv", "Date,Amount,Description\n2026-07-01,100,Customer deposit\n")
    bank_id = client.get("/api/v1/uploads", headers=headers).json()[0]["id"]
    upload(client, headers, "ledger.csv", "Date,Amount,Description\n2026-07-02,100,Receipt\n")
    ledger_id = client.get("/api/v1/uploads", headers=headers).json()[0]["id"]
    run = client.post("/api/v1/reconciliations", headers=headers, json={"bank_upload_id": bank_id, "ledger_upload_id": ledger_id}).json()
    bank_match = next(item for item in run["matches"] if item["bank_row"])
    ledger_match = next(item for item in run["matches"] if item["ledger_row"])
    body = {"bank_row": bank_match["bank_row"], "ledger_row": ledger_match["ledger_row"], "note": "Verified receipt", "idempotency_key": "manual-1"}
    first = client.post(f"/api/v1/reconciliations/{run['id']}/matches", headers=headers, json=body)
    second = client.post(f"/api/v1/reconciliations/{run['id']}/matches", headers=headers, json=body)
    assert first.status_code == second.status_code == 200
    payload = second.json()
    assert sum(item["match_type"] == "manual" for item in payload["matches"]) == 1
    manual = next(item for item in payload["matches"] if item["match_type"] == "manual")
    assert manual["review_note"] == "Verified receipt"
    assert manual["final_state"]["bank_row"] == bank_match["bank_row"]
    assert any(event["action"] == "manual_match" for event in payload["audit_history"])


def test_exception_balance_completion_and_read_only_reopen(client):
    headers = register(client)
    upload(client, headers, "bank.csv", "Date,Amount,Reference,Description\n2026-07-01,5,FEE-1,Bank service fee\n")
    bank_id = client.get("/api/v1/uploads", headers=headers).json()[0]["id"]
    upload(client, headers, "ledger.csv", "Date,Amount,Reference,Description\n2026-07-01,5,FEE-1,Bank service fee\n")
    ledger_id = client.get("/api/v1/uploads", headers=headers).json()[0]["id"]
    run = client.post("/api/v1/reconciliations", headers=headers, json={"bank_upload_id": bank_id, "ledger_upload_id": ledger_id}).json()
    client.post(f"/api/v1/reconciliations/{run['id']}/bulk-approve-exact", headers=headers, json={"idempotency_key": "bulk-1"})
    balanced = client.put(f"/api/v1/reconciliations/{run['id']}/balance", headers=headers, json={"opening_balance": 0, "closing_balance": 5})
    assert balanced.json()["balance"]["passed"] is True
    completed = client.post(f"/api/v1/reconciliations/{run['id']}/complete", headers=headers, json={"note": "Reviewed"})
    assert completed.status_code == 200
    match_id = completed.json()["matches"][0]["id"]
    assert client.patch(f"/api/v1/reconciliations/{run['id']}/matches/{match_id}", headers=headers, json={"status": "rejected"}).status_code == 409
    reopened = client.post(f"/api/v1/reconciliations/{run['id']}/reopen", headers=headers, json={"note": "Correction"})
    assert reopened.json()["status"] == "review"
    assert [event["action"] for event in reopened.json()["audit_history"]][:2] == ["reopened", "completed"]


def test_possible_exception_language_and_cross_tenant_actions(client):
    headers = register(client)
    upload(client, headers, "bank.csv", "Date,Amount,Description\n2026-07-01,12,Bank fee\n")
    bank_id = client.get("/api/v1/uploads", headers=headers).json()[0]["id"]
    upload(client, headers, "ledger.csv", "Date,Amount,Description\n2026-07-03,99,Other\n")
    ledger_id = client.get("/api/v1/uploads", headers=headers).json()[0]["id"]
    run = client.post("/api/v1/reconciliations", headers=headers, json={"bank_upload_id": bank_id, "ledger_upload_id": ledger_id}).json()
    exception = next(item for item in run["matches"] if item["bank_row"])
    assert exception["exception_type"] == "bank_fee"
    assert exception["exception_status"] == "pending"
    other = register(client, "intruder@example.com")
    assert client.post(f"/api/v1/reconciliations/{run['id']}/bulk-approve-exact", headers=other, json={}).status_code == 404
