from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.knowledge_repository import KnowledgeImportRepository
from app.services.milvus_service import MilvusService

EXPECTED_MODEL_NAME = "BAAI/bge-small-zh-v1.5"
EXPECTED_DIMENSION = 512
HEX_64_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def resolve_project_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_text(record: dict[str, Any], field: str, line_number: int, path: Path, chunk_id: str = "") -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        suffix = f" for chunk_id {chunk_id}" if chunk_id else ""
        raise ValueError(f"{path}:{line_number} {field} must be a non-empty string{suffix}")
    return value.strip()


def require_int(record: dict[str, Any], field: str, line_number: int, path: Path, chunk_id: str = "") -> int:
    value = record.get(field)
    if isinstance(value, bool):
        suffix = f" for chunk_id {chunk_id}" if chunk_id else ""
        raise ValueError(f"{path}:{line_number} {field} must be an integer{suffix}")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        suffix = f" for chunk_id {chunk_id}" if chunk_id else ""
        raise ValueError(f"{path}:{line_number} {field} must be an integer{suffix}") from exc
    if str(value).strip() != str(parsed) and not isinstance(value, int):
        suffix = f" for chunk_id {chunk_id}" if chunk_id else ""
        raise ValueError(f"{path}:{line_number} {field} must be an integer{suffix}")
    return parsed


def require_document_id(record: dict[str, Any], line_number: int, path: Path, chunk_id: str) -> str:
    value = record.get("document_id")
    if not isinstance(value, str) or not HEX_64_PATTERN.fullmatch(value):
        raise ValueError(
            f"{path}:{line_number} invalid document_id for chunk_id {chunk_id}: "
            f"{value!r}; expected a 64-character lowercase hexadecimal string"
        )
    return value


