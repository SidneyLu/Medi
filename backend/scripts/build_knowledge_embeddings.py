from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.embedding_service import EmbeddingService


DEFAULT_INPUT = PROJECT_ROOT / "data" / "processed" / "knowledge_chunks.jsonl"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "processed" / "knowledge_embeddings.npz"
DEFAULT_MANIFEST = PROJECT_ROOT / "data" / "processed" / "embedding_manifest.json"
EXPECTED_DIMENSION = 512


def main() -> None:
    parser = argparse.ArgumentParser(description="Build local embeddings for MSD knowledge chunks.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Knowledge chunks JSONL input path.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Compressed NPZ embedding output path.")
    parser.add_argument("--manifest-output", default=str(DEFAULT_MANIFEST), help="Embedding manifest JSON output path.")
    parser.add_argument("--model-name", default="BAAI/bge-small-zh-v1.5", help="Local sentence-transformers model name or path.")
    parser.add_argument("--device", default="cpu", choices=["cpu", "cuda", "auto"], help="Embedding device.")
    parser.add_argument("--batch-size", type=int, default=32, help="Embedding batch size.")
    parser.add_argument("--start-index", type=int, default=None, help="Optional zero-based inclusive start index.")
    parser.add_argument("--end-index", type=int, default=None, help="Optional zero-based exclusive end index.")
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    manifest_path = Path(args.manifest_output).expanduser().resolve()
    if args.batch_size <= 0:
        raise SystemExit("batch-size must be greater than zero")
    if not input_path.exists():
        raise SystemExit(f"Input file does not exist: {input_path}")
    if args.start_index is not None and args.start_index < 0:
        raise SystemExit("start-index must not be negative")
    if args.end_index is not None and args.end_index < 0:
        raise SystemExit("end-index must not be negative")
    if args.start_index is not None and args.end_index is not None and args.start_index > args.end_index:
        raise SystemExit("start-index must be less than or equal to end-index")

    started = time.perf_counter()
    all_chunks = read_and_validate_chunks(input_path)
    selected_start_index = args.start_index if args.start_index is not None else 0
    selected_end_index = args.end_index if args.end_index is not None else len(all_chunks)
    selected_chunks = all_chunks[slice(args.start_index, args.end_index)]
    if not selected_chunks:
        raise SystemExit("start-index and end-index did not select any knowledge chunks")
    service = EmbeddingService(
        model_name=args.model_name,
        device=args.device,
        batch_size=args.batch_size,
        normalize_embeddings=True,
        expected_dimension=EXPECTED_DIMENSION,
    )
    embeddings = service.encode_documents([str(item["content"]) for item in selected_chunks])
    chunk_ids = np.asarray([str(item["chunk_id"]) for item in selected_chunks])
    content_hashes = np.asarray([str(item["content_hash"]) for item in selected_chunks])
    pdf_pages = np.asarray([int(item["pdf_page"]) for item in selected_chunks], dtype=np.int64)
    validate_embedding_output(
        embeddings=embeddings,
        chunk_ids=chunk_ids,
        content_hashes=content_hashes,
        pdf_pages=pdf_pages,
        input_count=len(selected_chunks),
        expected_dimension=EXPECTED_DIMENSION,
    )
    write_npz_atomic(
        output_path,
        embeddings=embeddings,
        chunk_ids=chunk_ids,
        content_hashes=content_hashes,
        pdf_pages=pdf_pages,
    )
    manifest = build_manifest(
        model_name=args.model_name,
        embedding_dimension=EXPECTED_DIMENSION,
        chunk_count=len(selected_chunks),
        source_chunk_count=len(all_chunks),
        selected_start_index=selected_start_index,
        selected_end_index=selected_end_index,
        input_file=str(input_path),
        input_sha256=file_sha256(input_path),
        device=service.config.device,
        batch_size=args.batch_size,
    )
    write_json_atomic(manifest_path, manifest)
    norms = np.linalg.norm(embeddings, axis=1) if len(embeddings) else np.asarray([], dtype=np.float32)
    elapsed = time.perf_counter() - started
    print(f"source_chunks={len(all_chunks)}")
    print(f"embedded_chunks={len(selected_chunks)}")
    print(f"embedding_dimension={EXPECTED_DIMENSION}")
    print(f"model_name={args.model_name}")
    print(f"device={service.config.device}")
    print(f"batch_size={args.batch_size}")
    print(f"minimum_norm={float(norms.min()) if len(norms) else 0.0:.6f}")
    print(f"average_norm={float(norms.mean()) if len(norms) else 0.0:.6f}")
    print(f"maximum_norm={float(norms.max()) if len(norms) else 0.0:.6f}")
    print(f"elapsed_seconds={elapsed:.3f}")
    print(f"output={output_path}")
    print(f"manifest_output={manifest_path}")


