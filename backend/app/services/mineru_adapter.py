"""Normalize MinerU content-list output into stable, page-addressable text chunks."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class ParsedBlock:
    page_number: int
    kind: str
    text: str
    bbox: list[float] | None
    level: int | None = None


@dataclass(frozen=True)
class ParsedChunk:
    chunk_id: str
    section_id: str
    article_title: str
    section_title: str
    heading_path: list[str]
    page_start: int
    page_end: int
    source_bboxes: list[dict[str, Any]]
    content: str
    source_excerpt: str
    content_hash: str


def load_mineru_blocks(parsed_dir: Path) -> list[ParsedBlock]:
    """Accept common MinerU content-list JSON shapes without coupling to one release."""
    candidates = list(parsed_dir.rglob("content_list.json")) + list(parsed_dir.rglob("*.json"))
    for path in candidates:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        records = raw.get("content_list") if isinstance(raw, dict) else raw
        if not isinstance(records, list):
            continue
        blocks = [_to_block(item) for item in records if isinstance(item, dict)]
        normalized = [block for block in blocks if block is not None]
        if normalized:
            return normalized
    raise ValueError(f"No MinerU content-list JSON was found below {parsed_dir}")


def _to_block(item: dict[str, Any]) -> ParsedBlock | None:
    kind = str(item.get("type") or item.get("block_type") or "text").lower()
    text = item.get("text") or item.get("content") or item.get("table_body") or ""
    if isinstance(text, list):
        text = "\n".join(str(value) for value in text)
    text = _clean_text(str(text))
    if not text:
        return None
    page = item.get("page_idx", item.get("page_no", item.get("page_number", 0)))
    try:
        page_number = int(page) + 1 if "page_idx" in item else int(page)
    except (TypeError, ValueError):
        page_number = 1
    bbox = item.get("bbox") or item.get("box")
    if not isinstance(bbox, list) or len(bbox) != 4:
        bbox = None
    level = item.get("text_level") or item.get("level")
    return ParsedBlock(page_number=max(1, page_number), kind=kind, text=text, bbox=bbox, level=int(level) if str(level).isdigit() else None)


def build_chunks(document_sha: str, title: str, blocks: Iterable[ParsedBlock], chunk_chars: int = 900) -> list[ParsedChunk]:
    path: list[str] = [title]
    pending: list[ParsedBlock] = []
    chunks: list[ParsedChunk] = []

    def flush() -> None:
        nonlocal pending
        if not pending:
            return
        text = "\n\n".join(block.text for block in pending)
        for index, part in enumerate(_split_text(text, chunk_chars)):
            matching = pending if index == 0 else [pending[-1]]
            page_start = min(block.page_number for block in matching)
            page_end = max(block.page_number for block in matching)
            bboxes = [{"page": block.page_number, "bbox": block.bbox} for block in matching if block.bbox]
            material = f"{document_sha}|{' > '.join(path)}|{page_start}|{part}"
            content_hash = hashlib.sha256(material.encode("utf-8")).hexdigest()
            chunk_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"medi-pdf:{content_hash}"))
            section_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"medi-section:{document_sha}:{' > '.join(path)}"))
            chunks.append(ParsedChunk(chunk_id, section_id, title, path[-1], list(path), page_start, page_end, bboxes, part, part[:360], content_hash))
        pending = []

    for block in blocks:
        if block.kind in {"title", "heading", "h1", "h2", "h3"}:
            flush()
            level = block.level or (1 if block.kind in {"title", "h1"} else 2)
            path = path[:max(1, level)]
            path.append(block.text)
            continue
        pending.append(block)
        if sum(len(item.text) for item in pending) >= chunk_chars * 2:
            flush()
    flush()
    return chunks


def _clean_text(value: str) -> str:
    return re.sub(r"[ \t]+", " ", re.sub(r"\n{3,}", "\n\n", value)).strip()


def _split_text(value: str, chunk_chars: int) -> list[str]:
    paragraphs = [part.strip() for part in value.split("\n\n") if part.strip()]
    result: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(current) + len(paragraph) + 2 <= chunk_chars:
            current = f"{current}\n\n{paragraph}".strip()
            continue
        if current:
            result.append(current)
        while len(paragraph) > chunk_chars:
            cut = max(paragraph.rfind("。", 0, chunk_chars), paragraph.rfind("；", 0, chunk_chars), chunk_chars)
            result.append(paragraph[:cut].strip())
            paragraph = paragraph[cut:].strip()
        current = paragraph
    if current:
        result.append(current)
    return result
