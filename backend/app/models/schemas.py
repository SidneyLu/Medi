from typing import Literal

from pydantic import BaseModel, Field, field_validator

SexAtBirth = Literal["female", "male", "intersex", "unknown"]
PregnancyStatus = Literal["not_applicable", "not_pregnant", "pregnant", "postpartum", "unknown"]
ReportType = Literal["physical_exam", "blood_test", "other"]
RiskLevel = Literal["low", "medium", "high", "unknown"]
ReportStatus = Literal["processing", "completed", "failed"]
IndicatorStatus = Literal["low", "normal", "high", "unknown"]


class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=254)
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized or "." not in normalized.rsplit("@", 1)[-1]:
            raise ValueError("invalid email address")
        return normalized

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        has_letter = any(ch.isalpha() for ch in value)
        has_digit = any(ch.isdigit() for ch in value)
        if not has_letter or not has_digit:
            raise ValueError("password must contain at least one letter and one digit")
        return value


class LoginRequest(RegisterRequest):
    pass


class AuthData(BaseModel):
    user_id: str
    email: str | None = None
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int | None = None


class ProfilePayload(BaseModel):
    nickname: str | None = Field(default=None, max_length=80)
    birth_date: str | None = Field(default=None, description="YYYY-MM-DD")
    sex_at_birth: SexAtBirth = "unknown"
    height_cm: float | None = Field(default=None, ge=30, le=260)
    weight_kg: float | None = Field(default=None, ge=1, le=400)
    pregnancy_status: PregnancyStatus = "unknown"
    chronic_conditions: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    current_medications: list[str] = Field(default_factory=list)


class ProfileData(BaseModel):
    profile: ProfilePayload | None
    tags: list[str]


class Citation(BaseModel):
    chunk_id: str | None = None
    article_title: str
    section_title: str
    source_url: str


class KnowledgeChunkData(BaseModel):
    chunk_id: str
    article_title: str
    section_title: str
    source_url: str
    category: str
    content: str
    score: float = 0
    tags: list[str] = Field(default_factory=list)
    version_label: str | None = None
    revised_at: str | None = None


class KnowledgeSearchData(BaseModel):
    query: str
    chunks: list[KnowledgeChunkData]


class ChatQueryRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=1000)
    use_profile: bool = True


class ChatQueryData(BaseModel):
    question: str
    answer: str
    risk_level: RiskLevel
    suggestions: list[str]
    profile_tags_used: list[str]
    citations: list[Citation]


class ReportItem(BaseModel):
    item_id: str
    name: str
    value: float | str | None = None
    unit: str | None = None
    reference_low: float | None = None
    reference_high: float | None = None
    status: IndicatorStatus
    explanation: str
    suggestions: list[str]
    citations: list[Citation]


class ReportAnalyzeData(BaseModel):
    report_id: str
    file_name: str
    report_type: ReportType
    status: ReportStatus
    summary: str
    profile_tags_used: list[str]
    items: list[ReportItem]


class ReportDetailData(ReportAnalyzeData):
    pass
