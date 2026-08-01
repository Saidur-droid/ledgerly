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
