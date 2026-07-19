from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any


ARTICLE_TITLE = "MSD诊疗手册大众版"
CATEGORY = "MSD诊疗手册"
MAX_PDF_PAGE = 1582
SENTENCE_END_PATTERN = re.compile(r"([^。！？；]*[。！？；])")


@dataclass(frozen=True)
class ChunkingConfig:
    target_chars: int = 600
    max_chars: int = 800
    overlap_chars: int = 100


@dataclass(frozen=True)
class ChunkingStats:
    duplicate_chunks_removed: int
    minimum_chunk_chars: int
    average_chunk_chars: float
    maximum_chunk_chars: int


class KnowledgeChunker:
    def __init__(self, config: ChunkingConfig | None = None) -> None:
        self.config = config or ChunkingConfig()
        if self.config.target_chars <= 0:
            raise ValueError("target_chars must be greater than zero")
        if self.config.max_chars <= 0:
            raise ValueError("max_chars must be greater than zero")
        if self.config.overlap_chars < 0:
            raise ValueError("overlap_chars must not be negative")
        if self.config.target_chars > self.config.max_chars:
            raise ValueError("target_chars must be less than or equal to max_chars")

    def build_page_chunks(self, page: dict[str, Any]) -> list[dict[str, Any]]:
        if not is_processable_page(page):
            return []
        document_id = str(page.get("document_id") or "")
        pdf_page = int(page.get("pdf_page") or 0)
        section_title = section_title_for_page(page)
        page_text = build_page_text(page, section_title)
        content_config = content_body_config(section_title, self.config)
        text_chunks = split_text(page_text, content_config)
        records = []
        chunk_count = len(text_chunks)
        for chunk_index, text in enumerate(text_chunks):
            content = build_content(section_title, text)
            if not content:
                continue
            content_hash = sha256_text(content)
            record = {
                "chunk_id": stable_chunk_id(document_id, pdf_page, chunk_index, content_hash),
                "document_id": document_id,
                "pdf_page": pdf_page,
                "printed_page": page.get("printed_page"),
                "chunk_index": chunk_index,
                "chunk_count": chunk_count,
                "article_title": ARTICLE_TITLE,
                "section_title": section_title,
                "source_url": f"msd-pdf://{document_id}/page/{pdf_page}",
                "category": CATEGORY,
                "content": content,
                "tags": build_tags(page),
                "version_label": str(page.get("version_label") or document_id[:12]),
                "revised_at": page.get("revised_at"),
                "content_hash": content_hash,
                "model_name": str(page.get("model_name") or ""),
                "searchable": True,
            }
            records.append(record)
        return records


def is_processable_page(page: dict[str, Any]) -> bool:
    if page.get("searchable") is not True:
        return False
    return any(str(page.get(field) or "").strip() for field in ("search_text", "body_text", "table_text", "figure_text"))


def section_title_for_page(page: dict[str, Any]) -> str:
    title = clean_text(str(page.get("title") or ""))
    if title:
        return title
    return f"PDF第{int(page.get('pdf_page') or 0)}页"


def build_page_text(page: dict[str, Any], section_title: str) -> str:
    body_text = remove_first_line_if_same(str(page.get("body_text") or ""), section_title)
    parts = [
        body_text,
        str(page.get("table_text") or ""),
        str(page.get("figure_text") or ""),
    ]
    combined = "\n\n".join(clean_text(part) for part in parts if clean_text(part))
    if combined:
        return combined
    fallback = remove_first_line_if_same(str(page.get("search_text") or ""), section_title)
    return clean_text(fallback)


def content_body_config(section_title: str, config: ChunkingConfig) -> ChunkingConfig:
    title = clean_text(section_title)
    title_overhead = len(title) + (1 if title else 0)
    body_max_chars = config.max_chars - title_overhead
    if body_max_chars <= 0:
        body_max_chars = config.max_chars
    body_target_chars = min(config.target_chars, body_max_chars)
    body_overlap_chars = min(config.overlap_chars, max(0, body_max_chars - 1))
    return ChunkingConfig(
        target_chars=max(1, body_target_chars),
        max_chars=max(1, body_max_chars),
        overlap_chars=body_overlap_chars,
    )


def build_content(section_title: str, text: str) -> str:
    title = clean_text(section_title)
    body = clean_text(text)
    if not body:
        return title
    if body == title:
        return title
    return f"{title}\n{body}" if title else body


