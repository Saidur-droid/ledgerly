def auth(client, email):
    response=client.post("/api/v1/auth/register",json={"email":email,"full_name":email.split("@")[0],"password":"strong-password"})
    return {"Authorization":f"Bearer {response.json()['access_token']}"}


def workspace(client,headers,name="Client One"):
    return client.post("/api/v1/accountant/workspaces",headers=headers,json={"name":name,"currency":"BDT"}).json()


def upload(client,headers):
    data=b"date,revenue,cogs,operating expenses,debit,credit,opening cash,closing cash,receivables,due date,category,product\n2026-06-01,1000,400,100,0,1000,500,1500,,,Sales,A\n2026-06-30,500,100,50,300,0,,1200,200,2026-05-01,Expense,A\n"
    client.post("/api/v1/uploads",headers=headers,files={"file":("month.csv",data,"text/csv")})
    return client.get("/api/v1/uploads",headers=headers).json()[0]["id"]


def test_multi_client_isolation_roles_and_audit(client):
    owner=auth(client,"owner.phase5@example.com"); accountant=auth(client,"accountant.phase5@example.com"); outsider=auth(client,"outside.phase5@example.com")
    one=workspace(client,owner); two=workspace(client,outsider,"Other Client")
    invited=client.post(f"/api/v1/accountant/workspaces/{one['id']}/members",headers=owner,json={"email":"accountant.phase5@example.com","role":"accountant"})
    assert invited.status_code==201
    assert client.get(f"/api/v1/accountant/workspaces/{one['id']}/audit",headers=accountant).status_code==200
    assert client.get(f"/api/v1/accountant/workspaces/{two['id']}/audit",headers=accountant).status_code==404
    assert client.post(f"/api/v1/accountant/workspaces/{one['id']}/members",headers=accountant,json={"email":"outside.phase5@example.com","role":"manager"}).status_code==403
    actions={x["action"] for x in client.get(f"/api/v1/accountant/workspaces/{one['id']}/audit",headers=owner).json()}
    assert {"workspace.created","member.invited"}<=actions


def test_checklist_approval_reuse_and_trial_balance(client):
    owner=auth(client,"close.phase5@example.com"); manager=auth(client,"manager.phase5@example.com"); ws=workspace(client,owner); file_id=upload(client,owner)
    client.post(f"/api/v1/accountant/workspaces/{ws['id']}/members",headers=owner,json={"email":"manager.phase5@example.com","role":"manager"})
    period=client.post(f"/api/v1/accountant/workspaces/{ws['id']}/periods",headers=owner,json={"period":"2026-07","file_ids":[file_id]}).json()
    assert client.patch(f"/api/v1/accountant/workspaces/{ws['id']}/periods/{period['id']}/checklist/files_received",headers=manager,json={"status":"approved"}).status_code==403
    assert client.patch(f"/api/v1/accountant/workspaces/{ws['id']}/periods/{period['id']}/checklist/files_received",headers=owner,json={"status":"approved"}).json()["checklist"][0]["approved_by"]
    invalid=client.put(f"/api/v1/accountant/workspaces/{ws['id']}/periods/{period['id']}/trial-balance",headers=owner,json={"entries":[{"debit":100,"credit":99}]})
    assert invalid.json()["status"]=="blocked" and invalid.json()["difference"]==1
    valid=client.put(f"/api/v1/accountant/workspaces/{ws['id']}/periods/{period['id']}/trial-balance",headers=owner,json={"entries":[{"debit":100,"credit":100}]})
    assert valid.json()["status"]=="valid"
    august=client.post(f"/api/v1/accountant/workspaces/{ws['id']}/periods",headers=owner,json={"period":"2026-08","reuse_previous":True}).json()
    assert august["reused_from_period_id"]==period["id"] and all(x["status"]=="pending" for x in august["checklist"])


