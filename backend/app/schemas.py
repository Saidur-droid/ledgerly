from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("full_name")
    @classmethod
    def normalize_full_name(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError("Full name must contain at least two characters.")
        return normalized


class UserRead(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    model_config = ConfigDict(from_attributes=True)


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = Field(default=None, min_length=2, max_length=120)

    @field_validator("full_name")
    @classmethod
    def normalize_full_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError("Full name must contain at least two characters.")
        return normalized

    @model_validator(mode="after")
    def require_update(self) -> "UserUpdate":
        if self.email is None and self.full_name is None:
            raise ValueError("Provide an email or full name to update.")
        return self


class SettingsRead(BaseModel):
    profile: UserRead


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)


AnalysisValue = str | int | float | bool | None
ShortText = Annotated[str, Field(min_length=1, max_length=500)]
LongText = Annotated[str, Field(min_length=1, max_length=20_000)]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnalysisColumn(ContractModel):
    label: ShortText
    align: Literal["left", "right"] = "left"


class AnalysisMetric(ContractModel):
    label: ShortText
    value: AnalysisValue
    detail: ShortText | None = None


class TextSection(ContractModel):
    type: Literal["text"]
    heading: ShortText | None = None
    markdown: LongText


class MetricsSection(ContractModel):
    type: Literal["metrics"]
    heading: ShortText | None = None
    items: list[AnalysisMetric] = Field(min_length=1, max_length=20)


class TableSection(ContractModel):
    type: Literal["table"]
    heading: ShortText | None = None
    columns: list[AnalysisColumn] = Field(min_length=1, max_length=12)
    rows: list[list[AnalysisValue]] = Field(max_length=50)

    @model_validator(mode="after")
    def rows_match_columns(self) -> "TableSection":
        if any(len(row) != len(self.columns) for row in self.rows):
            raise ValueError("Each table row must match the declared column count.")
        for row in self.rows:
            for value in row:
                if isinstance(value, str) and len(value) > 500:
                    raise ValueError("Table cell text exceeds 500 characters.")
        return self


class ListSection(ContractModel):
    type: Literal["list"]
    heading: ShortText | None = None
    style: Literal["bulleted", "numbered"] = "bulleted"
    items: list[ShortText] = Field(max_length=30)


class Scenario(ContractModel):
    name: ShortText
    assumptions: list[ShortText] = Field(max_length=20)
    outcomes: list[AnalysisMetric] = Field(max_length=20)


class ScenariosSection(ContractModel):
    type: Literal["scenarios"]
    heading: ShortText | None = None
    scenarios: list[Scenario] = Field(min_length=1, max_length=10)


class ForecastSection(ContractModel):
    type: Literal["forecast"]
    heading: ShortText | None = None
    summary: LongText
    horizon: ShortText | None = None
    methodology: LongText | None = None
    metrics: list[AnalysisMetric] = Field(default_factory=list, max_length=20)
    caveats: list[ShortText] = Field(default_factory=list, max_length=20)


class Risk(ContractModel):
    label: ShortText
    detail: ShortText
    severity: Literal["low", "medium", "high", "unknown"] = "unknown"


class RisksSection(ContractModel):
    type: Literal["risks"]
    heading: ShortText | None = None
    items: list[Risk] = Field(max_length=30)


class Action(ContractModel):
    label: ShortText
    detail: ShortText | None = None
    priority: Literal["low", "medium", "high", "unprioritized"] = "unprioritized"


class ActionsSection(ContractModel):
    type: Literal["actions"]
    heading: ShortText | None = None
    items: list[Action] = Field(max_length=30)


class NoticeSection(ContractModel):
    type: Literal["notice"]
    tone: Literal["info", "warning", "policy", "error"] = "info"
    heading: ShortText | None = None
    message: LongText


AnalysisSection = Annotated[
    TextSection
    | MetricsSection
    | TableSection
    | ListSection
    | ScenariosSection
    | ForecastSection
    | RisksSection
    | ActionsSection
    | NoticeSection,
    Field(discriminator="type"),
]


class ChatResponse(ContractModel):
    schema_version: Literal[1] = 1
    type: Literal["markdown", "structured", "policy_notice", "error"]
    content: LongText | None = None
    sections: list[AnalysisSection] = Field(default_factory=list, max_length=24)
    correlation_id: str = Field(min_length=8, max_length=64, pattern=r"^[a-zA-Z0-9-]+$")

    @model_validator(mode="after")
    def type_matches_content(self) -> "ChatResponse":
        if self.type == "markdown":
            if self.content is None or self.sections:
                raise ValueError(
                    "Markdown responses require content and cannot contain sections."
                )
        elif self.type == "structured":
            if self.content is not None:
                raise ValueError("Structured responses cannot contain content.")
        elif self.type == "policy_notice":
            if self.content is None:
                raise ValueError("Policy notices require content.")
        elif self.content is None or self.sections:
            raise ValueError("Error responses require content and no sections.")
        return self


class UploadRead(BaseModel):
    id: int
    filename: str
    file_type: str
    row_count: int
    confidence: float
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class PulseRead(BaseModel):
    score: int
    confidence: float
    summary: str
    factors: list[dict]
    metrics: dict
    comparison: dict | None = None


class MappingUpdate(BaseModel):
    role: Literal["bank_statement", "ledger", "sales", "expenses", "unknown"]
    period: str | None = Field(default=None, max_length=40)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    column_mapping: dict[str, str]


class CleaningDecision(BaseModel):
    status: Literal["approved", "rejected"]
    final_value: AnalysisValue = None


class ReconciliationCreate(BaseModel):
    bank_upload_id: int
    ledger_upload_id: int


class MatchDecision(BaseModel):
    status: Literal["approved", "rejected", "pending"]
    note: str | None = Field(default=None, max_length=2000)
    idempotency_key: str | None = Field(default=None, max_length=100)


class ManualMatchCreate(BaseModel):
    bank_row: int = Field(ge=2)
    ledger_row: int = Field(ge=2)
    note: str | None = Field(default=None, max_length=2000)
    idempotency_key: str | None = Field(default=None, max_length=100)


class ReconciliationAction(BaseModel):
    note: str | None = Field(default=None, max_length=2000)
    idempotency_key: str | None = Field(default=None, max_length=100)


class BalanceUpdate(BaseModel):
    opening_balance: float
    closing_balance: float
