import hashlib
import re
from io import BytesIO

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.service import DISCLAIMER, answer_business_question
from app.business_engine.parser import parse_business_file
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
from app.models import User
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
)

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
        store.save_pulse(user_id=user.id, pulse=pulse)
    except Exception as error:
        store.rollback()
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


@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    user: User = Depends(get_current_user),
    store: BusinessStore = Depends(get_business_store),
) -> ChatResponse:
    upload, pulse = latest_pulse(user.id, store)
    context = {
        "filename": upload.filename,
        "uploaded_at": upload.created_at,
        "metrics": pulse.metrics,
        "pulse_score": pulse.score,
        "factors": pulse.factors,
        "data": upload.normalized_data,
    }
    answer, confidence = answer_business_question(payload.question, context)
    return ChatResponse(answer=answer, confidence=confidence, sources=[upload.filename], disclaimer=DISCLAIMER)


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
