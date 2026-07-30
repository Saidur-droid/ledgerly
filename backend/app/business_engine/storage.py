from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Pulse, Upload


@dataclass(frozen=True)
class StoredUpload:
    id: int
    user_id: int
    filename: str
    file_type: str
    checksum: str
    row_count: int
    confidence: float
    normalized_data: dict[str, Any]
    created_at: datetime


@dataclass(frozen=True)
class StoredPulse:
    upload_id: int
    score: int
    confidence: float
    summary: str
    factors: list[dict[str, Any]]
    metrics: dict[str, float]


def _upload_from_model(upload: Upload) -> StoredUpload:
    return StoredUpload(
        id=upload.id,
        user_id=upload.user_id,
        filename=upload.filename,
        file_type=upload.file_type,
        checksum=upload.checksum,
        row_count=upload.row_count,
        confidence=upload.confidence,
        normalized_data=upload.normalized_data,
        created_at=upload.created_at,
    )


def _pulse_from_model(pulse: Pulse) -> StoredPulse:
    return StoredPulse(
        upload_id=pulse.upload_id,
        score=pulse.score,
        confidence=pulse.confidence,
        summary=pulse.summary,
        factors=pulse.factors,
        metrics=pulse.metrics,
    )


class BusinessStore:
    """PostgreSQL-backed persistence for uploaded business data and Pulse history."""

    def __init__(self, session: Session):
        self.session = session
        self._pending_metrics: dict[int, dict[str, float]] = {}

    def create_upload(
        self,
        *,
        user_id: int,
        filename: str,
        file_type: str,
        checksum: str,
        row_count: int,
        confidence: float,
        normalized_data: dict[str, Any],
        metrics: dict[str, float],
    ) -> StoredUpload:
        upload = Upload(
            user_id=user_id,
            filename=filename,
            file_type=file_type,
            checksum=checksum,
            row_count=row_count,
            confidence=confidence,
            normalized_data=normalized_data,
        )
        self.session.add(upload)
        self.session.flush()
        self._pending_metrics[upload.id] = metrics
        return _upload_from_model(upload)

    def get_metrics(self, *, user_id: int, upload_id: int) -> dict[str, float]:
        if upload_id in self._pending_metrics:
            return self._pending_metrics[upload_id]
        pulse = self.session.scalar(
            select(Pulse)
            .join(Upload)
            .where(Upload.user_id == user_id, Pulse.upload_id == upload_id)
        )
        return pulse.metrics if pulse else {}

    def save_pulse(self, *, user_id: int, pulse: StoredPulse) -> None:
        upload_exists = self.session.scalar(
            select(Upload.id).where(
                Upload.id == pulse.upload_id,
                Upload.user_id == user_id,
            )
        )
        if upload_exists is None:
            raise ValueError("Cannot save a Pulse for another user's upload.")
        self.session.add(
            Pulse(
                upload_id=pulse.upload_id,
                score=pulse.score,
                confidence=pulse.confidence,
                summary=pulse.summary,
                factors=pulse.factors,
                metrics=pulse.metrics,
            )
        )
        self.session.commit()
        self._pending_metrics.pop(pulse.upload_id, None)

    def list_uploads(self, *, user_id: int) -> list[StoredUpload]:
        uploads = self.session.scalars(
            select(Upload)
            .where(Upload.user_id == user_id)
            .order_by(Upload.created_at.desc())
        ).all()
        return [_upload_from_model(upload) for upload in uploads]

    def latest_context(
        self,
        *,
        user_id: int,
    ) -> tuple[StoredUpload, StoredPulse] | None:
        upload = self.session.scalar(
            select(Upload)
            .where(Upload.user_id == user_id)
            .order_by(Upload.created_at.desc())
        )
        if upload is None or upload.pulse is None:
            return None
        return _upload_from_model(upload), _pulse_from_model(upload.pulse)

    def previous_pulse(
        self,
        *,
        user_id: int,
        upload_id: int,
    ) -> StoredPulse | None:
        upload = self.session.scalar(
            select(Upload)
            .where(Upload.user_id == user_id, Upload.id != upload_id)
            .order_by(Upload.created_at.desc())
        )
        return _pulse_from_model(upload.pulse) if upload and upload.pulse else None

    def rollback(self) -> None:
        self.session.rollback()


def get_business_store(db: Session = Depends(get_db)) -> BusinessStore:
    return BusinessStore(db)
