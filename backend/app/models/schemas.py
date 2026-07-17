from typing import Literal

from pydantic import BaseModel, Field, field_validator

SexAtBirth = Literal["female", "male", "other", "unknown"]
PregnancyStatus = Literal["not_applicable", "pregnant", "postpartum", "unknown"]
ReportType = Literal["physical_exam", "blood_test", "other"]
RiskLevel = Literal["low", "medium", "high", "unknown"]
ReportStatus = Literal["uploaded", "ocr_processing", "needs_confirmation", "interpreting", "completed", "failed"]
IndicatorStatus = Literal["low", "normal", "high", "unknown"]
Role = Literal["user", "assistant"]


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


class UserData(BaseModel):
    user_id: str
    email: str
    nickname: str


class AuthSessionData(UserData):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class ProfilePayload(BaseModel):
    nickname: str = Field(default="", max_length=80)
    birth_date: str = Field(default="", description="YYYY-MM-DD")
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
    chunk_id: str
    article_title: str
    section_title: str
    source_url: str


class PdfBoundingBox(BaseModel):
    page: int
    bbox: list[float]


class CitationDetail(BaseModel):
    chunk_id: str
    document_id: str
    document_title: str
    section_title: str
    heading_path: list[str]
    page_start: int
    page_end: int
    page_count: int
    source_excerpt: str
    document_version: str
    source_bboxes: list[PdfBoundingBox] = Field(default_factory=list)
    preview_url: str


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


class Paginated(BaseModel):
    items: list
    next_cursor: str | None = None


class ChatQueryRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=1000)
    use_profile: bool = True


class Conversation(BaseModel):
    conversation_id: str
    title: str
    updated_at: str
    preview: str


class ChatMessage(BaseModel):
    message_id: str
    role: Role
    content: str
    created_at: str
    risk_level: RiskLevel | None = None
    suggestions: list[str] | None = None
    profile_tags_used: list[str] | None = None
    citations: list[Citation] | None = None
    evidence_available: bool | None = None


class ConversationDetail(Conversation):
    messages: list[ChatMessage]


class ConversationListData(BaseModel):
    items: list[Conversation]
    next_cursor: str | None = None


class ReportItem(BaseModel):
    item_id: str
    name: str
    value: float | None = None
    unit: str = ""
    reference_low: float | None = None
    reference_high: float | None = None
    status: IndicatorStatus = "unknown"
    explanation: str | None = None
    suggestions: list[str] | None = None
    citations: list[Citation] | None = None


class ReportData(BaseModel):
    report_id: str
    file_name: str
    report_type: ReportType
    status: ReportStatus
    created_at: str
    summary: str | None = None
    profile_tags_used: list[str]
    items: list[ReportItem]
    error_message: str | None = None


class ReportListData(BaseModel):
    items: list[ReportData]
    next_cursor: str | None = None


class ReportItemsUpdateRequest(BaseModel):
    items: list[ReportItem]
