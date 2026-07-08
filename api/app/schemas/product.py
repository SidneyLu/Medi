from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel

from app.schemas.common import Citation, TimelineEventOut


class ProductListItem(BaseModel):
    sku_id: int
    model_name: str
    normalized_model_name: str
    brand_name: str
    category: str
    launch_date: date | None = None
    current_price: float | None = None
    chipset: str | None = None


class ProductDetail(BaseModel):
    sku_id: int
    model_name: str
    normalized_model_name: str
    brand_name: str
    series_name: str | None = None
    category: str
    competitor_group: str | None = None
    launch_date: date | None = None
    official_url: str | None = None
    current_price: float | None = None
    original_price: float | None = None
    promotion_text: str | None = None
    observed_at: datetime | None = None
    spec_json: dict[str, Any]
    selling_points: list[str]
    citations: list[Citation]
    timeline: list[TimelineEventOut]
