from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=128)


class UserRead(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)


class ChatResponse(BaseModel):
    answer: str
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
