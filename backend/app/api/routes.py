import hashlib
import logging
import re
from collections import Counter
from uuid import uuid4
from io import BytesIO

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.service import answer_business_question
from app.ai.contract import serialize_ask_response
from app.business_engine.parser import parse_business_file
from app.business_engine.data_inbox import canonical_transactions, detect_profile, exact_matches, find_cleaning_issues
from app.business_engine.storage import (
    BusinessStore,
    StoredPulse,
    StoredUpload,
    get_business_store,
)
from app.business_pulse.engine import calculate_pulse, compare_metrics
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import create_access_token, get_current_user, hash_password, verify_password
from app.financial_engine.service import calculate_upload, calculation_payload, latest_calculation_payload
from app.models import CalculatedMetric, CalculationVersion, CleaningIssue, DataSourceProfile, MetricEvidence, ReconciliationAuditEvent, ReconciliationMatch, ReconciliationRun, SourceMapping, Upload, User, utcnow
from app.report_engine.pdf import build_pulse_report
from app.schemas import (
    ChatRequest,
    ChatResponse,
    PulseRead,
    SettingsRead,
    Token,
    UploadRead,
    UserCreate,
    UserRead,
    UserUpdate,
    CleaningDecision,
    MappingUpdate,
    MatchDecision,
    ManualMatchCreate,
    ReconciliationAction,
    BalanceUpdate,
    ReconciliationCreate,
)

LOGGER = logging.getLogger("ledgerly.upload")

router = APIRouter(prefix="/api/v1")
SAFE_FILENAME_SEPARATOR = re.compile(r"[/\\]+")


