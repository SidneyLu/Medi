from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

import jieba
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json

from app.services.mineru_adapter import ParsedChunk


class KnowledgeRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def initialize(self) -> None:
        schema_path = Path(__file__).resolve().parents[2] / "sql" / "knowledge_schema.sql"
        with self._connect() as conn:
            conn.execute(schema_path.read_text(encoding="utf-8"))

    def begin_run(self, source_sha256: str, parsed_path: str) -> str:
        run_id = str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO ingestion_runs (run_id, source_sha256, parsed_path, status) VALUES (%s, %s, %s, 'running')",
                (run_id, source_sha256, parsed_path),
            )
        return run_id

    def complete_run(self, run_id: str, document_id: str | None, pages_processed: int, chunks_written: int, error_message: str | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                """UPDATE ingestion_runs SET document_id=%s, pages_processed=%s, chunks_written=%s,
                   status=%s, error_message=%s, completed_at=now() WHERE run_id=%s""",
                (document_id, pages_processed, chunks_written, "failed" if error_message else "completed", error_message, run_id),
            )

    def upsert_document(self, source_path: Path, title: str, source_sha256: str, page_count: int, parser_version: str | None = None) -> str:
        document_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"medi-pdf:{source_sha256}"))
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO source_documents (document_id, source_sha256, title, source_path, page_count, parser_name, parser_version)
                   VALUES (%s,%s,%s,%s,%s,'MinerU',%s)
                   ON CONFLICT (source_sha256) DO UPDATE SET title=EXCLUDED.title, source_path=EXCLUDED.source_path,
                   page_count=EXCLUDED.page_count, parser_version=EXCLUDED.parser_version, updated_at=now()""",
                (document_id, source_sha256, title, str(source_path.resolve()), page_count, parser_version),
            )
        return document_id

    def upsert_pages(self, document_id: str, page_sizes: list[tuple[float, float]]) -> None:
        with self._connect() as conn:
            for page, (width, height) in enumerate(page_sizes, 1):
                conn.execute(
                    """INSERT INTO source_pages (document_id, page_number, width, height) VALUES (%s,%s,%s,%s)
                       ON CONFLICT (document_id, page_number) DO UPDATE SET width=EXCLUDED.width, height=EXCLUDED.height""",
                    (document_id, page, width, height),
                )

    def upsert_chunks(self, document_id: str, chunks: list[ParsedChunk], embedding_model: str) -> None:
        with self._connect() as conn:
            for order, chunk in enumerate(chunks):
                conn.execute(
                    """INSERT INTO knowledge_sections (section_id, document_id, heading_path, title, page_start, page_end, section_order)
                       VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (section_id) DO NOTHING""",
                    (chunk.section_id, document_id, chunk.heading_path, chunk.section_title, chunk.page_start, chunk.page_end, order),
                )
                search_text = " ".join(jieba.cut_for_search(f"{chunk.article_title} {chunk.section_title} {chunk.content}"))
                conn.execute(
                    """INSERT INTO knowledge_chunks (chunk_id, document_id, section_id, article_title, section_title,
                       heading_path, page_start, page_end, source_bboxes, content, source_excerpt, search_text,
                       content_hash, embedding_model)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (document_id, content_hash) DO UPDATE SET source_bboxes=EXCLUDED.source_bboxes,
                       content=EXCLUDED.content, source_excerpt=EXCLUDED.source_excerpt, search_text=EXCLUDED.search_text,
                       embedding_model=EXCLUDED.embedding_model, updated_at=now()""",
                    (chunk.chunk_id, document_id, chunk.section_id, chunk.article_title, chunk.section_title, chunk.heading_path,
                     chunk.page_start, chunk.page_end, Json(chunk.source_bboxes), chunk.content, chunk.source_excerpt,
                     search_text, chunk.content_hash, embedding_model),
                )

    def get_cached_embedding(self, content_hash: str, model_name: str) -> list[float] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT vector FROM embedding_cache WHERE content_hash=%s AND model_name=%s", (content_hash, model_name)).fetchone()
        return list(row["vector"]) if row else None

    def put_cached_embedding(self, content_hash: str, model_name: str, vector: list[float]) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO embedding_cache (content_hash, model_name, vector) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                (content_hash, model_name, Json(vector)),
            )

    def lexical_search(self, query: str, limit: int) -> list[dict[str, Any]]:
        terms = " ".join(jieba.cut_for_search(query))
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT *, ts_rank_cd(to_tsvector('simple', search_text), plainto_tsquery('simple', %s)) AS lexical_score
                   FROM knowledge_chunks WHERE published_status='published'
                   ORDER BY lexical_score DESC, similarity(content, %s) DESC LIMIT %s""",
                (terms, query, limit),
            ).fetchall()
        return rows

    def chunks_by_ids(self, chunk_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not chunk_ids:
            return {}
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM knowledge_chunks WHERE chunk_id = ANY(%s::uuid[])", (chunk_ids,)).fetchall()
        return {str(row["chunk_id"]): row for row in rows}

    def get_citation(self, chunk_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            return conn.execute(
                """SELECT c.*, d.title AS document_title, d.source_sha256, d.page_count
                   FROM knowledge_chunks c JOIN source_documents d ON d.document_id=c.document_id
                   LEFT JOIN source_pages p ON p.document_id=c.document_id AND p.page_number=c.page_start
                   WHERE c.chunk_id=%s""",
                (chunk_id,),
            ).fetchone()

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            return conn.execute("SELECT * FROM source_documents WHERE document_id=%s", (document_id,)).fetchone()

    def set_preview_path(self, document_id: str, page_number: int, preview_path: str, width: float, height: float) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE source_pages SET preview_path=%s, width=%s, height=%s WHERE document_id=%s AND page_number=%s",
                (preview_path, width, height, document_id, page_number),
            )

    def get_page(self, document_id: str, page_number: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            return conn.execute("SELECT * FROM source_pages WHERE document_id=%s AND page_number=%s", (document_id, page_number)).fetchone()