def read_jsonl_chunks(path: Path) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    seen_chunk_ids: set[str] = set()
    page_groups: dict[tuple[str, int], dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                record = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number} is not valid JSON: {exc}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"{path}:{line_number} must be a JSON object")

            chunk_id = require_text(record, "chunk_id", line_number, path)
            document_id = require_document_id(record, line_number, path, chunk_id)
            pdf_page = require_int(record, "pdf_page", line_number, path, chunk_id)
            chunk_index = require_int(record, "chunk_index", line_number, path, chunk_id)
            chunk_count = require_int(record, "chunk_count", line_number, path, chunk_id)
            article_title = require_text(record, "article_title", line_number, path, chunk_id)
            section_title = require_text(record, "section_title", line_number, path, chunk_id)
            source_url = require_text(record, "source_url", line_number, path, chunk_id)
            category = require_text(record, "category", line_number, path, chunk_id)
            content = require_text(record, "content", line_number, path, chunk_id)
            content_hash = require_text(record, "content_hash", line_number, path, chunk_id).lower()
            tags = record.get("tags")
            searchable = record.get("searchable")

            if len(chunk_id) > 64:
                raise ValueError(f"{path}:{line_number} chunk_id length must be <= 64 for chunk_id {chunk_id}")
            if chunk_id in seen_chunk_ids:
                raise ValueError(f"{path}:{line_number} duplicate chunk_id {chunk_id}")
            if pdf_page <= 0:
                raise ValueError(f"{path}:{line_number} pdf_page must be positive for chunk_id {chunk_id}")
            if chunk_index < 0:
                raise ValueError(f"{path}:{line_number} chunk_index must be >= 0 for chunk_id {chunk_id}")
            if chunk_count <= 0:
                raise ValueError(f"{path}:{line_number} chunk_count must be positive for chunk_id {chunk_id}")
            if chunk_index >= chunk_count:
                raise ValueError(f"{path}:{line_number} chunk_index must be less than chunk_count for chunk_id {chunk_id}")
            if len(category.encode("utf-8")) > 128:
                raise ValueError(f"{path}:{line_number} category UTF-8 length must be <= 128 for chunk_id {chunk_id}")
            if not isinstance(tags, list):
                raise ValueError(f"{path}:{line_number} tags must be a list for chunk_id {chunk_id}")
            if not isinstance(searchable, bool):
                raise ValueError(f"{path}:{line_number} searchable must be bool for chunk_id {chunk_id}")
            if not HEX_64_PATTERN.fullmatch(content_hash):
                raise ValueError(f"{path}:{line_number} content_hash must be a 64-character lowercase hex string for chunk_id {chunk_id}")
            expected_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            if expected_hash != content_hash:
                raise ValueError(
                    f"{path}:{line_number} content_hash mismatch for chunk_id {chunk_id}: "
                    f"expected hash {expected_hash}, actual hash {content_hash}"
                )

            page_key = (document_id, pdf_page)
            page_group = page_groups.setdefault(page_key, {"chunk_count": chunk_count, "indexes": set(), "line_number": line_number})
            if page_group["chunk_count"] != chunk_count:
                raise ValueError(
                    f"{path}:{line_number} chunk_count mismatch for document_id {document_id} pdf_page {pdf_page}: "
                    f"expected {page_group['chunk_count']}, actual {chunk_count}"
                )
            if chunk_index in page_group["indexes"]:
                raise ValueError(
                    f"{path}:{line_number} duplicate chunk_index {chunk_index} for document_id {document_id} pdf_page {pdf_page}"
                )
            page_group["indexes"].add(chunk_index)
            seen_chunk_ids.add(chunk_id)
            record["chunk_id"] = chunk_id
            record["document_id"] = document_id
            record["chunk_index"] = chunk_index
            record["chunk_count"] = chunk_count
            record["article_title"] = article_title
            record["section_title"] = section_title
            record["source_url"] = source_url
            record["category"] = category
            record["content"] = content
            record["content_hash"] = content_hash
            record["pdf_page"] = pdf_page
            record["tags"] = tags
            record["searchable"] = searchable
            chunks.append(record)
    if not chunks:
        raise ValueError(f"{path} must contain at least one knowledge chunk")
    for (document_id, pdf_page), page_group in page_groups.items():
        chunk_count = int(page_group["chunk_count"])
        expected_indexes = set(range(chunk_count))
        actual_indexes = set(page_group["indexes"])
        if actual_indexes != expected_indexes:
            missing = sorted(expected_indexes - actual_indexes)
            extra = sorted(actual_indexes - expected_indexes)
            raise ValueError(
                f"{path}: chunk_index values for document_id {document_id} pdf_page {pdf_page} "
                f"must be continuous from 0 to {chunk_count - 1}; missing={missing}, extra={extra}"
            )
    return chunks


def read_embeddings_npz(path: Path) -> dict[str, Any]:
    with np.load(path, allow_pickle=False) as archive:
        required = {"embeddings", "chunk_ids", "content_hashes", "pdf_pages"}
        missing = sorted(required - set(archive.files))
        if missing:
            raise ValueError(f"{path} missing arrays: {missing}")
        embeddings = archive["embeddings"]
        chunk_ids = archive["chunk_ids"]
        content_hashes = archive["content_hashes"]
        pdf_pages = archive["pdf_pages"]

    if embeddings.ndim != 2 or embeddings.shape[1] != EXPECTED_DIMENSION:
        raise ValueError(f"embeddings shape must be [N,{EXPECTED_DIMENSION}], found {embeddings.shape}")
    if embeddings.dtype != np.float32:
        raise ValueError(f"embeddings dtype must be float32, found {embeddings.dtype}")
    if not np.isfinite(embeddings).all():
        raise ValueError("embeddings contain NaN or Infinity")
    if len(chunk_ids) != embeddings.shape[0] or len(content_hashes) != embeddings.shape[0] or len(pdf_pages) != embeddings.shape[0]:
        raise ValueError("NPZ arrays must have the same row count")
    if pdf_pages.dtype != np.int64:
        raise ValueError(f"pdf_pages dtype must be int64, found {pdf_pages.dtype}")

    norms = np.linalg.norm(embeddings, axis=1)
    if embeddings.shape[0] and (float(norms.min()) < 0.99 or float(norms.max()) > 1.01):
        raise ValueError(
            f"embedding norms must be within 0.99-1.01, found min={float(norms.min())}, max={float(norms.max())}"
        )
    chunk_id_list = [str(value) for value in chunk_ids.tolist()]
    if len(set(chunk_id_list)) != len(chunk_id_list):
        raise ValueError("NPZ chunk_ids must be unique")

    return {
        "embeddings": embeddings,
        "chunk_ids": chunk_id_list,
        "content_hashes": [str(value) for value in content_hashes.tolist()],
        "pdf_pages": [int(value) for value in pdf_pages.tolist()],
        "norms": norms,
    }


