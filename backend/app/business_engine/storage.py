import json
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
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


class BusinessStore(Protocol):
    backend_name: str

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
    ) -> StoredUpload: ...

    def get_metrics(self, *, user_id: int, upload_id: int) -> dict[str, float]: ...

    def save_pulse(self, *, user_id: int, pulse: StoredPulse) -> None: ...

    def list_uploads(self, *, user_id: int) -> list[StoredUpload]: ...

    def latest_context(self, *, user_id: int) -> tuple[StoredUpload, StoredPulse] | None: ...

    def previous_pulse(self, *, user_id: int, upload_id: int) -> StoredPulse | None: ...

    def rollback(self) -> None: ...

    def close(self) -> None: ...


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


class SqlAlchemyBusinessStore:
    """Compatibility path used until Snowflake credentials are configured."""

    backend_name = "database"

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

    def latest_context(self, *, user_id: int) -> tuple[StoredUpload, StoredPulse] | None:
        upload = self.session.scalar(
            select(Upload)
            .where(Upload.user_id == user_id)
            .order_by(Upload.created_at.desc())
        )
        if upload is None or upload.pulse is None:
            return None
        return _upload_from_model(upload), _pulse_from_model(upload.pulse)

    def previous_pulse(self, *, user_id: int, upload_id: int) -> StoredPulse | None:
        upload = self.session.scalar(
            select(Upload)
            .where(Upload.user_id == user_id, Upload.id != upload_id)
            .order_by(Upload.created_at.desc())
        )
        return _pulse_from_model(upload.pulse) if upload and upload.pulse else None

    def rollback(self) -> None:
        self.session.rollback()

    def close(self) -> None:
        pass


