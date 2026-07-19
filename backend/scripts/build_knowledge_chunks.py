from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.knowledge_chunker import (
    ChunkingConfig,
    KnowledgeChunker,
    chunk_length_stats,
    dedupe_chunks,
    is_processable_page,
    sort_chunks,
    validate_chunks,
)


DEFAULT_INPUT = PROJECT_ROOT / "data" / "processed" / "msd_pages.jsonl"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "processed" / "knowledge_chunks.jsonl"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build MSD knowledge chunks from processed OCR pages.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Processed page JSONL input path.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Knowledge chunks JSONL output path.")
    parser.add_argument("--start-page", type=int, default=None, help="Optional first 1-based PDF page to include.")
    parser.add_argument("--end-page", type=int, default=None, help="Optional last 1-based PDF page to include.")
    parser.add_argument("--target-chars", type=int, default=600, help="Target chunk character count.")
    parser.add_argument("--max-chars", type=int, default=800, help="Maximum chunk character count.")
    parser.add_argument("--overlap-chars", type=int, default=100, help="Chunk overlap character count.")
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    if not input_path.exists():
        raise SystemExit(f"Input file does not exist: {input_path}")
    if args.start_page is not None and args.start_page < 1:
        raise SystemExit("start-page must be greater than zero")
    if args.end_page is not None and args.end_page < 1:
        raise SystemExit("end-page must be greater than zero")
    if args.start_page is not None and args.end_page is not None and args.start_page > args.end_page:
        raise SystemExit("start-page must be less than or equal to end-page")

    source_records = read_jsonl(input_path)
    unique_pages = select_unique_pages(source_records, start_page=args.start_page, end_page=args.end_page)
    searchable_pages = [record for record in unique_pages if record.get("searchable") is True]
    selected_pages = [record for record in unique_pages if is_processable_page(record)]

    chunker = KnowledgeChunker(ChunkingConfig(target_chars=args.target_chars, max_chars=args.max_chars, overlap_chars=args.overlap_chars))
    all_chunks = []
    pages_with_chunks = 0
    pages_without_chunks = 0
    for page in selected_pages:
        page_chunks = chunker.build_page_chunks(page)
        if page_chunks:
            pages_with_chunks += 1
            all_chunks.extend(page_chunks)
        else:
            pages_without_chunks += 1

    deduped_chunks, duplicate_chunks_removed = dedupe_chunks(all_chunks)
    sorted_chunks = sort_chunks(deduped_chunks)
    validate_chunks(sorted_chunks, max_chars=args.max_chars)
    write_jsonl_atomic(output_path, sorted_chunks)
    stats = chunk_length_stats(sorted_chunks)

    print(f"source_records={len(source_records)}")
    print(f"selected_pages={len(selected_pages)}")
    print(f"searchable_pages={len(searchable_pages)}")
    print(f"skipped_pages={len(unique_pages) - len(selected_pages)}")
    print(f"generated_chunks={len(sorted_chunks)}")
    print(f"pages_with_chunks={pages_with_chunks}")
    print(f"pages_without_chunks={pages_without_chunks}")
    print(f"duplicate_chunks_removed={duplicate_chunks_removed}")
    print(f"minimum_chunk_chars={stats.minimum_chunk_chars}")
    print(f"average_chunk_chars={stats.average_chunk_chars:.2f}")
    print(f"maximum_chunk_chars={stats.maximum_chunk_chars}")
    print(f"output={output_path}")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records = []
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
                raise ValueError(f"JSONL record must be an object at {path}:{line_number}")
            records.append(record)
    return records


def select_unique_pages(records: list[dict[str, Any]], *, start_page: int | None, end_page: int | None) -> list[dict[str, Any]]:
    selected = []
    seen: set[tuple[str, int]] = set()
    for record in records:
        pdf_page = int(record.get("pdf_page") or 0)
        if start_page is not None and pdf_page < start_page:
            continue
        if end_page is not None and pdf_page > end_page:
            continue
        document_id = str(record.get("document_id") or "")
        key = (document_id, pdf_page)
        if key in seen:
            continue
        seen.add(key)
        selected.append(record)
    return selected


def write_jsonl_atomic(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")
    with temp_path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            file.flush()
    for attempt in range(1, 21):
        try:
            temp_path.replace(path)
            return
        except PermissionError:
            if attempt >= 20:
                raise
            print(f"output file is temporarily locked, retrying {attempt}/20")
            time.sleep(0.5)


if __name__ == "__main__":
    main()
