import hashlib
from io import BytesIO

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.service import DISCLAIMER, answer_business_question
from app.business_engine.parser import parse_business_file
from app.business_pulse.engine import calculate_pulse, compare_metrics
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import create_access_token, get_current_user, hash_password, verify_password
from app.models import Pulse, Upload, User
from app.report_engine.pdf import build_pulse_report
from app.schemas import ChatRequest, ChatResponse, PulseRead, Token, UploadRead, UserCreate, UserRead

router = APIRouter(prefix="/api/v1")


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


@router.post("/uploads", response_model=PulseRead, status_code=status.HTTP_201_CREATED)
async def upload_business_data(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PulseRead:
    content = await file.read()
    limit = get_settings().max_upload_mb * 1024 * 1024
    if len(content) > limit:
        raise HTTPException(status_code=413, detail="File is larger than the configured upload limit.")
    try:
        parsed = parse_business_file(file.filename or "upload", content)
    except (ValueError, TypeError) as error:
        raise HTTPException(status_code=400, detail=str(error))

    previous = db.scalar(select(Upload).where(Upload.user_id == user.id).order_by(Upload.created_at.desc()))
    pulse_result = calculate_pulse(parsed.metrics, parsed.confidence)
    upload = Upload(
        user_id=user.id,
        filename=file.filename or "upload",
        file_type=(file.filename or "").rsplit(".", 1)[-1].lower(),
        checksum=hashlib.sha256(content).hexdigest(),
        row_count=len(parsed.records),
        confidence=parsed.confidence,
        normalized_data={"columns": parsed.columns, "records": parsed.records, "warnings": parsed.warnings},
    )
    db.add(upload)
    db.flush()
    pulse = Pulse(
        upload_id=upload.id,
        score=pulse_result.score,
        confidence=pulse_result.confidence,
        summary=pulse_result.summary,
        factors=pulse_result.factors,
        metrics=pulse_result.metrics,
    )
    db.add(pulse)
    db.commit()
    return PulseRead(
        score=pulse.score,
        confidence=pulse.confidence,
        summary=pulse.summary,
        factors=pulse.factors,
        metrics=pulse.metrics,
        comparison=compare_metrics(pulse.metrics, previous.pulse.metrics if previous and previous.pulse else None),
    )


@router.get("/uploads", response_model=list[UploadRead])
def list_uploads(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[Upload]:
    return list(db.scalars(select(Upload).where(Upload.user_id == user.id).order_by(Upload.created_at.desc())).all())


def latest_pulse(user_id: int, db: Session) -> tuple[Upload, Pulse]:
    upload = db.scalar(select(Upload).where(Upload.user_id == user_id).order_by(Upload.created_at.desc()))
    if upload is None or upload.pulse is None:
        raise HTTPException(status_code=404, detail="Upload business data first.")
    return upload, upload.pulse


@router.get("/pulse/latest", response_model=PulseRead)
def read_latest_pulse(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> PulseRead:
    upload, pulse = latest_pulse(user.id, db)
    previous = db.scalar(
        select(Upload).where(Upload.user_id == user.id, Upload.id != upload.id).order_by(Upload.created_at.desc())
    )
    return PulseRead(
        score=pulse.score,
        confidence=pulse.confidence,
        summary=pulse.summary,
        factors=pulse.factors,
        metrics=pulse.metrics,
        comparison=compare_metrics(pulse.metrics, previous.pulse.metrics if previous and previous.pulse else None),
    )


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ChatResponse:
    upload, pulse = latest_pulse(user.id, db)
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
def report(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> StreamingResponse:
    _, pulse = latest_pulse(user.id, db)
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