def _json_value(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


class SnowflakeBusinessStore:
    backend_name = "snowflake"

    def __init__(self, settings: Settings):
        import snowflake.connector

        connection_options: dict[str, Any] = {
            "account": settings.snowflake_account,
            "user": settings.snowflake_user,
            "password": settings.snowflake_password,
            "warehouse": settings.snowflake_warehouse,
            "database": settings.snowflake_database,
            "schema": settings.snowflake_schema,
            "application": "Ledgerly",
            "autocommit": False,
            "session_parameters": {"QUERY_TAG": "ledgerly_business_pipeline"},
        }
        if settings.snowflake_role:
            connection_options["role"] = settings.snowflake_role
        self.connection = snowflake.connector.connect(**connection_options)

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
        cursor = self.connection.cursor()
        try:
            cursor.execute("SELECT LEDGERLY_UPLOAD_SEQUENCE.NEXTVAL")
            upload_id = int(cursor.fetchone()[0])
            cursor.execute(
                """
                INSERT INTO UPLOADS (
                    UPLOAD_ID, USER_ID, FILENAME, FILE_TYPE, CHECKSUM,
                    ROW_COUNT, CONFIDENCE, NORMALIZED_DATA
                )
                SELECT %s, %s, %s, %s, %s, %s, %s, PARSE_JSON(%s)
                """,
                (
                    upload_id,
                    user_id,
                    filename,
                    file_type,
                    checksum,
                    row_count,
                    confidence,
                    json.dumps(normalized_data, default=str),
                ),
            )
            if metrics:
                cursor.executemany(
                    """
                    INSERT INTO BUSINESS_METRICS (
                        UPLOAD_ID, USER_ID, METRIC_NAME, METRIC_VALUE
                    ) VALUES (%s, %s, %s, %s)
                    """,
                    [
                        (upload_id, user_id, name, value)
                        for name, value in metrics.items()
                    ],
                )
            cursor.execute(
                """
                SELECT UPLOAD_ID, USER_ID, FILENAME, FILE_TYPE, CHECKSUM,
                       ROW_COUNT, CONFIDENCE, NORMALIZED_DATA, CREATED_AT
                FROM UPLOADS
                WHERE USER_ID = %s AND UPLOAD_ID = %s
                """,
                (user_id, upload_id),
            )
            return self._upload_from_row(cursor.fetchone())
        finally:
            cursor.close()

    def get_metrics(self, *, user_id: int, upload_id: int) -> dict[str, float]:
        cursor = self.connection.cursor()
        try:
            cursor.execute(
                """
                SELECT METRIC_NAME, METRIC_VALUE
                FROM BUSINESS_METRICS
                WHERE USER_ID = %s AND UPLOAD_ID = %s
                ORDER BY METRIC_NAME
                """,
                (user_id, upload_id),
            )
            return {str(name): float(value) for name, value in cursor.fetchall()}
        finally:
            cursor.close()

    def save_pulse(self, *, user_id: int, pulse: StoredPulse) -> None:
        cursor = self.connection.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO PULSE_HISTORY (
                    PULSE_ID, UPLOAD_ID, USER_ID, SCORE, CONFIDENCE,
                    SUMMARY, FACTORS, METRICS
                )
                SELECT %s, %s, %s, %s, %s, %s, PARSE_JSON(%s), PARSE_JSON(%s)
                """,
                (
                    str(uuid.uuid4()),
                    pulse.upload_id,
                    user_id,
                    pulse.score,
                    pulse.confidence,
                    pulse.summary,
                    json.dumps(pulse.factors),
                    json.dumps(pulse.metrics),
                ),
            )
            self.connection.commit()
        finally:
            cursor.close()

    def list_uploads(self, *, user_id: int) -> list[StoredUpload]:
        cursor = self.connection.cursor()
        try:
            cursor.execute(
                """
                SELECT UPLOAD_ID, USER_ID, FILENAME, FILE_TYPE, CHECKSUM,
                       ROW_COUNT, CONFIDENCE, NORMALIZED_DATA, CREATED_AT
                FROM UPLOADS
                WHERE USER_ID = %s
                ORDER BY CREATED_AT DESC
                """,
                (user_id,),
            )
            return [self._upload_from_row(row) for row in cursor.fetchall()]
        finally:
            cursor.close()

    def latest_context(self, *, user_id: int) -> tuple[StoredUpload, StoredPulse] | None:
        cursor = self.connection.cursor()
        try:
            cursor.execute(
                """
                SELECT
                    U.UPLOAD_ID, U.USER_ID, U.FILENAME, U.FILE_TYPE, U.CHECKSUM,
                    U.ROW_COUNT, U.CONFIDENCE, U.NORMALIZED_DATA, U.CREATED_AT,
                    P.SCORE, P.CONFIDENCE, P.SUMMARY, P.FACTORS, P.METRICS
                FROM UPLOADS U
                JOIN PULSE_HISTORY P ON P.UPLOAD_ID = U.UPLOAD_ID
                WHERE U.USER_ID = %s AND P.USER_ID = %s
                ORDER BY U.CREATED_AT DESC, P.CREATED_AT DESC
                LIMIT 1
                """,
                (user_id, user_id),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            upload = self._upload_from_row(row[:9])
            pulse = StoredPulse(
                upload_id=upload.id,
                score=int(row[9]),
                confidence=float(row[10]),
                summary=str(row[11]),
                factors=_json_value(row[12]),
                metrics=_json_value(row[13]),
            )
            return upload, pulse
        finally:
            cursor.close()

    def previous_pulse(self, *, user_id: int, upload_id: int) -> StoredPulse | None:
        cursor = self.connection.cursor()
        try:
            cursor.execute(
                """
                SELECT P.UPLOAD_ID, P.SCORE, P.CONFIDENCE, P.SUMMARY, P.FACTORS, P.METRICS
                FROM PULSE_HISTORY P
                JOIN UPLOADS U ON U.UPLOAD_ID = P.UPLOAD_ID
                WHERE U.USER_ID = %s AND P.USER_ID = %s AND U.UPLOAD_ID != %s
                ORDER BY U.CREATED_AT DESC, P.CREATED_AT DESC
                LIMIT 1
                """,
                (user_id, user_id, upload_id),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return StoredPulse(
                upload_id=int(row[0]),
                score=int(row[1]),
                confidence=float(row[2]),
                summary=str(row[3]),
                factors=_json_value(row[4]),
                metrics=_json_value(row[5]),
            )
        finally:
            cursor.close()

    def rollback(self) -> None:
        self.connection.rollback()

    def close(self) -> None:
        self.connection.close()

    @staticmethod
    def _upload_from_row(row: tuple[Any, ...]) -> StoredUpload:
        return StoredUpload(
            id=int(row[0]),
            user_id=int(row[1]),
            filename=str(row[2]),
            file_type=str(row[3]),
            checksum=str(row[4]),
            row_count=int(row[5]),
            confidence=float(row[6]),
            normalized_data=_json_value(row[7]),
            created_at=row[8],
        )


def get_business_store(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Iterator[BusinessStore]:
    store: BusinessStore
    if settings.snowflake_configured:
        store = SnowflakeBusinessStore(settings)
    else:
        store = SqlAlchemyBusinessStore(db)
    try:
        yield store
    finally:
        store.close()
