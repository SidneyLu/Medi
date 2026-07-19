from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import fitz

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.local_pdf_ocr import LocalPdfOcrProcessor, write_json_atomic
from app.services.pdf_page_processor import document_id_from_path


DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "processed" / "msd_pages.jsonl"
DEFAULT_RAW_OUTPUT = PROJECT_ROOT / "data" / "processed" / "raw_local"
DEFAULT_ERROR_OUTPUT = PROJECT_ROOT / "data" / "processed" / "local_ocr_errors.jsonl"
DEFAULT_TMP_OUTPUT = PROJECT_ROOT / "data" / "processed" / "tmp" / "local_pdf_ocr"


def main() -> None:
    parser = argparse.ArgumentParser(description="Process scanned medical PDF pages with local PaddleOCR.")
    parser.add_argument("--pdf", required=True, help="Local scanned PDF path.")
    parser.add_argument("--start-page", type=int, required=True, help="First 1-based PDF page to process.")
    parser.add_argument("--end-page", type=int, required=True, help="Last 1-based PDF page to process.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Clean JSONL output path.")
    parser.add_argument("--raw-output", default=str(DEFAULT_RAW_OUTPUT), help="Directory for local raw OCR JSON files.")
    parser.add_argument("--error-output", default=str(DEFAULT_ERROR_OUTPUT), help="Error JSONL output path.")
    parser.add_argument("--render-scale", type=float, default=2.0, help="PyMuPDF render scale.")
    parser.add_argument("--max-image-size", type=int, default=2400, help="Maximum rendered image side length in pixels.")
    parser.add_argument("--min-confidence", type=float, default=0.5, help="Minimum OCR line confidence.")
    parser.add_argument("--device", default="cpu", choices=["cpu", "gpu", "cuda"], help="PaddleOCR device.")
    args = parser.parse_args()

    pdf_path = Path(args.pdf).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    raw_output_dir = Path(args.raw_output).expanduser().resolve()
    error_output_path = Path(args.error_output).expanduser().resolve()
    _validate_inputs(pdf_path, args.start_page, args.end_page)

    document_id = document_id_from_path(pdf_path)
    raw_document_dir = raw_output_dir / document_id
    image_dir = DEFAULT_TMP_OUTPUT / document_id
    requested_pages = list(range(args.start_page, args.end_page + 1))
    existing_records = _read_jsonl_records(output_path)
    existing_by_page = {
        int(record["pdf_page"]): record
        for record in existing_records
        if record.get("document_id") == document_id
    }
    pages_to_process = [page for page in requested_pages if page not in existing_by_page]
    records_by_key = {
        (str(record.get("document_id") or ""), int(record.get("pdf_page") or 0)): record
        for record in existing_records
        if record.get("document_id") and int(record.get("pdf_page") or 0) > 0
    }

    raw_document_dir.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    error_output_path.parent.mkdir(parents=True, exist_ok=True)
    image_dir.mkdir(parents=True, exist_ok=True)

    processor = LocalPdfOcrProcessor(
        render_scale=args.render_scale,
        max_image_size=args.max_image_size,
        min_confidence=args.min_confidence,
        device=args.device,
    )
    stats = {
        "requested_pages": len(pages_to_process),
        "processed_pages": 0,
        "skipped_pages": len(requested_pages) - len(pages_to_process),
        "failed_pages": 0,
        "seconds": 0.0,
    }

    with error_output_path.open("a", encoding="utf-8") as error_file:
        for pdf_page in pages_to_process:
            result = processor.process_page(pdf_path, document_id=document_id, pdf_page=pdf_page, image_dir=image_dir)
            stats["seconds"] += result.seconds
            if result.raw_record is not None:
                write_json_atomic(raw_document_dir / f"page_{pdf_page:04d}.json", result.raw_record)
            if result.record is not None:
                records_by_key[(document_id, pdf_page)] = result.record
                _write_sorted_records(output_path, list(records_by_key.values()))
                stats["processed_pages"] += 1
            else:
                _append_jsonl(error_file, result.error or {"pdf_page": pdf_page, "error": "unknown error"})
                stats["failed_pages"] += 1

    searchable_pages = sum(
        1
        for record in records_by_key.values()
        if record.get("document_id") == document_id and record.get("searchable")
    )
    average = stats["seconds"] / stats["processed_pages"] if stats["processed_pages"] else 0.0
    print(f"requested_pages={stats['requested_pages']}")
    print(f"processed_pages={stats['processed_pages']}")
    print(f"skipped_pages={stats['skipped_pages']}")
    print(f"failed_pages={stats['failed_pages']}")
    print(f"searchable_pages={searchable_pages}")
    print(f"average_seconds_per_page={average:.3f}")
    print(f"output={output_path}")
    print(f"raw_output={raw_document_dir}")
    print(f"error_output={error_output_path}")


def _validate_inputs(pdf_path: Path, start_page: int, end_page: int) -> int:
    if not pdf_path.exists():
        raise SystemExit(f"PDF file does not exist: {pdf_path}")
    if not pdf_path.is_file():
        raise SystemExit(f"PDF path is not a file: {pdf_path}")
    if start_page < 1 or end_page < 1:
        raise SystemExit("start-page and end-page must be 1-based positive integers")
    if start_page > end_page:
        raise SystemExit("start-page must be less than or equal to end-page")
    try:
        with fitz.open(pdf_path) as document:
            total_pages = document.page_count
    except Exception as exc:
        raise SystemExit(f"PDF cannot be opened: {exc}") from exc
    if end_page > total_pages:
        raise SystemExit(f"end-page {end_page} exceeds PDF page count {total_pages}")
    return total_pages


def _read_jsonl_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                data = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
            if isinstance(data, dict):
                records.append(data)
    return records


def _write_sorted_records(path: Path, records: list[dict[str, Any]]) -> None:
    deduped: dict[tuple[str, int], dict[str, Any]] = {}
    for record in records:
        document_id = str(record.get("document_id") or "")
        pdf_page = int(record.get("pdf_page") or 0)
        if document_id and pdf_page > 0:
            deduped[(document_id, pdf_page)] = record
    ordered = sorted(deduped.values(), key=lambda item: (str(item.get("document_id") or ""), int(item.get("pdf_page") or 0)))
    temp_path = path.with_name(f"{path.name}.tmp")
    with temp_path.open("w", encoding="utf-8") as file:
        for record in ordered:
            file.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            file.flush()
    temp_path.replace(path)


def _append_jsonl(file: Any, data: dict[str, Any]) -> None:
    file.write(json.dumps(data, ensure_ascii=False, sort_keys=True) + "\n")
    file.flush()


if __name__ == "__main__":
    main()
