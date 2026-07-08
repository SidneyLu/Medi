from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Citation(BaseModel):
    title: str
    url: str
    source_type: str
    crawled_at: datetime | None = None
    snippet: str


class CompareTable(BaseModel):
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)


class TimelineEventOut(BaseModel):
    field: str
    old_value: str | None = None
    new_value: str | None = None
    observed_at: datetime


class RelatedSku(BaseModel):
    sku_id: int
    model_name: str
    brand_name: str
