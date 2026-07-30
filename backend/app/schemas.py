from datetime import datetime
from typing import Literal

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


class AnalysisColumn(BaseModel):
    key: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=120)
    align: Literal["left", "right"] = "left"


class AnalysisTable(BaseModel):
    columns: list[AnalysisColumn] = Field(min_length=1, max_length=20)
    rows: list[dict[str, AnalysisValue]] = Field(max_length=100)


class AnalysisCard(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    value: str = Field(min_length=1, max_length=240)
    detail: str | None = Field(default=None, max_length=500)


class AnalysisSection(BaseModel):
    heading: str = Field(min_length=1, max_length=160)
    markdown: str | None = Field(default=None, max_length=20_000)
    table: AnalysisTable | None = None
    cards: list[AnalysisCard] = Field(default_factory=list, max_length=20)


class RankingMetadata(BaseModel):
    formula: str = Field(min_length=1, max_length=300)
    weights: dict[str, float]
    normalization: str = Field(min_length=1, max_length=1_000)
    first_period: str = Field(min_length=1, max_length=1_000)
    interpretation: str = Field(min_length=1, max_length=1_000)


class StructuredAnalysis(BaseModel):
    kind: Literal["structured_analysis"]
    title: str = Field(min_length=1, max_length=200)
    summary: str | None = Field(default=None, max_length=5_000)
    sections: list[AnalysisSection] = Field(default_factory=list, max_length=30)
    scoring: RankingMetadata | None = None
    risks: list[str] = Field(default_factory=list, max_length=30)
    action_plan: list[str] = Field(default_factory=list, max_length=30)


class ChatResponse(BaseModel):
    answer: str | StructuredAnalysis
    confidence: str
    sources: list[str]
    disclaimer: str


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
