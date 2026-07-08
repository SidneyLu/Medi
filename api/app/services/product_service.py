from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, desc, or_, select
from sqlalchemy.orm import Session

from app.db.models import (
    Brand,
    PriceSnapshot,
    ProductSeries,
    ProductSku,
    SellingPointSnapshot,
    SourceDocument,
    SpecSnapshot,
    TimelineEvent,
)
from app.schemas.common import Citation, CompareTable, TimelineEventOut
from app.schemas.product import ProductDetail, ProductListItem


class ProductService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_products(self, search: str | None = None, brand: str | None = None, category: str | None = None) -> list[ProductListItem]:
        stmt: Select[Any] = (
            select(ProductSku, Brand.name)
            .join(Brand, ProductSku.brand_id == Brand.id)
            .order_by(ProductSku.id)
        )
        if search:
            token = f"%{search}%"
            stmt = stmt.where(
                or_(
                    ProductSku.model_name.ilike(token),
                    ProductSku.normalized_model_name.ilike(token),
                )
            )
        if brand:
            stmt = stmt.where(Brand.name == brand)
        if category:
            stmt = stmt.where(ProductSku.category == category)

        rows = self.db.execute(stmt).all()
        items: list[ProductListItem] = []
        for sku, brand_name in rows:
            latest_price = self._latest_snapshot(PriceSnapshot, sku.id)
            latest_spec = self._latest_snapshot(SpecSnapshot, sku.id)
            items.append(
                ProductListItem(
                    sku_id=sku.id,
                    model_name=sku.model_name,
                    normalized_model_name=sku.normalized_model_name,
                    brand_name=brand_name,
                    category=sku.category,
                    launch_date=sku.launch_date,
                    current_price=self._to_float(latest_price.current_price) if latest_price else None,
                    chipset=latest_spec.chipset if latest_spec else None,
                )
            )
        return items

    def get_product_detail(self, sku_id: int) -> ProductDetail | None:
        stmt = (
            select(ProductSku, Brand.name, ProductSeries.name)
            .join(Brand, ProductSku.brand_id == Brand.id)
            .join(ProductSeries, ProductSku.series_id == ProductSeries.id, isouter=True)
            .where(ProductSku.id == sku_id)
        )
        row = self.db.execute(stmt).first()
        if not row:
            return None
        sku, brand_name, series_name = row
        latest_price = self._latest_snapshot(PriceSnapshot, sku.id)
        latest_spec = self._latest_snapshot(SpecSnapshot, sku.id)
        latest_selling = self._latest_snapshot(SellingPointSnapshot, sku.id)
        docs = (
            self.db.execute(
                select(SourceDocument).where(SourceDocument.sku_id == sku.id).order_by(desc(SourceDocument.crawled_at)).limit(5)
            )
            .scalars()
            .all()
        )
        timeline = self.list_timeline(sku.id)
        citations = [
            Citation(
                title=doc.title,
                url=doc.url,
                source_type=doc.source_type,
                crawled_at=doc.crawled_at,
                snippet=f"来源文档：{doc.title}",
            )
            for doc in docs
        ]
        spec_json = latest_spec.spec_json if latest_spec else {}
        return ProductDetail(
            sku_id=sku.id,
            model_name=sku.model_name,
            normalized_model_name=sku.normalized_model_name,
            brand_name=brand_name,
            series_name=series_name,
            category=sku.category,
            competitor_group=sku.competitor_group,
            launch_date=sku.launch_date,
            official_url=sku.official_url,
            current_price=self._to_float(latest_price.current_price) if latest_price else None,
            original_price=self._to_float(latest_price.original_price) if latest_price else None,
            promotion_text=latest_price.promotion_text if latest_price else None,
            observed_at=latest_price.observed_at if latest_price else None,
            spec_json=spec_json,
            selling_points=latest_selling.selling_points if latest_selling else [],
            citations=citations,
            timeline=timeline,
        )

    def list_timeline(self, sku_id: int) -> list[TimelineEventOut]:
        events = (
            self.db.execute(
                select(TimelineEvent).where(TimelineEvent.sku_id == sku_id).order_by(desc(TimelineEvent.observed_at)).limit(20)
            )
            .scalars()
            .all()
        )
        return [
            TimelineEventOut(
                field=event.field_name,
                old_value=event.old_value,
                new_value=event.new_value,
                observed_at=event.observed_at,
            )
            for event in events
        ]

    def build_compare_table(self, sku_ids: list[int]) -> CompareTable:
        details = [self.get_product_detail(sku_id) for sku_id in sku_ids]
        details = [detail for detail in details if detail]
        columns = ["field"] + [detail.model_name for detail in details]
        tracked_fields = [
            ("brand", "品牌"),
            ("current_price", "现价"),
            ("chipset", "芯片"),
            ("ram", "内存"),
            ("storage", "存储"),
            ("screen_size", "屏幕尺寸"),
            ("battery_capacity", "电池"),
        ]
        rows: list[dict[str, Any]] = []
        for field_key, field_label in tracked_fields:
            row: dict[str, Any] = {"field": field_label}
            for detail in details:
                value = detail.brand_name if field_key == "brand" else detail.spec_json.get(field_key)
                if field_key == "current_price":
                    value = detail.current_price
                row[detail.model_name] = value
            rows.append(row)
        return CompareTable(columns=columns, rows=rows)

    def get_related_skus(self, sku_ids: list[int]) -> list[dict[str, Any]]:
        if not sku_ids:
            return []
        rows = self.db.execute(
            select(ProductSku, Brand.name)
            .join(Brand, ProductSku.brand_id == Brand.id)
            .where(ProductSku.id.in_(sku_ids))
        ).all()
        return [
            {"sku_id": sku.id, "model_name": sku.model_name, "brand_name": brand_name}
            for sku, brand_name in rows
        ]

    def build_structured_summary(self, sku_ids: list[int]) -> tuple[str, list[str]]:
        details = [self.get_product_detail(sku_id) for sku_id in sku_ids]
        details = [detail for detail in details if detail]
        if not details:
            return "当前没有匹配到 SKU 数据。", ["sku_ids"]
        sentences: list[str] = []
        missing_fields: list[str] = []
        for detail in details:
            spec = detail.spec_json
            missing = [field for field in ("chipset", "ram", "storage", "battery_capacity") if not spec.get(field)]
            missing_fields.extend([f"{detail.model_name}:{field}" for field in missing])
            sentences.append(
                f"{detail.model_name} 当前价格 {detail.current_price or '未知'} 元，芯片 {spec.get('chipset', '未知')}，"
                f"电池 {spec.get('battery_capacity', '未知')}，卖点包括 {'、'.join(detail.selling_points[:3]) or '暂无'}。"
            )
        return "\n".join(sentences), missing_fields

    def _latest_snapshot(self, model: Any, sku_id: int) -> Any | None:
        return (
            self.db.execute(
                select(model).where(model.sku_id == sku_id).order_by(desc(model.observed_at)).limit(1)
            )
            .scalars()
            .first()
        )

    def _to_float(self, value: Decimal | None) -> float | None:
        return float(value) if value is not None else None
