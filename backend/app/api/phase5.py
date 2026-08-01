import re
import threading
import time
from collections import defaultdict, deque
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models import (CalculatedMetric, CalculationVersion, PilotMetric, ReportSnapshot, ReconciliationRun,
    Upload, User, Workspace, WorkspaceAuditEvent, WorkspaceMember, WorkspaceNote, WorkspacePeriod)

router = APIRouter(prefix="/api/v1/accountant", tags=["accountant-workspace"])
ROLES = {"owner", "accountant", "manager"}
CHECKLIST = ["files_received", "data_cleaned", "reconciliation_reviewed", "trial_balance_validated", "report_delivered"]
_calls: dict[tuple[int, str], deque[float]] = defaultdict(deque)
_lock = threading.Lock()


def model(row: Any) -> dict[str, Any]:
    data = {column.name: getattr(row, column.name) for column in row.__table__.columns}
    for key, value in list(data.items()):
        if hasattr(value, "isoformat"): data[key] = value.isoformat()
    return data


def membership(db: Session, workspace_id: int, user_id: int, allowed: set[str] | None = None) -> tuple[Workspace, WorkspaceMember]:
    row = db.scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user_id, WorkspaceMember.status == "active"))
    workspace = db.get(Workspace, workspace_id)
    if not workspace or not row: raise HTTPException(404, "Workspace not found.")
    if allowed and row.role not in allowed: raise HTTPException(403, "You do not have permission for this action.")
    return workspace, row


def audit(db: Session, workspace_id: int, actor: int, action: str, entity: str, entity_id: int | None, details: dict | None = None, key: str | None = None) -> None:
    db.add(WorkspaceAuditEvent(workspace_id=workspace_id, actor_user_id=actor, action=action, entity_type=entity, entity_id=entity_id, details=details or {}, idempotency_key=key))


def limited(user_id: int, endpoint: str, limit: int = 20) -> None:
    now = time.monotonic(); key = (user_id, endpoint)
    with _lock:
        queue = _calls[key]
        while queue and queue[0] < now - 60: queue.popleft()
        if len(queue) >= limit: raise HTTPException(429, "Rate limit exceeded. Try again shortly.")
        queue.append(now)


@router.get("/pilot/sample-template.csv", response_class=PlainTextResponse)
def pilot_sample_template() -> str:
    return "date,description,revenue,cogs,expenses,cash,currency\n2026-01-31,Example month,0,0,0,0,USD\n"