def split_text(text: str, config: ChunkingConfig) -> list[str]:
    normalized = clean_text(text)
    if not normalized:
        return []
    if len(normalized) <= config.max_chars:
        return [normalized]
    units = split_to_units(normalized, config.max_chars)
    chunks = pack_units(units, config)
    return remove_duplicate_chunks(chunks)


def split_to_units(text: str, max_chars: int) -> list[str]:
    paragraphs = split_paragraphs(text)
    units: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= max_chars:
            units.append(paragraph)
            continue
        sentences = split_sentences(paragraph)
        for sentence in sentences:
            if len(sentence) <= max_chars:
                units.append(sentence)
            else:
                units.extend(hard_split(sentence, max_chars))
    return [unit for unit in units if unit.strip()]


def split_paragraphs(text: str) -> list[str]:
    blocks = re.split(r"\n\s*\n|\n", text)
    return [clean_text(block) for block in blocks if clean_text(block)]


def split_sentences(text: str) -> list[str]:
    sentences = []
    cursor = 0
    for match in SENTENCE_END_PATTERN.finditer(text):
        sentence = text[cursor : match.end()].strip()
        if sentence:
            sentences.append(sentence)
        cursor = match.end()
    tail = text[cursor:].strip()
    if tail:
        sentences.append(tail)
    return sentences or [text]


def hard_split(text: str, max_chars: int) -> list[str]:
    return [text[index : index + max_chars].strip() for index in range(0, len(text), max_chars) if text[index : index + max_chars].strip()]


def pack_units(units: list[str], config: ChunkingConfig) -> list[str]:
    chunks: list[str] = []
    current = ""
    current_has_new_content = False
    for unit in units:
        candidate = join_text(current, unit)
        if current and len(candidate) > config.max_chars:
            if current_has_new_content:
                chunks.append(current)
            current = join_text(overlap_tail_for_unit(current, unit, config.max_chars, config.overlap_chars), unit)
            current_has_new_content = True
            if len(current) > config.max_chars:
                split_current = hard_split_preserving_new_text(current, config.max_chars)
                chunks.extend(split_current[:-1])
                current = split_current[-1] if split_current else ""
                current_has_new_content = bool(current)
        else:
            current = candidate
            current_has_new_content = True
        if len(current) >= config.target_chars:
            chunks.append(current)
            current = overlap_tail(current, config.overlap_chars)
            current_has_new_content = False
    if current and current not in chunks and (current_has_new_content or not chunks):
        chunks.append(current)
    return [clean_text(chunk) for chunk in chunks if clean_text(chunk)]


def join_text(left: str, right: str) -> str:
    if not left:
        return right.strip()
    if not right:
        return left.strip()
    return f"{left.strip()}\n{right.strip()}"


def overlap_tail(text: str, overlap_chars: int) -> str:
    if overlap_chars <= 0:
        return ""
    return text[-overlap_chars:].strip()


def overlap_tail_for_unit(previous: str, unit: str, max_chars: int, requested_overlap: int) -> str:
    if requested_overlap <= 0:
        return ""
    available = max_chars - len(unit.strip()) - 1
    if available <= 0:
        return ""
    return overlap_tail(previous, min(requested_overlap, available))


def hard_split_preserving_new_text(text: str, max_chars: int) -> list[str]:
    return hard_split(text, max_chars)


def remove_duplicate_chunks(chunks: list[str]) -> list[str]:
    seen: set[str] = set()
    result = []
    for chunk in chunks:
        normalized = clean_text(chunk)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def build_tags(page: dict[str, Any]) -> list[str]:
    pdf_page = int(page.get("pdf_page") or 0)
    model_name = str(page.get("model_name") or "")
    tags = ["source:msd", f"pdf_page:{pdf_page}", f"model:{model_name}"]
    printed_page = page.get("printed_page")
    if printed_page is not None and str(printed_page) != "":
        tags.append(f"printed_page:{printed_page}")
    return tags


def stable_chunk_id(document_id: str, pdf_page: int, chunk_index: int, content_hash: str) -> str:
    return sha256_text(f"{document_id}|{pdf_page}|{chunk_index}|{content_hash}")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def remove_first_line_if_same(text: str, title: str) -> str:
    if not text or not title:
        return text
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        if line.strip() != title:
            return text
        return "\n".join(lines[:index] + lines[index + 1 :]).strip("\n")
    return text


