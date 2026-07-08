from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.db.models import (
    Brand,
    PriceSnapshot,
    ProductAlias,
    ProductSeries,
    ProductSku,
    PromotionSnapshot,
    SellingPointSnapshot,
    SourceDocument,
    SourceSite,
    SpecSnapshot,
    TimelineEvent,
)
from app.db.session import SessionLocal
from app.services.llm_service import LLMService
from app.services.vector_store import VectorStoreService


def import_seed_data() -> dict[str, int]:
    settings = get_settings()
    llm_service = LLMService()
    vector_store = VectorStoreService()
    splitter = RecursiveCharacterTextSplitter(chunk_size=400, chunk_overlap=60)
    counts = defaultdict(int)
    with SessionLocal() as db:
        sku_lookup = _import_skus(db, settings.seed_data_dir / "product_sku_seed.csv", counts)
        _import_aliases(db, settings.seed_data_dir / "product_alias.csv", sku_lookup, counts)
        site_lookup = _import_sites(db, settings.seed_data_dir / "source_registry.csv", counts)
        doc_metadata = _load_doc_metadata(settings.seed_data_dir / "manual_source_urls.csv")
        db.commit()

        for normalized_name, sku_id in sku_lookup.items():
            base_dir = settings.processed_data_dir / normalized_name
            if not base_dir.exists():
                continue
            for source_type_dir in base_dir.iterdir():
                if not source_type_dir.is_dir():
                    continue
                for doc_file in source_type_dir.glob("*.*"):
                    if doc_file.suffix.lower() not in {".md", ".txt"}:
                        continue
                    metadata = _pick_doc_metadata(doc_metadata, normalized_name, source_type_dir.name, doc_file)
                    source_document = _upsert_source_document(
                        db=db,
                        sku_id=sku_id,
                        site_lookup=site_lookup,
                        source_type=source_type_dir.name,
                        doc_file=doc_file,
                        metadata=metadata,
                    )
                    db.commit()
                    vector_store.delete_by_document(source_document.id)
                    text = doc_file.read_text(encoding="utf-8")
                    chunks = splitter.split_text(text)
                    embeddings = llm_service.embed_documents(chunks) if chunks else []
                    ids = [f"{source_document.id}-{index}" for index in range(len(chunks))]
                    metadatas = [
                        {
                            "chunk_id": ids[index],
                            "source_document_id": source_document.id,
                            "sku_id": sku_id,
                            "source_type": source_document.source_type,
                            "site_name": metadata["site_name"],
                            "title": source_document.title,
                            "published_at": source_document.published_at.isoformat() if source_document.published_at else "",
                            "crawled_at": source_document.crawled_at.isoformat(),
                            "url": source_document.url,
                        }
                        for index in range(len(chunks))
                    ]
                    if chunks:
                        vector_store.upsert(ids=ids, documents=chunks, metadatas=metadatas, embeddings=embeddings)
                    counts["documents"] += 1
                    counts["chunks"] += len(chunks)
        db.commit()
    return dict(counts)


def _import_skus(db, csv_path: Path, counts: defaultdict[str, int]) -> dict[str, int]:
    rows = _read_csv(csv_path)
    sku_lookup: dict[str, int] = {}
    for row in rows:
        brand = _get_or_create(db, Brand, {"name": row["brand_name"]})
        series = _get_or_create(db, ProductSeries, {"brand_id": brand.id, "name": row["series_name"]})
        sku = db.execute(
            select(ProductSku).where(ProductSku.normalized_model_name == row["normalized_model_name"])
        ).scalar_one_or_none()
        launch_date = datetime.strptime(row["launch_date"], "%Y-%m-%d").date() if row.get("launch_date") else None
        if not sku:
            sku = ProductSku(
                brand_id=brand.id,
                series_id=series.id,
                model_name=row["model_name"],
                normalized_model_name=row["normalized_model_name"],
                category=row["category"],
                competitor_group=row.get("competitor_group"),
                official_url=row.get("official_url"),
                launch_date=launch_date,
                status="active",
            )
            db.add(sku)
            db.flush()
            counts["skus"] += 1
        else:
            sku.brand_id = brand.id
            sku.series_id = series.id
            sku.model_name = row["model_name"]
            sku.category = row["category"]
            sku.competitor_group = row.get("competitor_group")
            sku.official_url = row.get("official_url")
            sku.launch_date = launch_date
        sku_lookup[row["normalized_model_name"]] = sku.id
        _upsert_seed_snapshots(db, sku.id, row)
    return sku_lookup


