from datetime import UTC, date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    uploads: Mapped[list["Upload"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Upload(Base):
    __tablename__ = "uploads"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(255))
    file_type: Mapped[str] = mapped_column(String(20))
    checksum: Mapped[str] = mapped_column(String(64), index=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=0)
    normalized_data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    user: Mapped[User] = relationship(back_populates="uploads")
    pulse: Mapped["Pulse | None"] = relationship(back_populates="upload", cascade="all, delete-orphan")
    profile: Mapped["DataSourceProfile | None"] = relationship(back_populates="upload", cascade="all, delete-orphan")
    cleaning_issues: Mapped[list["CleaningIssue"]] = relationship(back_populates="upload", cascade="all, delete-orphan")


class Pulse(Base):
    __tablename__ = "pulses"

    id: Mapped[int] = mapped_column(primary_key=True)
    upload_id: Mapped[int] = mapped_column(
        ForeignKey("uploads.id", ondelete="CASCADE"),
        unique=True,
    )
    score: Mapped[int] = mapped_column(Integer)
    confidence: Mapped[float] = mapped_column(Float)
    summary: Mapped[str] = mapped_column(Text)
    factors: Mapped[list] = mapped_column(JSON, default=list)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    upload: Mapped[Upload] = relationship(back_populates="pulse")


class SourceMapping(Base):
    __tablename__ = "source_mappings"
    __table_args__ = (UniqueConstraint("user_id", "source_key", name="uq_source_mapping_user_source"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    source_key: Mapped[str] = mapped_column(String(255))
    column_mapping: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class DataSourceProfile(Base):
    __tablename__ = "data_source_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    upload_id: Mapped[int] = mapped_column(ForeignKey("uploads.id", ondelete="CASCADE"), unique=True)
    role: Mapped[str] = mapped_column(String(40), default="unknown")
    period: Mapped[str | None] = mapped_column(String(40), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    column_mapping: Mapped[dict] = mapped_column(JSON, default=dict)
    mapping_confidence: Mapped[float] = mapped_column(Float, default=0)
    mapping_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    upload: Mapped[Upload] = relationship(back_populates="profile")


class CleaningIssue(Base):
    __tablename__ = "cleaning_issues"

    id: Mapped[int] = mapped_column(primary_key=True)
    upload_id: Mapped[int] = mapped_column(ForeignKey("uploads.id", ondelete="CASCADE"), index=True)
    row_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    column_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    issue_type: Mapped[str] = mapped_column(String(40), index=True)
    severity: Mapped[str] = mapped_column(String(12), default="warning")
    original_value: Mapped[object | None] = mapped_column(JSON, nullable=True)
    suggested_value: Mapped[object | None] = mapped_column(JSON, nullable=True)
    final_value: Mapped[object | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="pending", index=True)
    explanation: Mapped[str] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    upload: Mapped[Upload] = relationship(back_populates="cleaning_issues")


class ReconciliationRun(Base):
    __tablename__ = "reconciliation_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    bank_upload_id: Mapped[int] = mapped_column(ForeignKey("uploads.id", ondelete="CASCADE"))
    ledger_upload_id: Mapped[int] = mapped_column(ForeignKey("uploads.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(20), default="review")
    opening_balance: Mapped[float | None] = mapped_column(Float, nullable=True)
    closing_balance: Mapped[float | None] = mapped_column(Float, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    matches: Mapped[list["ReconciliationMatch"]] = relationship(cascade="all, delete-orphan")
    audit_events: Mapped[list["ReconciliationAuditEvent"]] = relationship(cascade="all, delete-orphan")


class ReconciliationMatch(Base):
    __tablename__ = "reconciliation_matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("reconciliation_runs.id", ondelete="CASCADE"), index=True)
    bank_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ledger_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    match_type: Mapped[str] = mapped_column(String(20), index=True)
    score: Mapped[float] = mapped_column(Float)
    rule: Mapped[str] = mapped_column(String(120))
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    transaction_date: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    exception_type: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    exception_status: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_state: Mapped[dict] = mapped_column(JSON, default=dict)
    suggested_state: Mapped[dict] = mapped_column(JSON, default=dict)
    final_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReconciliationAuditEvent(Base):
    __tablename__ = "reconciliation_audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("reconciliation_runs.id", ondelete="CASCADE"), index=True)
    match_id: Mapped[int | None] = mapped_column(ForeignKey("reconciliation_matches.id", ondelete="SET NULL"), nullable=True, index=True)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(40), index=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    idempotency_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CalculationVersion(Base):
    __tablename__ = "calculation_versions"
    __table_args__ = (
        UniqueConstraint("user_id", "fingerprint", name="uq_calculation_user_fingerprint"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    upload_id: Mapped[int] = mapped_column(ForeignKey("uploads.id", ondelete="CASCADE"), index=True)
    engine_version: Mapped[str] = mapped_column(String(40))
    fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(12), index=True)
    input_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    periods: Mapped[list["FinancialPeriod"]] = relationship(cascade="all, delete-orphan")
    metrics: Mapped[list["CalculatedMetric"]] = relationship(cascade="all, delete-orphan")
    validations: Mapped[list["ValidationResult"]] = relationship(cascade="all, delete-orphan")
    forecasts: Mapped[list["ForecastResult"]] = relationship(cascade="all, delete-orphan")


class FinancialPeriod(Base):
    __tablename__ = "financial_periods"
    __table_args__ = (UniqueConstraint("calculation_id", "period_key", name="uq_financial_period_calculation_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    calculation_id: Mapped[int] = mapped_column(ForeignKey("calculation_versions.id", ondelete="CASCADE"), index=True)
    period_key: Mapped[str] = mapped_column(String(20))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    status: Mapped[str] = mapped_column(String(12))


class CalculatedMetric(Base):
    __tablename__ = "calculated_metrics"
    __table_args__ = (UniqueConstraint("calculation_id", "metric_key", "dimensions_key", name="uq_calculated_metric_identity"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    calculation_id: Mapped[int] = mapped_column(ForeignKey("calculation_versions.id", ondelete="CASCADE"), index=True)
    period_id: Mapped[int | None] = mapped_column(ForeignKey("financial_periods.id", ondelete="CASCADE"), nullable=True, index=True)
    metric_key: Mapped[str] = mapped_column(String(80), index=True)
    dimensions_key: Mapped[str] = mapped_column(String(255), default="")
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str] = mapped_column(String(20), default="currency")
    status: Mapped[str] = mapped_column(String(12), index=True)
    breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence: Mapped[list["MetricEvidence"]] = relationship(cascade="all, delete-orphan")


class MetricEvidence(Base):
    __tablename__ = "metric_evidence"

    id: Mapped[int] = mapped_column(primary_key=True)
    metric_id: Mapped[int] = mapped_column(ForeignKey("calculated_metrics.id", ondelete="CASCADE"), index=True)
    upload_id: Mapped[int] = mapped_column(ForeignKey("uploads.id", ondelete="CASCADE"), index=True)
    source_file: Mapped[str] = mapped_column(String(255))
    source_location: Mapped[str] = mapped_column(String(255), default="data")
    included_records: Mapped[list] = mapped_column(JSON, default=list)
    excluded_records: Mapped[list] = mapped_column(JSON, default=list)
    formula: Mapped[str] = mapped_column(Text)
    mappings: Mapped[dict] = mapped_column(JSON, default=dict)
    adjustments: Mapped[list] = mapped_column(JSON, default=list)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    engine_version: Mapped[str] = mapped_column(String(40))


class ValidationResult(Base):
    __tablename__ = "validation_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    calculation_id: Mapped[int] = mapped_column(ForeignKey("calculation_versions.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(12), index=True)
    message: Mapped[str] = mapped_column(Text)
    row_ids: Mapped[list] = mapped_column(JSON, default=list)
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class ForecastResult(Base):
    __tablename__ = "forecast_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    calculation_id: Mapped[int] = mapped_column(ForeignKey("calculation_versions.id", ondelete="CASCADE"), index=True)
    horizon_days: Mapped[int] = mapped_column(Integer, default=30)
    status: Mapped[str] = mapped_column(String(12), index=True)
    opening_cash: Mapped[float | None] = mapped_column(Float, nullable=True)
    projected_inflow: Mapped[float | None] = mapped_column(Float, nullable=True)
    projected_outflow: Mapped[float | None] = mapped_column(Float, nullable=True)
    projected_closing_cash: Mapped[float | None] = mapped_column(Float, nullable=True)
    shortage_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    inputs: Mapped[dict] = mapped_column(JSON, default=dict)
    daily_results: Mapped[list] = mapped_column(JSON, default=list)