def read_and_validate_chunks(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                record = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"record must be a JSON object at {path}:{line_number}")
            chunk_id = str(record.get("chunk_id") or "")
            if not chunk_id:
                raise ValueError(f"chunk_id must not be empty at {path}:{line_number}")
            if chunk_id in seen:
                raise ValueError(f"duplicate chunk_id at {path}:{line_number}: {chunk_id}")
            seen.add(chunk_id)
            if not str(record.get("content") or "").strip():
                raise ValueError(f"content must not be empty for chunk_id {chunk_id}")
            content = str(record.get("content") or "")
            content_hash = str(record.get("content_hash") or "").strip()
            if not content_hash:
                raise ValueError(f"content_hash must not be empty for chunk_id {chunk_id}")
            expected_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            if content_hash != expected_hash:
                raise ValueError(
                    f"content_hash mismatch at {path}:{line_number}, chunk_id {chunk_id}, "
                    f"expected hash {expected_hash}, actual hash {content_hash}"
                )
            pdf_page = int(record.get("pdf_page") or 0)
            if pdf_page <= 0:
                raise ValueError(f"pdf_page must be a positive integer for chunk_id {chunk_id}")
            records.append(record)
    return records


def validate_embedding_output(
    *,
    embeddings: np.ndarray,
    chunk_ids: np.ndarray,
    content_hashes: np.ndarray,
    pdf_pages: np.ndarray,
    input_count: int,
    expected_dimension: int,
) -> None:
    if embeddings.shape[0] != len(chunk_ids):
        raise ValueError("embeddings row count must equal chunk_ids count")
    if embeddings.shape[0] != len(content_hashes):
        raise ValueError("embeddings row count must equal content_hashes count")
    if embeddings.shape[0] != len(pdf_pages):
        raise ValueError("embeddings row count must equal pdf_pages count")
    if embeddings.shape[0] != input_count:
        raise ValueError("input record count must equal output embedding count")
    if embeddings.ndim != 2 or embeddings.shape[1] != expected_dimension:
        raise ValueError(f"embeddings shape must be [N, {expected_dimension}], got {embeddings.shape}")
    if embeddings.dtype != np.float32:
        raise ValueError(f"embeddings dtype must be float32, got {embeddings.dtype}")
    if pdf_pages.dtype != np.int64:
        raise ValueError(f"pdf_pages dtype must be int64, got {pdf_pages.dtype}")
    if not np.all(np.isfinite(embeddings)):
        raise ValueError("embeddings must not contain NaN or Infinity")
    if len(set(str(item) for item in chunk_ids.tolist())) != len(chunk_ids):
        raise ValueError("chunk_ids must be unique")
    if len(embeddings):
        norms = np.linalg.norm(embeddings, axis=1)
        if np.any((norms < 0.99) | (norms > 1.01)):
            raise ValueError("all embedding L2 norms must be between 0.99 and 1.01")


def write_npz_atomic(path: Path, **arrays: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")
    with temp_path.open("wb") as file:
        np.savez_compressed(file, **arrays)
        file.flush()
    with np.load(temp_path, allow_pickle=False) as data:
        validate_embedding_output(
            embeddings=data["embeddings"],
            chunk_ids=data["chunk_ids"],
            content_hashes=data["content_hashes"],
            pdf_pages=data["pdf_pages"],
            input_count=len(arrays["chunk_ids"]),
            expected_dimension=EXPECTED_DIMENSION,
        )
    replace_with_retry(temp_path, path)


def build_manifest(
    *,
    model_name: str,
    embedding_dimension: int,
    chunk_count: int,
    source_chunk_count: int,
    selected_start_index: int,
    selected_end_index: int,
    input_file: str,
    input_sha256: str,
    device: str,
    batch_size: int,
) -> dict[str, Any]:
    return {
        "model_name": model_name,
        "embedding_dimension": embedding_dimension,
        "normalized": True,
        "chunk_count": chunk_count,
        "source_chunk_count": source_chunk_count,
        "selected_start_index": selected_start_index,
        "selected_end_index": selected_end_index,
        "input_file": input_file,
        "input_sha256": input_sha256,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "device": device,
        "batch_size": batch_size,
    }


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")
    with temp_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2, sort_keys=True)
        file.write("\n")
        file.flush()
    replace_with_retry(temp_path, path)


def replace_with_retry(temp_path: Path, target_path: Path) -> None:
    last_error: PermissionError | None = None
    for attempt in range(1, 21):
        try:
            temp_path.replace(target_path)
            return
        except PermissionError as exc:
            last_error = exc
            if attempt >= 20:
                break
            print(f"output file is temporarily locked, retrying {attempt}/20")
            time.sleep(0.5)
    if last_error is not None:
        raise last_error


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
