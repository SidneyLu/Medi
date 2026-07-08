from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import Citation, CompareTable, RelatedSku, TimelineEventOut


class ChatRequest(BaseModel):
    question: str
    sku_ids: list[int] = Field(default_factory=list)
    comparison_sku_ids: list[int] = Field(default_factory=list)
    time_range: str | None = None
    source_filters: list[str] = Field(default_factory=list)


class ChatResponse(BaseModel):
    answer_text: str
    citations: list[Citation] = Field(default_factory=list)
    compare_table: CompareTable = Field(default_factory=CompareTable)
    timeline_events: list[TimelineEventOut] = Field(default_factory=list)
    related_skus: list[RelatedSku] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    generated_at: datetime


class CompareRequest(BaseModel):
    sku_ids: list[int] = Field(min_length=2, max_length=4)