def test_grounded_multilingual_exact_answers_missing_data_and_rate_limit(client):
    owner=auth(client,"ai.phase5@example.com"); ws=workspace(client,owner); upload(client,owner)
    english=client.post(f"/api/v1/accountant/workspaces/{ws['id']}/ai",headers=owner,json={"question":"What is revenue?","language":"en"}).json()
    assert english["confidence"]=="high" and "1,500.00 BDT" in english["answer"] and english["details"]["collapsed"]
    arabic=client.post(f"/api/v1/accountant/workspaces/{ws['id']}/ai",headers=owner,json={"question":"ما هي الإيرادات؟","language":"ar"}).json()
    assert arabic["language"]=="ar" and arabic["direction"]=="rtl" and "1,500.00" in arabic["answer"]
    missing=client.post(f"/api/v1/accountant/workspaces/{ws['id']}/ai",headers=owner,json={"question":"What is EBITDA?","language":"en"}).json()
    assert missing["confidence"]=="none" and missing["details"]["missing"]==["exact supported metric name"]
    statuses=[client.post(f"/api/v1/accountant/workspaces/{ws['id']}/ai",headers=owner,json={"question":"revenue?","language":"en"}).status_code for _ in range(20)]
    assert 429 in statuses


def test_dashboard_notes_and_cross_workspace_file_security(client):
    owner=auth(client,"dash.phase5@example.com"); other=auth(client,"dash-other.phase5@example.com"); ws=workspace(client,owner); foreign=upload(client,other)
    assert client.post(f"/api/v1/accountant/workspaces/{ws['id']}/periods",headers=owner,json={"period":"2026-07","file_ids":[foreign]}).status_code==404
    period=client.post(f"/api/v1/accountant/workspaces/{ws['id']}/periods",headers=owner,json={"period":"2026-07"}).json()
    assert client.post(f"/api/v1/accountant/workspaces/{ws['id']}/notes",headers=owner,json={"period_id":period["id"],"body":"Client confirmed opening balance."}).status_code==201
    dashboard=client.get("/api/v1/accountant/dashboard",headers=owner).json()
    assert dashboard["summary"]["missing_data"]==1 and dashboard["clients"][0]["role"]=="owner"


def test_pilot_metrics_are_isolated_validated_and_calculated(client):
    owner=auth(client,"pilot-owner@example.com"); outsider=auth(client,"pilot-outsider@example.com"); ws=workspace(client,owner)
    payload={"setup_minutes":45,"manual_close_minutes":300,"ledgerly_close_minutes":90,"matched_count":90,"possible_count":5,"unmatched_count":5,"validation_failures":2,"corrections_required":3,"report_completed":True,"repeated_monthly_usage":False,"feedback":"Useful review workflow.","testimonial_permission":False,"readiness_checklist":{"bank_statement":True,"ledger_export":True}}
    saved=client.put(f"/api/v1/accountant/workspaces/{ws['id']}/pilot/2026-07",headers=owner,json=payload)
    assert saved.status_code==200
    assert saved.json()["time_saved_minutes"]==210
    assert saved.json()["reconciliation_accuracy_percent"]==90.0
    assert client.get(f"/api/v1/accountant/workspaces/{ws['id']}/pilot",headers=outsider).status_code==404
    assert client.put(f"/api/v1/accountant/workspaces/{ws['id']}/pilot/2026-07",headers=owner,json={"matched_count":-1}).status_code==422
    report=client.get(f"/api/v1/accountant/workspaces/{ws['id']}/pilot",headers=owner).json()
    assert report["periods"][0]["feedback"]=="Useful review workflow."
    assert "does not invent" in report["notice"]


def test_sample_template_is_downloadable_and_contains_no_fake_results(client):
    response=client.get("/api/v1/accountant/pilot/sample-template.csv")
    assert response.status_code==200
    assert response.text.startswith("date,description,revenue,cogs,expenses,cash,currency")
    assert "Example month,0,0,0,0,USD" in response.text