@router.post("/auth/register", response_model=Token, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> Token:
    if db.scalar(select(User).where(User.email == payload.email.lower())):
        raise HTTPException(status_code=409, detail="An account already exists for this email.")
    user = User(email=payload.email.lower(), full_name=payload.full_name.strip(), password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return Token(access_token=create_access_token(user.id), user=UserRead.model_validate(user))


@router.post("/auth/login", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)) -> Token:
    user = db.scalar(select(User).where(User.email == form.username.lower()))
    if user is None or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    return Token(access_token=create_access_token(user.id), user=UserRead.model_validate(user))


@router.get("/me", response_model=UserRead)
def read_me(user: User = Depends(get_current_user)) -> User:
    return user


@router.get("/settings", response_model=SettingsRead)
def read_settings(user: User = Depends(get_current_user)) -> SettingsRead:
    return SettingsRead(profile=UserRead.model_validate(user))


@router.patch("/settings/profile", response_model=UserRead)
def update_profile(
    payload: UserUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    if payload.email is not None:
        email = payload.email.lower()
        existing_user = db.scalar(
            select(User).where(User.email == email, User.id != user.id)
        )
        if existing_user is not None:
            raise HTTPException(
                status_code=409,
                detail="An account already exists for this email.",
            )
        user.email = email
    if payload.full_name is not None:
        user.full_name = payload.full_name.strip()
    db.commit()
    db.refresh(user)
    return user


@router.post("/uploads", response_model=PulseRead, status_code=status.HTTP_201_CREATED)
async def upload_business_data(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    store: BusinessStore = Depends(get_business_store),
    db: Session = Depends(get_db),
) -> PulseRead:
    filename = SAFE_FILENAME_SEPARATOR.split(file.filename or "upload")[-1]
    if not filename or len(filename) > 255:
        raise HTTPException(
            status_code=400,
            detail="The file name must be between 1 and 255 characters.",
        )
    limit = get_settings().max_upload_mb * 1024 * 1024
    content = await file.read(limit + 1)
    if len(content) > limit:
        raise HTTPException(
            status_code=413,
            detail=(
                f"The file exceeds the {get_settings().max_upload_mb} MB "
                "upload limit."
            ),
        )
    try:
        parsed = parse_business_file(filename, content)
    except (ValueError, TypeError) as error:
        raise HTTPException(status_code=400, detail=str(error))

    try:
        upload = store.create_upload(
            user_id=user.id,
            filename=filename,
            file_type=filename.rsplit(".", 1)[-1].lower(),
            checksum=hashlib.sha256(content).hexdigest(),
            row_count=len(parsed.records),
            confidence=parsed.confidence,
            normalized_data={
                "columns": parsed.columns,
                "records": parsed.records,
                "warnings": parsed.warnings,
                "metadata": parsed.metadata,
            },
            metrics=parsed.metrics,
        )
        upload_model = db.get(Upload, upload.id)
        if upload_model is None:
            raise RuntimeError("Upload was not persisted.")
        profile_data = detect_profile(filename, parsed.records, parsed.columns)
        source_key = filename.rsplit(".", 1)[0].strip().lower()
        saved_mapping = db.scalar(select(SourceMapping).where(SourceMapping.user_id == user.id, SourceMapping.source_key == source_key))
        if saved_mapping is not None:
            profile_data["column_mapping"] = saved_mapping.column_mapping
            profile_data["mapping_approved"] = True
        profile = DataSourceProfile(upload_id=upload.id, **profile_data)
        db.add(profile)
        for issue in find_cleaning_issues(parsed.records, profile_data["column_mapping"]):
            db.add(CleaningIssue(upload_id=upload.id, **issue))
        stored_metrics = store.get_metrics(user_id=user.id, upload_id=upload.id)
        previous = store.previous_pulse(user_id=user.id, upload_id=upload.id)
        pulse_result = calculate_pulse(stored_metrics, upload.confidence)
        pulse = StoredPulse(
            upload_id=upload.id,
            score=pulse_result.score,
            confidence=pulse_result.confidence,
            summary=pulse_result.summary,
            factors=pulse_result.factors,
            metrics=pulse_result.metrics,
        )
        calculate_upload(db, user_id=user.id, upload_id=upload.id)
        store.save_pulse(user_id=user.id, pulse=pulse)
    except Exception as error:
        store.rollback()
        # Never include the exception message: database errors may contain SQL
        # parameters derived from private financial rows.
        LOGGER.error("upload_storage_failed stage=persist_and_calculate error_type=%s", type(error).__name__)
        raise HTTPException(
            status_code=503,
            detail="Business data storage is temporarily unavailable.",
        ) from error
    return PulseRead(
        score=pulse.score,
        confidence=pulse.confidence,
        summary=pulse.summary,
        factors=pulse.factors,
        metrics=pulse.metrics,
        comparison=compare_metrics(pulse.metrics, previous.metrics if previous else None),
    )


def _owned_upload(db: Session, user_id: int, upload_id: int) -> Upload:
    upload = db.scalar(select(Upload).where(Upload.id == upload_id, Upload.user_id == user_id))
    if upload is None:
        raise HTTPException(status_code=404, detail="Upload not found.")
    return upload


def _model_values(model) -> dict:
    return {column.name: getattr(model, column.name) for column in model.__table__.columns}


@router.get("/data-inbox/{upload_id}")
def data_inbox_detail(upload_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    upload = _owned_upload(db, user.id, upload_id)
    profile = db.scalar(select(DataSourceProfile).where(DataSourceProfile.upload_id == upload.id))
    issues = db.scalars(select(CleaningIssue).where(CleaningIssue.upload_id == upload.id).order_by(CleaningIssue.row_number, CleaningIssue.id)).all()
    return {"upload": UploadRead.model_validate(upload).model_dump(), "profile": _model_values(profile) if profile else None, "issues": [_model_values(issue) for issue in issues], "summary": {"total": len(issues), "pending": sum(issue.status == "pending" for issue in issues), "errors": sum(issue.severity == "error" for issue in issues)}}


@router.put("/data-inbox/{upload_id}/mapping")
def update_mapping(upload_id: int, payload: MappingUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    upload = _owned_upload(db, user.id, upload_id)
    columns = set(upload.normalized_data.get("columns", []))
    if not set(payload.column_mapping.values()) <= columns:
        raise HTTPException(status_code=400, detail="Every mapped column must exist in the source file.")
    profile = db.scalar(select(DataSourceProfile).where(DataSourceProfile.upload_id == upload.id))
    if profile is None:
        raise HTTPException(status_code=404, detail="Data profile not found.")
    profile.role, profile.period, profile.currency = payload.role, payload.period, payload.currency.upper() if payload.currency else None
    profile.column_mapping, profile.mapping_approved = payload.column_mapping, True
    source_key = upload.filename.rsplit(".", 1)[0].strip().lower()
    saved = db.scalar(select(SourceMapping).where(SourceMapping.user_id == user.id, SourceMapping.source_key == source_key))
    if saved is None:
        db.add(SourceMapping(user_id=user.id, source_key=source_key, column_mapping=payload.column_mapping))
    else:
        saved.column_mapping, saved.updated_at = payload.column_mapping, utcnow()
    db.commit()
    return {"status": "approved", "column_mapping": profile.column_mapping}


@router.patch("/data-inbox/{upload_id}/issues/{issue_id}")
def review_issue(upload_id: int, issue_id: int, payload: CleaningDecision, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    _owned_upload(db, user.id, upload_id)
    issue = db.scalar(select(CleaningIssue).where(CleaningIssue.id == issue_id, CleaningIssue.upload_id == upload_id))
    if issue is None:
        raise HTTPException(status_code=404, detail="Cleaning issue not found.")
    issue.status, issue.reviewed_at = payload.status, utcnow()
    issue.final_value = payload.final_value if payload.status == "approved" else issue.original_value
    db.commit()
    return {"id": issue.id, "status": issue.status, "final_value": issue.final_value, "original_value": issue.original_value}


@router.post("/reconciliations", status_code=status.HTTP_201_CREATED)
def create_reconciliation(payload: ReconciliationCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    bank = _owned_upload(db, user.id, payload.bank_upload_id)
    ledger = _owned_upload(db, user.id, payload.ledger_upload_id)
    if bank.id == ledger.id:
        raise HTTPException(status_code=400, detail="Choose two different uploads.")
    profiles = {p.upload_id: p for p in db.scalars(select(DataSourceProfile).where(DataSourceProfile.upload_id.in_([bank.id, ledger.id]))).all()}
    if any(upload_id not in profiles for upload_id in (bank.id, ledger.id)):
        raise HTTPException(status_code=400, detail="Both uploads require a data profile.")
    run = ReconciliationRun(user_id=user.id, bank_upload_id=bank.id, ledger_upload_id=ledger.id)
    db.add(run); db.flush()
    bank_tx = canonical_transactions(bank.normalized_data.get("records", []), profiles[bank.id].column_mapping)
    ledger_tx = canonical_transactions(ledger.normalized_data.get("records", []), profiles[ledger.id].column_mapping)
    for result in exact_matches(bank_tx, ledger_tx):
        db.add(ReconciliationMatch(run_id=run.id, **result))
    db.add(ReconciliationAuditEvent(run_id=run.id, actor_user_id=user.id, action="created", details={"bank_upload_id": bank.id, "ledger_upload_id": ledger.id}))
    db.commit()
    return reconciliation_detail(run.id, user, db)


@router.get("/reconciliations/{run_id}")
def reconciliation_detail(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    run = db.scalar(select(ReconciliationRun).where(ReconciliationRun.id == run_id, ReconciliationRun.user_id == user.id))
    if run is None:
        raise HTTPException(status_code=404, detail="Reconciliation not found.")
    matches = db.scalars(select(ReconciliationMatch).where(ReconciliationMatch.run_id == run.id).order_by(ReconciliationMatch.id)).all()
    exact = sum(match.match_type == "exact" for match in matches)
    bank_rows = {match.bank_row for match in matches if match.bank_row is not None}
    approved = sum(match.status in {"approved", "manual"} for match in matches)
    resolved = sum(match.bank_row is not None and (match.status in {"approved", "manual", "rejected"} or match.match_type == "exact") for match in matches)
    pending_exceptions = sum(bool(match.exception_type) and match.exception_status == "pending" for match in matches)
    ledger_values: dict[int, float] = {}
    for match in matches:
        ledger = match.evidence.get("ledger") or {}
        if match.ledger_row is not None and ledger:
            ledger_values.setdefault(match.ledger_row, float(ledger.get("signed_amount") or 0))
    ledger_movement = round(sum(ledger_values.values()), 2)
    statement_movement = None if run.opening_balance is None or run.closing_balance is None else round(run.closing_balance - run.opening_balance, 2)
    variance = None if statement_movement is None else round(statement_movement - ledger_movement, 2)
    counts = dict(Counter(match.match_type for match in matches))
    counts.update({"exceptions": sum(bool(m.exception_type) for m in matches), "approved": approved})
    events = db.scalars(select(ReconciliationAuditEvent).where(ReconciliationAuditEvent.run_id == run.id).order_by(ReconciliationAuditEvent.id.desc())).all()
    return {"id": run.id, "status": run.status, "bank_upload_id": run.bank_upload_id, "ledger_upload_id": run.ledger_upload_id, "completion_percent": round(min(resolved, len(bank_rows)) / len(bank_rows) * 100, 1) if bank_rows else 100.0, "counts": counts, "balance": {"opening_balance": run.opening_balance, "closing_balance": run.closing_balance, "calculated_movement": ledger_movement, "statement_movement": statement_movement, "variance": variance, "passed": variance == 0 if variance is not None else False}, "checklist": {"all_items_reviewed": all(m.status in {"approved", "manual", "rejected"} for m in matches), "exceptions_resolved": pending_exceptions == 0, "balances_validated": variance == 0 if variance is not None else False}, "matches": [_model_values(match) for match in matches], "audit_history": [_model_values(event) for event in events]}


@router.get("/reconciliations")
def list_reconciliations(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    runs = db.scalars(select(ReconciliationRun).where(ReconciliationRun.user_id == user.id).order_by(ReconciliationRun.id.desc())).all()
    return [{"id": run.id, "status": run.status, "bank_upload_id": run.bank_upload_id, "ledger_upload_id": run.ledger_upload_id, "created_at": run.created_at} for run in runs]


@router.patch("/reconciliations/{run_id}/matches/{match_id}")
def review_match(run_id: int, match_id: int, payload: MatchDecision, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    run = _owned_run(db, user.id, run_id)
    _ensure_editable(run)
    match = db.scalar(select(ReconciliationMatch).where(ReconciliationMatch.id == match_id, ReconciliationMatch.run_id == run.id))
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found.")
    if _idempotent(db, run.id, user.id, payload.idempotency_key):
        return {"id": match.id, "status": match.status}
    before = _model_values(match)
    match.status, match.review_note, match.reviewed_at = payload.status, payload.note, utcnow()
    match.exception_status = "resolved" if match.exception_type and payload.status in {"approved", "rejected"} else match.exception_status
    match.final_state = {"bank_row": match.bank_row, "ledger_row": match.ledger_row, "status": match.status}
    _audit(db, run, user, "match_reviewed", match, {"before": before, "after": match.final_state, "note": payload.note}, payload.idempotency_key)
    db.commit()
    return {"id": match.id, "status": match.status}


@router.post("/reconciliations/{run_id}/matches")
def manual_match(run_id: int, payload: ManualMatchCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    run = _owned_run(db, user.id, run_id); _ensure_editable(run)
    existing = _idempotent(db, run.id, user.id, payload.idempotency_key)
    if existing:
        return reconciliation_detail(run.id, user, db)
    matches = db.scalars(select(ReconciliationMatch).where(ReconciliationMatch.run_id == run.id)).all()
    bank = next((m for m in matches if m.bank_row == payload.bank_row), None)
    ledger = next((m for m in matches if m.ledger_row == payload.ledger_row), None)
    if bank is None or ledger is None:
        raise HTTPException(status_code=400, detail="Both source rows must exist in this reconciliation.")
    if any(m.status in {"approved", "manual"} and (m.bank_row == payload.bank_row or m.ledger_row == payload.ledger_row) for m in matches):
        raise HTTPException(status_code=409, detail="One of these rows already has an approved match. Unmatch it first.")
    evidence = {"bank": bank.evidence.get("bank"), "ledger": ledger.evidence.get("ledger"), "manual": True}
    state = {"bank_row": payload.bank_row, "ledger_row": payload.ledger_row, "match_type": "manual"}
    created = ReconciliationMatch(run_id=run.id, bank_row=payload.bank_row, ledger_row=payload.ledger_row, match_type="manual", score=1, rule="manually matched by reviewer", amount=(evidence.get("bank") or {}).get("amount"), transaction_date=(evidence.get("bank") or {}).get("date"), status="manual", evidence=evidence, review_note=payload.note, original_state={}, suggested_state={}, final_state=state, reviewed_at=utcnow())
    bank.status = "rejected"; bank.exception_status = "resolved"
    if ledger.id != bank.id: ledger.status = "rejected"; ledger.exception_status = "resolved"
    db.add(created); db.flush(); _audit(db, run, user, "manual_match", created, state | {"note": payload.note}, payload.idempotency_key); db.commit()
    return reconciliation_detail(run.id, user, db)


@router.post("/reconciliations/{run_id}/matches/{match_id}/unmatch")
def unmatch(run_id: int, match_id: int, payload: ReconciliationAction, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    run = _owned_run(db, user.id, run_id); _ensure_editable(run)
    match = db.scalar(select(ReconciliationMatch).where(ReconciliationMatch.id == match_id, ReconciliationMatch.run_id == run.id))
    if match is None: raise HTTPException(status_code=404, detail="Match not found.")
    if not _idempotent(db, run.id, user.id, payload.idempotency_key):
        match.status, match.final_state, match.review_note, match.reviewed_at = "rejected", {"unmatched": True}, payload.note, utcnow()
        _audit(db, run, user, "unmatched", match, {"note": payload.note}, payload.idempotency_key); db.commit()
    return reconciliation_detail(run.id, user, db)


@router.post("/reconciliations/{run_id}/bulk-approve-exact")
def bulk_approve_exact(run_id: int, payload: ReconciliationAction, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    run = _owned_run(db, user.id, run_id); _ensure_editable(run)
    if not _idempotent(db, run.id, user.id, payload.idempotency_key):
        matches = db.scalars(select(ReconciliationMatch).where(ReconciliationMatch.run_id == run.id, ReconciliationMatch.match_type == "exact", ReconciliationMatch.status == "pending", ReconciliationMatch.score >= .95)).all()
        for match in matches: match.status, match.final_state, match.reviewed_at = "approved", match.suggested_state, utcnow()
        _audit(db, run, user, "bulk_approved_exact", None, {"count": len(matches)}, payload.idempotency_key); db.commit()
    return reconciliation_detail(run.id, user, db)


@router.put("/reconciliations/{run_id}/balance")
def update_balance(run_id: int, payload: BalanceUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    run = _owned_run(db, user.id, run_id); _ensure_editable(run)
    run.opening_balance, run.closing_balance = payload.opening_balance, payload.closing_balance
    _audit(db, run, user, "balance_updated", None, payload.model_dump(), None); db.commit()
    return reconciliation_detail(run.id, user, db)


@router.post("/reconciliations/{run_id}/complete")
def complete_reconciliation(run_id: int, payload: ReconciliationAction, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    run = _owned_run(db, user.id, run_id); _ensure_editable(run)
    detail = reconciliation_detail(run.id, user, db)
    failed = [name for name, passed in detail["checklist"].items() if not passed]
    if failed: raise HTTPException(status_code=409, detail=f"Cannot complete: {', '.join(failed).replace('_', ' ')}.")
    run.status, run.completed_at = "completed", utcnow(); _audit(db, run, user, "completed", None, {"note": payload.note}, payload.idempotency_key); db.commit()
    return reconciliation_detail(run.id, user, db)


@router.post("/reconciliations/{run_id}/reopen")
def reopen_reconciliation(run_id: int, payload: ReconciliationAction, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    run = _owned_run(db, user.id, run_id)
    if run.status != "completed": raise HTTPException(status_code=409, detail="Only completed reconciliations can be reopened.")
    if not _idempotent(db, run.id, user.id, payload.idempotency_key):
        run.status, run.completed_at = "review", None; _audit(db, run, user, "reopened", None, {"note": payload.note}, payload.idempotency_key); db.commit()
    return reconciliation_detail(run.id, user, db)


def _owned_run(db: Session, user_id: int, run_id: int) -> ReconciliationRun:
    run = db.scalar(select(ReconciliationRun).where(ReconciliationRun.id == run_id, ReconciliationRun.user_id == user_id))
    if run is None: raise HTTPException(status_code=404, detail="Reconciliation not found.")
    return run


def _ensure_editable(run: ReconciliationRun) -> None:
    if run.status == "completed": raise HTTPException(status_code=409, detail="Completed reconciliations are read-only. Reopen this run to make changes.")


def _idempotent(db: Session, run_id: int, user_id: int, key: str | None) -> ReconciliationAuditEvent | None:
    return None if not key else db.scalar(select(ReconciliationAuditEvent).where(ReconciliationAuditEvent.run_id == run_id, ReconciliationAuditEvent.actor_user_id == user_id, ReconciliationAuditEvent.idempotency_key == key))


def _audit(db: Session, run: ReconciliationRun, user: User, action: str, match: ReconciliationMatch | None, details: dict, key: str | None) -> None:
    db.add(ReconciliationAuditEvent(run_id=run.id, match_id=match.id if match else None, actor_user_id=user.id, action=action, details=details, idempotency_key=key))


@router.get("/uploads", response_model=list[UploadRead])
def list_uploads(
    user: User = Depends(get_current_user),
    store: BusinessStore = Depends(get_business_store),
) -> list[StoredUpload]:
    return store.list_uploads(user_id=user.id)


def latest_pulse(user_id: int, store: BusinessStore) -> tuple[StoredUpload, StoredPulse]:
    context = store.latest_context(user_id=user_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Upload business data first.")
    return context


@router.get("/pulse/latest", response_model=PulseRead)
def read_latest_pulse(
    user: User = Depends(get_current_user),
    store: BusinessStore = Depends(get_business_store),
) -> PulseRead:
    upload, pulse = latest_pulse(user.id, store)
    previous = store.previous_pulse(
        user_id=user.id,
        upload_id=upload.id,
    )
    return PulseRead(
        score=pulse.score,
        confidence=pulse.confidence,
        summary=pulse.summary,
        factors=pulse.factors,
        metrics=pulse.metrics,
        comparison=compare_metrics(pulse.metrics, previous.metrics if previous else None),
    )


@router.post("/financials/uploads/{upload_id}/calculate")
def recalculate_financials(
    upload_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    try:
        calculation = calculate_upload(db, user_id=user.id, upload_id=upload_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    db.commit()
    return calculation_payload(db, calculation, include_evidence=False)


@router.get("/financials/latest")
def read_latest_financials(
    include_evidence: bool = Query(default=False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    payload = latest_calculation_payload(db, user_id=user.id, include_evidence=include_evidence)
    if payload is None:
        raise HTTPException(status_code=404, detail="Upload business data first.")
    return payload


@router.get("/financials/metrics/{metric_id}/evidence")
def read_metric_evidence(
    metric_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    metric = db.scalar(
        select(CalculatedMetric)
        .join(CalculationVersion, CalculationVersion.id == CalculatedMetric.calculation_id)
        .where(CalculatedMetric.id == metric_id, CalculationVersion.user_id == user.id)
    )
    if metric is None:
        raise HTTPException(status_code=404, detail="Metric not found.")
    evidence = db.scalars(select(MetricEvidence).where(MetricEvidence.metric_id == metric.id)).all()
    return {
        "metric": {"id": metric.id, "key": metric.metric_key, "value": metric.value, "status": metric.status, "breakdown": metric.breakdown},
        "evidence": [{"id": row.id, "source_file": row.source_file, "source_location": row.source_location, "included_records": row.included_records, "excluded_records": row.excluded_records, "formula": row.formula, "mappings": row.mappings, "adjustments": row.adjustments, "calculated_at": row.calculated_at.isoformat(), "engine_version": row.engine_version} for row in evidence],
    }
@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    user: User = Depends(get_current_user),
    store: BusinessStore = Depends(get_business_store),
    db: Session = Depends(get_db),
) -> ChatResponse:
    upload, pulse = latest_pulse(user.id, store)
    financials = latest_calculation_payload(db, user_id=user.id, include_evidence=False)
    calculated = {
        item["key"]: item["value"]
        for item in (financials or {}).get("metrics", [])
        if item["value"] is not None and not item["dimensions"]
    }
    engine_metrics = {
        "revenue": calculated.get("revenue"),
        "expenses": calculated.get("operating_expenses"),
        "profit": calculated.get("net_profit") or calculated.get("reported_profit"),
        "cash": calculated.get("closing_cash"),
    }
    context = {
        "filename": upload.filename,
        "uploaded_at": upload.created_at,
        "metrics": {key: value for key, value in engine_metrics.items() if value is not None},
        "pulse_score": pulse.score,
        "factors": pulse.factors,
        "data": {
            "records": (financials or {}).get("input_summary", {}).get("analysis_records", []),
            "metadata": {**upload.normalized_data.get("metadata", {}), "calculation_version": (financials or {}).get("engine_version")},
        },
    }
    result = answer_business_question(payload.question, context)
    if isinstance(result.answer, dict) and financials:
        sections = result.answer.get("sections")
        section_types = {
            section.get("type") for section in sections or []
            if isinstance(section, dict)
        }
        if {"table", "forecast", "actions"} <= section_types and "text" not in section_types:
            sections.append({
                "type": "text",
                "heading": "Calculation provenance",
                "markdown": (
                    "All financial values in this analysis come from the "
                    f"persisted deterministic calculation **{financials['engine_version']}**; "
                    "Ask Ledgerly only explains those results."
                ),
            })
    return serialize_ask_response(
        result.answer,
        correlation_id=uuid4().hex,
        policy_notice=result.policy_notice,
    )


@router.get("/reports/latest.pdf")
def report(
    user: User = Depends(get_current_user),
    store: BusinessStore = Depends(get_business_store),
) -> StreamingResponse:
    _, pulse = latest_pulse(user.id, store)
    content = build_pulse_report(user.full_name, {
        "score": pulse.score,
        "summary": pulse.summary,
        "metrics": pulse.metrics,
    })
    return StreamingResponse(
        BytesIO(content),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="ledgerly-report.pdf"'},
    )