def read_manifest(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    if not isinstance(manifest, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return manifest


def validate_manifest(manifest: dict[str, Any], chunks_path: Path, chunk_count: int) -> None:
    expected = {
        "model_name": EXPECTED_MODEL_NAME,
        "embedding_dimension": EXPECTED_DIMENSION,
        "normalized": True,
        "chunk_count": chunk_count,
        "source_chunk_count": chunk_count,
        "selected_start_index": 0,
        "selected_end_index": chunk_count,
        "input_sha256": file_sha256(chunks_path),
    }
    for key, expected_value in expected.items():
        actual_value = manifest.get(key)
        if actual_value != expected_value:
            raise ValueError(f"manifest {key} mismatch: expected {expected_value!r}, actual {actual_value!r}")


def validate_alignment(chunks: list[dict[str, Any]], npz_data: dict[str, Any]) -> None:
    if len(chunks) != len(npz_data["chunk_ids"]):
        raise ValueError(f"JSONL and NPZ row counts differ: {len(chunks)} vs {len(npz_data['chunk_ids'])}")
    for index, chunk in enumerate(chunks):
        chunk_id = chunk["chunk_id"]
        content_hash = chunk["content_hash"]
        pdf_page = int(chunk["pdf_page"])
        if chunk_id != npz_data["chunk_ids"][index]:
            raise ValueError(f"row {index} chunk_id mismatch: JSONL {chunk_id}, NPZ {npz_data['chunk_ids'][index]}")
        if content_hash != npz_data["content_hashes"][index]:
            raise ValueError(
                f"row {index} content_hash mismatch for chunk_id {chunk_id}: "
                f"JSONL {content_hash}, NPZ {npz_data['content_hashes'][index]}"
            )
        if pdf_page != npz_data["pdf_pages"][index]:
            raise ValueError(f"row {index} pdf_page mismatch for chunk_id {chunk_id}: JSONL {pdf_page}, NPZ {npz_data['pdf_pages'][index]}")


def validate_inputs(chunks_path: Path, embeddings_path: Path, manifest_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    chunks = read_jsonl_chunks(chunks_path)
    npz_data = read_embeddings_npz(embeddings_path)
    manifest = read_manifest(manifest_path)
    validate_manifest(manifest, chunks_path, len(chunks))
    validate_alignment(chunks, npz_data)
    return chunks, npz_data, manifest


def build_milvus_records(chunks: list[dict[str, Any]], embeddings: np.ndarray, embedding_model_name: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for chunk, embedding in zip(chunks, embeddings, strict=True):
        records.append(
            {
                "chunk_id": chunk["chunk_id"],
                "document_id": chunk["document_id"],
                "pdf_page": int(chunk["pdf_page"]),
                "chunk_index": int(chunk["chunk_index"]),
                "category": chunk["category"],
                "content_hash": chunk["content_hash"],
                "model_name": embedding_model_name,
                "embedding": embedding.astype(np.float32).tolist(),
            }
        )
    return records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import local Medi knowledge chunks into PostgreSQL and Milvus.")
    parser.add_argument("--chunks", default="data/processed/knowledge_chunks.jsonl")
    parser.add_argument("--embeddings", default="data/processed/knowledge_embeddings.npz")
    parser.add_argument("--manifest", default="data/processed/embedding_manifest.json")
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--replace-document", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    start_time = time.perf_counter()
    chunks_path = resolve_project_path(args.chunks)
    embeddings_path = resolve_project_path(args.embeddings)
    manifest_path = resolve_project_path(args.manifest)

    if args.batch_size <= 0:
        raise SystemExit("--batch-size must be greater than 0")

    chunks, npz_data, manifest = validate_inputs(chunks_path, embeddings_path, manifest_path)
    embedding_model_name = str(manifest["model_name"])
    document_counts = Counter(str(row["document_id"]) for row in chunks)
    document_ids = sorted(document_counts)
    if args.replace_document and len(document_ids) != 1:
        raise SystemExit("--replace-document requires input data to contain exactly one document_id")

    repository: KnowledgeImportRepository | None = None
    milvus: MilvusService | None = None
    postgres_upserted = 0
    milvus_upserted = 0
    postgres_counts: dict[str, int] = {}
    milvus_counts: dict[str, int] = {}
    postgres_status = "not_started"
    milvus_status = "not_started"
    import_status = "failed"
    error: Exception | None = None

    try:
        repository = KnowledgeImportRepository()
        repository.initialize_schema()
        postgres_status = "schema_ready"

        milvus = MilvusService(dimension=EXPECTED_DIMENSION)
        milvus.connect()
        milvus.ensure_collection()
        milvus_status = "collection_ready"

        if args.replace_document:
            target_document_id = document_ids[0]
            existing_postgres = repository.count_by_document_id(target_document_id)
            existing_milvus = milvus.count_by_document_id(target_document_id)
            print(f"replace_document_target={target_document_id}")
            print(f"existing_postgres_count={existing_postgres}")
            print(f"existing_milvus_count={existing_milvus}")
            repository.delete_by_document_id(target_document_id)
            milvus.delete_by_document_id(target_document_id)

        postgres_upserted = repository.upsert_chunks(chunks, embedding_model_name=embedding_model_name, batch_size=args.batch_size)
        postgres_status = "upsert_complete"

        milvus_records = build_milvus_records(chunks, npz_data["embeddings"], embedding_model_name)
        milvus_upserted = milvus.upsert_embeddings(milvus_records, batch_size=args.batch_size)
        milvus_status = "upsert_complete"

        postgres_counts = {document_id: repository.count_by_document_id(document_id) for document_id in document_ids}
        milvus_counts = {document_id: milvus.count_by_document_id(document_id) for document_id in document_ids}
        if postgres_counts == dict(document_counts) and milvus_counts == dict(document_counts):
            import_status = "success"
        else:
            import_status = "verification_failed"
    except Exception as exc:
        error = exc
        if postgres_status == "upsert_complete" and milvus_status != "upsert_complete":
            milvus_status = "failed_after_postgres"
        elif milvus_status == "upsert_complete" and postgres_status != "upsert_complete":
            postgres_status = "failed_after_milvus"
    finally:
        if milvus is not None:
            milvus.close()
        if repository is not None:
            repository.close()

        norms = npz_data.get("norms")
        collection_name = getattr(milvus, "collection_name", "")
        stats = {
            "validated_chunks": len(chunks),
            "embedding_dimension": EXPECTED_DIMENSION,
            "document_ids": document_ids,
            "postgres_upserted": postgres_upserted,
            "milvus_upserted": milvus_upserted,
            "postgres_counts": postgres_counts,
            "milvus_counts": milvus_counts,
            "batch_size": args.batch_size,
            "elapsed_seconds": round(time.perf_counter() - start_time, 3),
            "postgres_status": postgres_status,
            "milvus_status": milvus_status,
            "import_status": import_status,
            "collection_name": collection_name,
            "embedding_norm_min": None if norms is None or len(norms) == 0 else round(float(np.min(norms)), 6),
            "embedding_norm_avg": None if norms is None or len(norms) == 0 else round(float(np.mean(norms)), 6),
            "embedding_norm_max": None if norms is None or len(norms) == 0 else round(float(np.max(norms)), 6),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        for key, value in stats.items():
            print(f"{key}={json.dumps(value, ensure_ascii=False)}")

    if error is not None:
        raise SystemExit(str(error)) from error
    if import_status != "success":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