@router.put("/workspaces/{workspace_id}/pilot/{period}")
def save_pilot_metrics(workspace_id: int, period: str, payload: dict = Body(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    membership(db, workspace_id, user.id, {"owner", "accountant"})
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", period):
        raise HTTPException(422, "period must be YYYY-MM.")
    row = db.scalar(select(PilotMetric).where(PilotMetric.workspace_id == workspace_id, PilotMetric.period == period)) or PilotMetric(workspace_id=workspace_id, period=period)
    integer_fields = {"setup_minutes", "manual_close_minutes", "ledgerly_close_minutes", "matched_count", "possible_count", "unmatched_count", "validation_failures", "corrections_required"}
    boolean_fields = {"report_completed", "repeated_monthly_usage", "testimonial_permission"}
    for key in integer_fields & payload.keys():
        value = payload[key]
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
            raise HTTPException(422, f"{key} must be a non-negative integer or null.")
        setattr(row, key, value)
    for key in boolean_fields & payload.keys():
        if not isinstance(payload[key], bool): raise HTTPException(422, f"{key} must be boolean.")
        setattr(row, key, payload[key])
    if "feedback" in payload:
        feedback = str(payload["feedback"] or "").strip()
        if len(feedback) > 5000: raise HTTPException(422, "feedback must be at most 5000 characters.")
        row.feedback = feedback or None
    if "readiness_checklist" in payload:
        if not isinstance(payload["readiness_checklist"], dict) or not all(isinstance(v, bool) for v in payload["readiness_checklist"].values()): raise HTTPException(422, "readiness_checklist values must be boolean.")
        row.readiness_checklist = payload["readiness_checklist"]
    db.add(row); db.flush(); audit(db, workspace_id, user.id, "pilot.metrics_saved", "pilot_metric", row.id, {"period": period}); db.commit(); db.refresh(row)
    data = model(row); before = row.manual_close_minutes; after = row.ledgerly_close_minutes
    data["time_saved_minutes"] = before - after if before is not None and after is not None else None
    total = row.matched_count + row.possible_count + row.unmatched_count
    data["reconciliation_accuracy_percent"] = round(row.matched_count / total * 100, 2) if total else None
    return data


@router.get("/workspaces/{workspace_id}/pilot")
def pilot_report(workspace_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    workspace, _ = membership(db, workspace_id, user.id)
    rows = db.scalars(select(PilotMetric).where(PilotMetric.workspace_id == workspace_id).order_by(PilotMetric.period)).all()
    periods = []
    for row in rows:
        item = model(row); total = row.matched_count + row.possible_count + row.unmatched_count
        item["time_saved_minutes"] = row.manual_close_minutes - row.ledgerly_close_minutes if row.manual_close_minutes is not None and row.ledgerly_close_minutes is not None else None
        item["reconciliation_accuracy_percent"] = round(row.matched_count / total * 100, 2) if total else None
        periods.append(item)
    return {"workspace_id": workspace.id, "workspace_name": workspace.name, "currency": workspace.currency, "periods": periods, "notice": "Pilot metrics are user-entered or system-counted; Ledgerly does not invent customer outcomes."}


@router.post("/workspaces", status_code=201)
def create_workspace(payload: dict = Body(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    name = str(payload.get("name", "")).strip()
    currency = str(payload.get("currency", "USD")).upper()
    if not 2 <= len(name) <= 160 or not re.fullmatch(r"[A-Z]{3}", currency): raise HTTPException(422, "Valid name and ISO currency are required.")
    row = Workspace(name=name, owner_user_id=user.id, currency=currency, brand=payload.get("brand") or {})
    db.add(row); db.flush(); db.add(WorkspaceMember(workspace_id=row.id, user_id=user.id, role="owner")); audit(db,row.id,user.id,"workspace.created","workspace",row.id)
    db.commit(); db.refresh(row); return model(row)


@router.get("/workspaces")
def list_workspaces(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(select(Workspace, WorkspaceMember).join(WorkspaceMember).where(WorkspaceMember.user_id == user.id, WorkspaceMember.status == "active").order_by(Workspace.name)).all()
    return [{**model(workspace), "role": member.role} for workspace,member in rows]


@router.get("/workspaces/{workspace_id}")
def workspace_detail(workspace_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db))->dict:
    workspace,member=membership(db,workspace_id,user.id); periods=db.scalars(select(WorkspacePeriod).where(WorkspacePeriod.workspace_id==workspace_id).order_by(WorkspacePeriod.period.desc())).all(); files=db.scalars(select(Upload).where(Upload.user_id==workspace.owner_user_id).order_by(Upload.id.desc())).all(); notes=db.scalars(select(WorkspaceNote).where(WorkspaceNote.workspace_id==workspace_id).order_by(WorkspaceNote.id.desc())).all()
    return {**model(workspace),"role":member.role,"files":[model(x) for x in files],"periods":[model(x) for x in periods],"notes":[model(x) for x in notes]}


@router.patch("/workspaces/{workspace_id}/branding")
def branding(workspace_id: int, payload: dict = Body(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    workspace,_ = membership(db,workspace_id,user.id,{"owner","accountant"}); workspace.brand = {key:payload[key] for key in ("business_name","logo_data","brand_color") if key in payload}; audit(db,workspace_id,user.id,"branding.updated","workspace",workspace_id); db.commit(); return model(workspace)


@router.post("/workspaces/{workspace_id}/members", status_code=201)
def invite(workspace_id: int, payload: dict = Body(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    membership(db,workspace_id,user.id,{"owner"}); role = payload.get("role"); target = db.scalar(select(User).where(func.lower(User.email) == str(payload.get("email","")).strip().lower()))
    if role not in ROLES: raise HTTPException(422,"Role must be owner, accountant, or manager.")
    if not target: raise HTTPException(404,"The user must register before being invited.")
    existing = db.scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id==workspace_id,WorkspaceMember.user_id==target.id))
    if existing: existing.role=role; existing.status="active"; row=existing
    else: row=WorkspaceMember(workspace_id=workspace_id,user_id=target.id,role=role); db.add(row)
    db.flush(); audit(db,workspace_id,user.id,"member.invited","member",row.id,{"role":role}); db.commit(); return model(row)


@router.delete("/workspaces/{workspace_id}/members/{member_id}")
def remove_member(workspace_id: int, member_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    workspace,_=membership(db,workspace_id,user.id,{"owner"}); row=db.scalar(select(WorkspaceMember).where(WorkspaceMember.id==member_id,WorkspaceMember.workspace_id==workspace_id))
    if not row: raise HTTPException(404,"Member not found.")
    if row.user_id==workspace.owner_user_id: raise HTTPException(409,"The workspace owner cannot be removed.")
    row.status="removed"; audit(db,workspace_id,user.id,"member.removed","member",row.id); db.commit(); return {"status":"removed"}


@router.post("/workspaces/{workspace_id}/periods", status_code=201)
def create_period(workspace_id: int, payload: dict = Body(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    workspace,_=membership(db,workspace_id,user.id,{"owner","accountant","manager"}); period=str(payload.get("period","")); ids=sorted(set(payload.get("file_ids") or []))
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])",period): raise HTTPException(422,"period must be YYYY-MM.")
    existing=db.scalar(select(WorkspacePeriod).where(WorkspacePeriod.workspace_id==workspace_id,WorkspacePeriod.period==period))
    if existing: return model(existing)
    if ids and len(db.scalars(select(Upload).where(Upload.user_id==workspace.owner_user_id,Upload.id.in_(ids))).all()) != len(ids): raise HTTPException(404,"One or more workspace files were not found.")
    source=None
    if payload.get("reuse_previous"):
        source=db.scalar(select(WorkspacePeriod).where(WorkspacePeriod.workspace_id==workspace_id,WorkspacePeriod.period<period).order_by(WorkspacePeriod.period.desc()))
    items = source.checklist if source else [{"key":key,"status":"pending","approved_by":None,"approved_at":None} for key in CHECKLIST]
    row=WorkspacePeriod(workspace_id=workspace_id,period=period,file_ids=ids,status="reconciliation_pending" if ids else "missing_data",checklist=[{**item,"status":"pending","approved_by":None,"approved_at":None} for item in items],reused_from_period_id=source.id if source else None)
    db.add(row); db.flush(); audit(db,workspace_id,user.id,"period.created","period",row.id,{"period":period,"reused":bool(source)}); db.commit(); return model(row)


@router.patch("/workspaces/{workspace_id}/periods/{period_id}/checklist/{key}")
def update_checklist(workspace_id:int,period_id:int,key:str,payload:dict=Body(...),user:User=Depends(get_current_user),db:Session=Depends(get_db))->dict:
    membership(db,workspace_id,user.id,{"owner","accountant","manager"}); row=db.scalar(select(WorkspacePeriod).where(WorkspacePeriod.id==period_id,WorkspacePeriod.workspace_id==workspace_id))
    if not row or key not in CHECKLIST: raise HTTPException(404,"Checklist item not found.")
    state=payload.get("status");
    if state not in {"pending","submitted","approved","rejected"}: raise HTTPException(422,"Invalid review state.")
    if state in {"approved","rejected"} and membership(db,workspace_id,user.id)[1].role=="manager": raise HTTPException(403,"Managers cannot approve closing work.")
    now=__import__("datetime").datetime.now(__import__("datetime").UTC).isoformat(); row.checklist=[{**item,"status":state,"approved_by":user.id if state=="approved" else None,"approved_at":now if state=="approved" else None} if item["key"]==key else item for item in row.checklist]
    approved={item["key"] for item in row.checklist if item["status"]=="approved"}; row.status="complete" if len(approved)==len(CHECKLIST) else ("report_due" if "trial_balance_validated" in approved else ("reconciliation_pending" if row.file_ids else "missing_data"))
    audit(db,workspace_id,user.id,f"checklist.{state}","period",row.id,{"item":key}); db.commit(); return model(row)


@router.put("/workspaces/{workspace_id}/periods/{period_id}/trial-balance")
def validate_tb(workspace_id:int,period_id:int,payload:dict=Body(...),user:User=Depends(get_current_user),db:Session=Depends(get_db))->dict:
    membership(db,workspace_id,user.id,{"owner","accountant"}); row=db.scalar(select(WorkspacePeriod).where(WorkspacePeriod.id==period_id,WorkspacePeriod.workspace_id==workspace_id)); entries=payload.get("entries")
    if not row or not isinstance(entries,list): raise HTTPException(422,"A valid entries list is required.")
    try: debit=sum(float(x["debit"]) for x in entries); credit=sum(float(x["credit"]) for x in entries)
    except (KeyError,TypeError,ValueError): raise HTTPException(422,"Every entry requires numeric debit and credit values.")
    difference=round(debit-credit,2); result={"debits":debit,"credits":credit,"difference":difference,"status":"valid" if difference==0 else "blocked","entries":entries}; row.trial_balance=result; audit(db,workspace_id,user.id,"trial_balance.validated","period",row.id,{"status":result["status"]}); db.commit(); return result


@router.get("/workspaces/{workspace_id}/periods/{period_id}/suggestions")
def suggestions(workspace_id:int,period_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db))->dict:
    membership(db,workspace_id,user.id); row=db.scalar(select(WorkspacePeriod).where(WorkspacePeriod.id==period_id,WorkspacePeriod.workspace_id==workspace_id))
    if not row: raise HTTPException(404,"Period not found.")
    entries=row.trial_balance.get("entries",[]) if row.trial_balance else []
    categories=[{"account":x.get("account"),"suggested_category":x.get("saved_category"),"source":"saved_rule"} for x in entries if x.get("saved_category")]
    journals=[{"debit_account":x.get("debit_account"),"credit_account":x.get("credit_account"),"amount":x.get("amount"),"source":"saved_rule","status":"suggested"} for x in entries if x.get("saved_rule") and x.get("amount") is not None]
    return {"categories":categories,"journal_entries":journals,"message":None if categories or journals else "No saved rules match this period; no suggestions were generated."}


@router.post("/workspaces/{workspace_id}/notes", status_code=201)
def add_note(workspace_id:int,payload:dict=Body(...),user:User=Depends(get_current_user),db:Session=Depends(get_db))->dict:
    membership(db,workspace_id,user.id); body=str(payload.get("body","")).strip()
    if not body or len(body)>5000: raise HTTPException(422,"Note must contain 1–5000 characters.")
    period_id=payload.get("period_id")
    if period_id and not db.scalar(select(WorkspacePeriod).where(WorkspacePeriod.id==period_id,WorkspacePeriod.workspace_id==workspace_id)): raise HTTPException(404,"Period not found.")
    row=WorkspaceNote(workspace_id=workspace_id,period_id=period_id,author_user_id=user.id,body=body); db.add(row); db.flush(); audit(db,workspace_id,user.id,"note.created","note",row.id); db.commit(); return model(row)


@router.get("/workspaces/{workspace_id}/audit")
def activity(workspace_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db))->list[dict]:
    membership(db,workspace_id,user.id); return [model(x) for x in db.scalars(select(WorkspaceAuditEvent).where(WorkspaceAuditEvent.workspace_id==workspace_id).order_by(WorkspaceAuditEvent.id.desc()).limit(200)).all()]


@router.get("/dashboard")
def dashboard(user:User=Depends(get_current_user),db:Session=Depends(get_db))->dict:
    workspaces=list_workspaces(user,db); ids=[x["id"] for x in workspaces]; periods=db.scalars(select(WorkspacePeriod).where(WorkspacePeriod.workspace_id.in_(ids)).order_by(WorkspacePeriod.period.desc())).all() if ids else []
    counts={key:0 for key in ("complete","missing_data","reconciliation_pending","report_due")}
    for row in periods: counts[row.status]=counts.get(row.status,0)+1
    return {"summary":counts,"clients":workspaces,"periods":[model(x) for x in periods]}


TRANSLATIONS={
 "en":{"missing":"Missing validated data: {metric}.","answer":"{metric}: {value} {currency}."},
 "bn":{"missing":"যাচাইকৃত তথ্য অনুপস্থিত: {metric}।","answer":"{metric}: {value} {currency}।"},
 "ar":{"missing":"البيانات المعتمدة المفقودة: {metric}.","answer":"{metric}: {value} {currency}."},
 "hi":{"missing":"सत्यापित डेटा अनुपलब्ध है: {metric}।","answer":"{metric}: {value} {currency}।"},
 "es":{"missing":"Faltan datos validados: {metric}.","answer":"{metric}: {value} {currency}."}}
METRIC_ALIASES={"revenue":["revenue","sales","রাজস্ব","الإيرادات","राजस्व","ingresos"],"net_profit":["net profit","profit","নিট মুনাফা","صافي الربح","शुद्ध लाभ","beneficio neto"],"closing_cash":["closing cash","cash balance","নগদ","الرصيد النقدي","नकद शेष","saldo de caja"],"expenses":["expenses","ব্যয়","المصروفات","खर्च","gastos"]}


@router.post("/workspaces/{workspace_id}/ai")
def grounded_ai(workspace_id:int,request:Request,payload:dict=Body(...),user:User=Depends(get_current_user),db:Session=Depends(get_db))->dict:
    workspace,member=membership(db,workspace_id,user.id); limited(user.id,"ai")
    question=str(payload.get("question","")).strip(); language=payload.get("language","en")
    if not question or language not in TRANSLATIONS: raise HTTPException(422,"question and a supported language are required.")
    metric=next((key for key,words in METRIC_ALIASES.items() if any(word.lower() in question.lower() for word in words)),None)
    if not metric: return {"answer":TRANSLATIONS[language]["missing"].format(metric="requested metric"),"language":language,"direction":"rtl" if language=="ar" else "ltr","confidence":"none","details":{"missing":["exact supported metric name"],"sources":[]}}
    calc=db.scalar(select(CalculationVersion).where(CalculationVersion.user_id==workspace.owner_user_id).order_by(CalculationVersion.id.desc()))
    value_row=db.scalar(select(CalculatedMetric).where(CalculatedMetric.calculation_id==calc.id,CalculatedMetric.metric_key==metric,CalculatedMetric.status!="blocked",CalculatedMetric.dimensions_key.in_(["","{}"])) ) if calc else None
    if not value_row or value_row.value is None: answer=TRANSLATIONS[language]["missing"].format(metric=metric.replace("_"," ")); missing=[metric]; sources=[]; confidence="none"
    else:
        value=format(value_row.value,",.2f"); answer=TRANSLATIONS[language]["answer"].format(metric=metric.replace("_"," "),value=value,currency=workspace.currency); missing=[]; sources=[f"metric:{value_row.id}"]; confidence="high"
    return {"answer":answer,"language":language,"direction":"rtl" if language=="ar" else "ltr","audience":"simple" if member.role=="owner" else "professional","confidence":confidence,"details":{"collapsed":True,"missing":missing,"sources":sources,"calculation":None}}


@router.post("/workspaces/{workspace_id}/reports/{report_id}/deliver")
def deliver(workspace_id:int,report_id:int,payload:dict=Body(default={}),user:User=Depends(get_current_user),db:Session=Depends(get_db))->dict:
    workspace,_=membership(db,workspace_id,user.id,{"owner","accountant"}); limited(user.id,"report",10); report=db.scalar(select(ReportSnapshot).where(ReportSnapshot.id==report_id,ReportSnapshot.user_id==workspace.owner_user_id))
    if not report: raise HTTPException(404,"Validated workspace report not found.")
    period=db.scalar(select(WorkspacePeriod).where(WorkspacePeriod.workspace_id==workspace_id,WorkspacePeriod.period==report.period));
    if period: period.report_id=report.id; period.status="complete"; audit(db,workspace_id,user.id,"report.delivered","report",report.id,{"channel":payload.get("channel","web")})
    db.commit(); return {"status":"delivered","report_id":report.id,"formats":["web","pdf","xlsx"]}
