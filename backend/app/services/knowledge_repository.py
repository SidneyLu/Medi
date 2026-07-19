from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json

if TYPE_CHECKING:
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
        import jieba

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
        import jieba

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


from app.core.config import get_settings as _get_settings

_KNOWLEDGE_CHUNKS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS msd_knowledge_chunks (
    chunk_id VARCHAR(64) PRIMARY KEY,
    document_id VARCHAR(64) NOT NULL,
    pdf_page INTEGER NOT NULL CHECK (pdf_page > 0),
    printed_page VARCHAR(32),
    chunk_index INTEGER NOT NULL CHECK (chunk_index >= 0),
    chunk_count INTEGER NOT NULL CHECK (chunk_count > 0),
    article_title TEXT NOT NULL,
    section_title TEXT NOT NULL,
    source_url TEXT NOT NULL,
    category TEXT NOT NULL,
    content TEXT NOT NULL,
    tags JSONB NOT NULL,
    version_label TEXT,
    revised_at TEXT,
    author TEXT,
    reviewer TEXT,
    content_hash VARCHAR(64) NOT NULL CHECK (length(content_hash) = 64),
    model_name TEXT NOT NULL,
    searchable BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_msd_knowledge_chunks_document_id ON msd_knowledge_chunks (document_id);
CREATE INDEX IF NOT EXISTS idx_msd_knowledge_chunks_pdf_page ON msd_knowledge_chunks (pdf_page);
CREATE INDEX IF NOT EXISTS idx_msd_knowledge_chunks_category ON msd_knowledge_chunks (category);
CREATE INDEX IF NOT EXISTS idx_msd_knowledge_chunks_content_hash ON msd_knowledge_chunks (content_hash);
CREATE INDEX IF NOT EXISTS idx_msd_knowledge_chunks_document_page ON msd_knowledge_chunks (document_id, pdf_page);
CREATE INDEX IF NOT EXISTS idx_msd_knowledge_chunks_tags_gin ON msd_knowledge_chunks USING GIN (tags);
"""

_EXPECTED_COLUMNS = {
    "chunk_id": "character varying",
    "document_id": "character varying",
    "pdf_page": "integer",
    "printed_page": "character varying",
    "chunk_index": "integer",
    "chunk_count": "integer",
    "article_title": "text",
    "section_title": "text",
    "source_url": "text",
    "category": "text",
    "content": "text",
    "tags": "jsonb",
    "version_label": "text",
    "revised_at": "text",
    "author": "text",
    "reviewer": "text",
    "content_hash": "character varying",
    "model_name": "text",
    "searchable": "boolean",
    "created_at": "timestamp with time zone",
    "updated_at": "timestamp with time zone",
}

_LEXICAL_STOPWORDS = {
    "有",
    "有哪些",
    "哪些",
    "什么",
    "是什么",
    "怎么",
    "如何",
    "请问",
    "一下",
    "常见",
    "相关",
    "可能",
    "一般",
    "主要",
    "表现",
}

_UPSERT_KNOWLEDGE_CHUNK_SQL = """
INSERT INTO msd_knowledge_chunks (
    chunk_id, document_id, pdf_page, printed_page, chunk_index, chunk_count,
    article_title, section_title, source_url, category, content, tags,
    version_label, revised_at, author, reviewer, content_hash, model_name,
    searchable
) VALUES (
    %(chunk_id)s, %(document_id)s, %(pdf_page)s, %(printed_page)s,
    %(chunk_index)s, %(chunk_count)s, %(article_title)s, %(section_title)s,
    %(source_url)s, %(category)s, %(content)s, %(tags)s, %(version_label)s,
    %(revised_at)s, %(author)s, %(reviewer)s, %(content_hash)s,
    %(model_name)s, %(searchable)s
)
ON CONFLICT (chunk_id) DO UPDATE SET
    document_id = EXCLUDED.document_id,
    pdf_page = EXCLUDED.pdf_page,
    printed_page = EXCLUDED.printed_page,
    chunk_index = EXCLUDED.chunk_index,
    chunk_count = EXCLUDED.chunk_count,
    article_title = EXCLUDED.article_title,
    section_title = EXCLUDED.section_title,
    source_url = EXCLUDED.source_url,
    category = EXCLUDED.category,
    content = EXCLUDED.content,
    tags = EXCLUDED.tags,
    version_label = EXCLUDED.version_label,
    revised_at = EXCLUDED.revised_at,
    author = EXCLUDED.author,
    reviewer = EXCLUDED.reviewer,
    content_hash = EXCLUDED.content_hash,
    model_name = EXCLUDED.model_name,
    searchable = EXCLUDED.searchable,
    updated_at = NOW()
"""


def _as_jsonb_array(value: Any) -> Json:
    if value is None:
        tags = []
    elif isinstance(value, list):
        tags = value
    else:
        tags = [str(value)]
    return Json([str(item) for item in tags if str(item).strip()])


class KnowledgeImportRepository:
    """PostgreSQL repository for importing and reading knowledge chunks."""

    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or _get_settings().database_url
        if not self.database_url:
            raise RuntimeError("DATABASE_URL is required for KnowledgeImportRepository")

    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def initialize_schema(self) -> None:
        with self._connect() as conn:
            with conn.transaction():
                conn.execute(_KNOWLEDGE_CHUNKS_SCHEMA_SQL)
                self._validate_schema(conn)

    def initialize(self) -> None:
        self.initialize_schema()

    def _validate_schema(self, conn) -> None:
        rows = conn.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'msd_knowledge_chunks'
            """
        ).fetchall()
        actual = {row["column_name"]: row["data_type"] for row in rows}
        missing = sorted(set(_EXPECTED_COLUMNS) - set(actual))
        mismatched = sorted(
            f"{name}: expected {_EXPECTED_COLUMNS[name]}, found {actual.get(name)}"
            for name in _EXPECTED_COLUMNS
            if name in actual and actual[name] != _EXPECTED_COLUMNS[name]
        )
        if missing or mismatched:
            details = "; ".join([*(f"missing {name}" for name in missing), *mismatched])
            raise RuntimeError(f"msd_knowledge_chunks schema is incompatible: {details}")

    def upsert_chunks(self, chunks: list[dict[str, Any]], embedding_model_name: str, batch_size: int = 200) -> int:
        if not chunks:
            return 0
        total = 0
        with self._connect() as conn:
            try:
                with conn.transaction():
                    with conn.cursor() as cursor:
                        for start in range(0, len(chunks), batch_size):
                            batch = [self._prepare_chunk(row, embedding_model_name) for row in chunks[start : start + batch_size]]
                            cursor.executemany(_UPSERT_KNOWLEDGE_CHUNK_SQL, batch)
                            total += len(batch)
            except Exception:
                conn.rollback()
                raise
        return total

    def _prepare_chunk(self, chunk: dict[str, Any], embedding_model_name: str) -> dict[str, Any]:
        return {
            "chunk_id": str(chunk["chunk_id"]),
            "document_id": str(chunk["document_id"]),
            "pdf_page": int(chunk["pdf_page"]),
            "printed_page": None if chunk.get("printed_page") is None else str(chunk.get("printed_page")),
            "chunk_index": int(chunk["chunk_index"]),
            "chunk_count": int(chunk["chunk_count"]),
            "article_title": str(chunk["article_title"]),
            "section_title": str(chunk["section_title"]),
            "source_url": str(chunk["source_url"]),
            "category": str(chunk["category"]),
            "content": str(chunk["content"]),
            "tags": _as_jsonb_array(chunk.get("tags")),
            "version_label": chunk.get("version_label"),
            "revised_at": chunk.get("revised_at"),
            "author": chunk.get("author"),
            "reviewer": chunk.get("reviewer"),
            "content_hash": str(chunk["content_hash"]),
            "model_name": embedding_model_name,
            "searchable": bool(chunk["searchable"]),
        }

    def count_by_document_id(self, document_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM msd_knowledge_chunks WHERE document_id = %s",
                (document_id,),
            ).fetchone()
        return int(row["count"])

    def get_chunks_by_ids(self, chunk_ids: list[str]) -> list[dict[str, Any]]:
        if not chunk_ids:
            return []
        order = {chunk_id: index for index, chunk_id in enumerate(chunk_ids)}
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM msd_knowledge_chunks WHERE chunk_id = ANY(%s)",
                (chunk_ids,),
            ).fetchall()
        return sorted(rows, key=lambda row: order.get(str(row["chunk_id"]), len(order)))

    def lexical_search(
        self,
        query: str,
        limit: int = 50,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        query_text = query.strip()
        if not query_text:
            raise ValueError("query must not be empty")
        if not isinstance(limit, int) or limit < 1 or limit > 100:
            raise ValueError("limit must be an integer from 1 to 100")

        terms = _extract_lexical_terms(query_text)
        if not terms:
            return []

        where_parts = ["searchable = TRUE"]
        where_params: list[Any] = []
        score_params: list[Any] = []
        if category:
            where_parts.append("category = %s")
            where_params.append(category)

        match_parts: list[str] = []
        score_parts: list[str] = []
        for term in terms:
            pattern = f"%{term}%"
            match_parts.append("(article_title ILIKE %s OR section_title ILIKE %s OR content ILIKE %s)")
            where_params.extend([pattern, pattern, pattern])
            score_parts.append(
                """
                (CASE WHEN article_title ILIKE %s THEN 8 ELSE 0 END)
                + (CASE WHEN section_title ILIKE %s THEN 6 ELSE 0 END)
                + (CASE WHEN content ILIKE %s THEN 2 ELSE 0 END)
                + (CASE WHEN section_title ILIKE %s THEN 3 ELSE 0 END)
                + (CASE WHEN content ILIKE %s THEN 1 ELSE 0 END)
                """
            )
            score_params.extend([pattern, pattern, pattern, pattern, pattern])

        where_parts.append("(" + " OR ".join(match_parts) + ")")
        sql = f"""
            SELECT
                chunk_id,
                document_id,
                pdf_page,
                article_title,
                section_title,
                category,
                content_hash,
                model_name,
                ({" + ".join(score_parts)}) AS lexical_score
            FROM msd_knowledge_chunks
            WHERE {" AND ".join(where_parts)}
            ORDER BY lexical_score DESC, chunk_id ASC
            LIMIT %s
        """
        params = [*score_params, *where_params, limit]
        with self._connect() as conn:
            return conn.execute(sql, params).fetchall()

    def chunks_by_ids(self, chunk_ids: list[str]) -> dict[str, dict[str, Any]]:
        return {row["chunk_id"]: row for row in self.get_chunks_by_ids(chunk_ids)}

    def delete_by_document_id(self, document_id: str) -> int:
        with self._connect() as conn:
            with conn.transaction():
                result = conn.execute(
                    "DELETE FROM msd_knowledge_chunks WHERE document_id = %s",
                    (document_id,),
                )
                return int(result.rowcount or 0)

    def close(self) -> None:
        return None


def _extract_lexical_terms(query: str) -> list[str]:
    import jieba

    terms: list[str] = []
    for raw_term in jieba.cut_for_search(query):
        term = raw_term.strip().lower()
        if len(term) < 2 or term in _LEXICAL_STOPWORDS:
            continue
        if term not in terms:
            terms.append(term)
    return terms
