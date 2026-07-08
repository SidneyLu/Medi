from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Brand(Base):
    __tablename__ = "brand"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ProductSeries(Base):
    __tablename__ = "product_series"
    __table_args__ = (UniqueConstraint("brand_id", "name", name="uq_series_brand_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brand.id"))
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    brand: Mapped[Brand] = relationship()


class ProductSku(Base):
    __tablename__ = "product_sku"
    __table_args__ = (UniqueConstraint("normalized_model_name", name="uq_sku_normalized_model"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brand.id"))
    series_id: Mapped[int | None] = mapped_column(ForeignKey("product_series.id"))
    model_name: Mapped[str] = mapped_column(String(180), index=True)
    normalized_model_name: Mapped[str] = mapped_column(String(180), index=True)
    category: Mapped[str] = mapped_column(String(50), index=True)
    competitor_group: Mapped[str | None] = mapped_column(String(100))
    official_url: Mapped[str | None] = mapped_column(Text)
    launch_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    brand: Mapped[Brand] = relationship()
    series: Mapped[ProductSeries | None] = relationship()


class ProductAlias(Base):
    __tablename__ = "product_alias"
    __table_args__ = (UniqueConstraint("sku_id", "alias_text", name="uq_alias_sku_text"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    sku_id: Mapped[int] = mapped_column(ForeignKey("product_sku.id"), index=True)
    alias_text: Mapped[str] = mapped_column(String(180), index=True)
    alias_type: Mapped[str | None] = mapped_column(String(50))
    source: Mapped[str | None] = mapped_column(String(50))


class SourceSite(Base):
    __tablename__ = "source_site"
    __table_args__ = (UniqueConstraint("site_name", name="uq_source_site_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    site_name: Mapped[str] = mapped_column(String(120), index=True)
    source_type: Mapped[str] = mapped_column(String(30), index=True)
    base_url: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[int | None]
    crawl_frequency: Mapped[str | None] = mapped_column(String(50))
    notes: Mapped[str | None] = mapped_column(Text)


class SourceDocument(Base):
    __tablename__ = "source_document"
    __table_args__ = (
        UniqueConstraint("sku_id", "url", "clean_text_path", name="uq_source_document_identity"),
        Index("ix_source_document_sku_type", "sku_id", "source_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_site_id: Mapped[int | None] = mapped_column(ForeignKey("source_site.id"))
    sku_id: Mapped[int] = mapped_column(ForeignKey("product_sku.id"), index=True)
    source_type: Mapped[str] = mapped_column(String(30), index=True)
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(String(255))
    published_at: Mapped[datetime | None] = mapped_column(DateTime)
    crawled_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    raw_storage_path: Mapped[str | None] = mapped_column(Text)
    clean_text_path: Mapped[str | None] = mapped_column(Text)

    source_site: Mapped[SourceSite | None] = relationship()
    sku: Mapped[ProductSku] = relationship()


class PriceSnapshot(Base):
    __tablename__ = "price_snapshot"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku_id: Mapped[int] = mapped_column(ForeignKey("product_sku.id"), index=True)
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("source_document.id"))
    current_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    original_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    promotion_text: Mapped[str | None] = mapped_column(Text)
    platform: Mapped[str | None] = mapped_column(String(120))
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class SpecSnapshot(Base):
    __tablename__ = "spec_snapshot"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku_id: Mapped[int] = mapped_column(ForeignKey("product_sku.id"), index=True)
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("source_document.id"))
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    chipset: Mapped[str | None] = mapped_column(String(120))
    ram: Mapped[str | None] = mapped_column(String(80))
    storage: Mapped[str | None] = mapped_column(String(80))
    screen_size: Mapped[str | None] = mapped_column(String(80))
    battery_capacity: Mapped[str | None] = mapped_column(String(80))
    spec_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class PromotionSnapshot(Base):
    __tablename__ = "promotion_snapshot"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku_id: Mapped[int] = mapped_column(ForeignKey("product_sku.id"), index=True)
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("source_document.id"))
    promotion_text: Mapped[str] = mapped_column(Text)
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class SellingPointSnapshot(Base):
    __tablename__ = "selling_point_snapshot"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku_id: Mapped[int] = mapped_column(ForeignKey("product_sku.id"), index=True)
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("source_document.id"))
    selling_points: Mapped[list[str]] = mapped_column(JSONB, default=list)
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class TimelineEvent(Base):
    __tablename__ = "timeline_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku_id: Mapped[int] = mapped_column(ForeignKey("product_sku.id"), index=True)
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("source_document.id"))
    field_name: Mapped[str] = mapped_column(String(120), index=True)
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