def _upsert_seed_snapshots(db, sku_id: int, row: dict[str, str]) -> None:
    observed_at = datetime.utcnow()
    db.execute(delete(PriceSnapshot).where(PriceSnapshot.sku_id == sku_id, PriceSnapshot.source_document_id.is_(None)))
    db.execute(delete(SpecSnapshot).where(SpecSnapshot.sku_id == sku_id, SpecSnapshot.source_document_id.is_(None)))
    db.execute(delete(PromotionSnapshot).where(PromotionSnapshot.sku_id == sku_id, PromotionSnapshot.source_document_id.is_(None)))
    db.execute(delete(SellingPointSnapshot).where(SellingPointSnapshot.sku_id == sku_id, SellingPointSnapshot.source_document_id.is_(None)))
    db.execute(delete(TimelineEvent).where(TimelineEvent.sku_id == sku_id, TimelineEvent.source_document_id.is_(None)))
    spec_json = {
        "chipset": row.get("chipset"),
        "ram": row.get("ram"),
        "storage": row.get("storage"),
        "screen_size": row.get("screen_size"),
        "resolution": row.get("resolution"),
        "refresh_rate": row.get("refresh_rate"),
        "battery_capacity": row.get("battery_capacity"),
    }
    spec = SpecSnapshot(
        sku_id=sku_id,
        observed_at=observed_at,
        chipset=row.get("chipset"),
        ram=row.get("ram"),
        storage=row.get("storage"),
        screen_size=row.get("screen_size"),
        battery_capacity=row.get("battery_capacity"),
        spec_json=spec_json,
    )
    db.add(spec)
    db.add(
        PriceSnapshot(
            sku_id=sku_id,
            current_price=Decimal(row["current_price"]) if row.get("current_price") else None,
            original_price=Decimal(row["original_price"]) if row.get("original_price") else None,
            promotion_text=row.get("promotion_text"),
            platform="seed",
            observed_at=observed_at,
        )
    )
    if row.get("promotion_text"):
        db.add(PromotionSnapshot(sku_id=sku_id, promotion_text=row["promotion_text"], observed_at=observed_at))
    selling_points = [point.strip() for point in (row.get("selling_points") or "").split("|") if point.strip()]
    if selling_points:
        db.add(SellingPointSnapshot(sku_id=sku_id, selling_points=selling_points, observed_at=observed_at))
    for field_name, new_value in spec_json.items():
        if new_value:
            db.add(
                TimelineEvent(
                    sku_id=sku_id,
                    field_name=field_name,
                    old_value=None,
                    new_value=new_value,
                    observed_at=observed_at,
                )
            )
    if row.get("current_price"):
        db.add(
            TimelineEvent(
                sku_id=sku_id,
                field_name="current_price",
                old_value=None,
                new_value=row["current_price"],
                observed_at=observed_at,
            )
        )


def _import_aliases(db, csv_path: Path, sku_lookup: dict[str, int], counts: defaultdict[str, int]) -> None:
    rows = _read_csv(csv_path)
    for row in rows:
        sku_id = sku_lookup.get(row["normalized_model_name"])
        if not sku_id:
            continue
        exists = db.execute(
            select(ProductAlias).where(ProductAlias.sku_id == sku_id, ProductAlias.alias_text == row["alias_text"])
        ).scalar_one_or_none()
        if not exists:
            db.add(
                ProductAlias(
                    sku_id=sku_id,
                    alias_text=row["alias_text"],
                    alias_type=row.get("alias_type"),
                    source=row.get("source"),
                )
            )
            counts["aliases"] += 1


def _import_sites(db, csv_path: Path, counts: defaultdict[str, int]) -> dict[str, int]:
    rows = _read_csv(csv_path)
    site_lookup: dict[str, int] = {}
    for row in rows:
        site = db.execute(select(SourceSite).where(SourceSite.site_name == row["site_name"])).scalar_one_or_none()
        if not site:
            site = SourceSite(
                site_name=row["site_name"],
                source_type=row["source_type"],
                base_url=row.get("base_url"),
                priority=int(row["priority"]) if row.get("priority") else None,
                crawl_frequency=row.get("crawl_frequency"),
                notes=row.get("notes"),
            )
            db.add(site)
            db.flush()
            counts["sites"] += 1
        site_lookup[site.site_name] = site.id
    return site_lookup


def _load_doc_metadata(csv_path: Path) -> dict[tuple[str, str], list[dict[str, str]]]:
    mapping: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in _read_csv(csv_path):
        key = (row["sku_model_name"], row["source_type"])
        mapping[key].append(row)
    return mapping


def _pick_doc_metadata(mapping: dict[tuple[str, str], list[dict[str, str]]], normalized_name: str, source_type: str, doc_file: Path) -> dict[str, str]:
    candidates = mapping.get((normalized_name, source_type), [])
    rel = doc_file.relative_to(doc_file.parents[1]).as_posix()
    for candidate in candidates:
        if candidate.get("document_path") == rel:
            return candidate
    return candidates[0] if candidates else {
        "site_name": source_type,
        "url": f"file://{doc_file.as_posix()}",
        "title": doc_file.stem,
    }


def _upsert_source_document(db, sku_id: int, site_lookup: dict[str, int], source_type: str, doc_file: Path, metadata: dict[str, str]) -> SourceDocument:
    clean_text_path = str(doc_file)
    url = metadata.get("url") or f"file://{doc_file.as_posix()}"
    document = db.execute(
        select(SourceDocument).where(
            SourceDocument.sku_id == sku_id,
            SourceDocument.url == url,
            SourceDocument.clean_text_path == clean_text_path,
        )
    ).scalar_one_or_none()
    title = metadata.get("title") or _extract_title(doc_file)
    if not document:
        document = SourceDocument(
            source_site_id=site_lookup.get(metadata.get("site_name", "")),
            sku_id=sku_id,
            source_type=source_type,
            url=url,
            title=title,
            published_at=datetime.utcnow(),
            crawled_at=datetime.utcnow(),
            raw_storage_path=str(get_settings().raw_data_dir / doc_file.relative_to(get_settings().processed_data_dir)),
            clean_text_path=clean_text_path,
        )
        db.add(document)
        db.flush()
        return document
    document.source_site_id = site_lookup.get(metadata.get("site_name", ""))
    document.source_type = source_type
    document.title = title
    document.crawled_at = datetime.utcnow()
    return document


def _extract_title(doc_file: Path) -> str:
    first_line = doc_file.read_text(encoding="utf-8").splitlines()[0]
    return first_line.lstrip("# ").strip() if first_line else doc_file.stem


def _read_csv(csv_path: Path) -> list[dict[str, str]]:
    if not csv_path.exists():
        return []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _get_or_create(db, model, attrs: dict[str, str]):
    instance = db.execute(select(model).filter_by(**attrs)).scalar_one_or_none()
    if instance:
        return instance
    instance = model(**attrs)
    db.add(instance)
    db.flush()
    return instance