def clean_text(text: str) -> str:
    text = text.replace("\r", "\n")
    lines = [re.sub(r"[ \t\u00a0\u3000]+", " ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line).strip()


def dedupe_chunks(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    seen: set[str] = set()
    result = []
    removed = 0
    for record in records:
        chunk_id = str(record.get("chunk_id") or "")
        if chunk_id in seen:
            removed += 1
            continue
        seen.add(chunk_id)
        result.append(record)
    return result, removed


def sort_chunks(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(records, key=lambda item: (str(item.get("document_id") or ""), int(item.get("pdf_page") or 0), int(item.get("chunk_index") or 0)))


def validate_chunks(records: list[dict[str, Any]], max_chars: int | None = None) -> None:
    ids: set[str] = set()
    by_page: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for record in records:
        chunk_id = str(record.get("chunk_id") or "")
        if not chunk_id:
            raise ValueError("chunk_id must not be empty")
        if chunk_id in ids:
            raise ValueError(f"duplicate chunk_id: {chunk_id}")
        ids.add(chunk_id)
        document_id = str(record.get("document_id") or "")
        if not document_id:
            raise ValueError(f"document_id must not be empty for chunk_id {chunk_id}")
        section_title = str(record.get("section_title") or "").strip()
        if not section_title:
            raise ValueError(f"section_title must not be empty for chunk_id {chunk_id}")
        content = str(record.get("content") or "")
        if not content.strip():
            raise ValueError(f"content must not be empty for chunk_id {chunk_id}")
        if max_chars is not None and len(content) > max_chars:
            pdf_page_for_error = int(record.get("pdf_page") or 0)
            raise ValueError(
                f"content length exceeds max_chars for chunk_id {chunk_id}, "
                f"pdf_page {pdf_page_for_error}, actual {len(content)}, max {max_chars}"
            )
        content_hash = str(record.get("content_hash") or "")
        if not content_hash:
            raise ValueError(f"content_hash must not be empty for chunk_id {chunk_id}")
        expected_content_hash = sha256_text(content)
        if content_hash != expected_content_hash:
            raise ValueError(f"content_hash mismatch for chunk_id {chunk_id}")
        pdf_page = int(record.get("pdf_page") or 0)
        if pdf_page < 1 or pdf_page > MAX_PDF_PAGE:
            raise ValueError(f"pdf_page out of range for chunk_id {chunk_id}: {pdf_page}")
        chunk_index = int(record.get("chunk_index") or 0)
        if chunk_index < 0:
            raise ValueError(f"chunk_index must not be negative for chunk_id {chunk_id}")
        chunk_count = int(record.get("chunk_count") or 0)
        if chunk_count <= 0:
            raise ValueError(f"chunk_count must be greater than zero for chunk_id {chunk_id}")
        page_key = (document_id, pdf_page)
        by_page.setdefault(page_key, []).append(record)
        expected_url = f"msd-pdf://{page_key[0]}/page/{pdf_page}"
        if record.get("source_url") != expected_url:
            raise ValueError(f"source_url does not match pdf_page for chunk_id {chunk_id}")
    for page_key, page_records in by_page.items():
        sorted_page_records = sorted(page_records, key=lambda item: int(item.get("chunk_index") or 0))
        expected_indexes = list(range(len(sorted_page_records)))
        actual_indexes = [int(item["chunk_index"]) for item in sorted_page_records]
        if actual_indexes != expected_indexes:
            raise ValueError(f"chunk_index must be continuous for page {page_key}: {actual_indexes}")
        expected_count = len(sorted_page_records)
        for item in sorted_page_records:
            if int(item.get("chunk_count") or 0) != expected_count:
                raise ValueError(f"chunk_count mismatch for page {page_key}")


def chunk_length_stats(records: list[dict[str, Any]]) -> ChunkingStats:
    lengths = [len(str(record.get("content") or "")) for record in records]
    if not lengths:
        return ChunkingStats(duplicate_chunks_removed=0, minimum_chunk_chars=0, average_chunk_chars=0.0, maximum_chunk_chars=0)
    return ChunkingStats(
        duplicate_chunks_removed=0,
        minimum_chunk_chars=min(lengths),
        average_chunk_chars=sum(lengths) / len(lengths),
        maximum_chunk_chars=max(lengths),
    )
