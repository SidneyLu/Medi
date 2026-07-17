CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS source_documents (
    document_id UUID PRIMARY KEY,
    source_sha256 TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    source_path TEXT NOT NULL,
    page_count INTEGER NOT NULL,
    parser_name TEXT NOT NULL,
    parser_version TEXT,
    trusted BOOLEAN NOT NULL DEFAULT TRUE,
    published_status TEXT NOT NULL DEFAULT 'published',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS source_pages (
    document_id UUID NOT NULL REFERENCES source_documents(document_id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL,
    content_hash TEXT,
    width REAL,
    height REAL,
    preview_path TEXT,
    PRIMARY KEY (document_id, page_number)
);

CREATE TABLE IF NOT EXISTS knowledge_sections (
    section_id UUID PRIMARY KEY,
    document_id UUID NOT NULL REFERENCES source_documents(document_id) ON DELETE CASCADE,
    heading_path TEXT[] NOT NULL,
    title TEXT NOT NULL,
    page_start INTEGER NOT NULL,
    page_end INTEGER NOT NULL,
    section_order INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS knowledge_chunks (
    chunk_id UUID PRIMARY KEY,
    document_id UUID NOT NULL REFERENCES source_documents(document_id) ON DELETE CASCADE,
    section_id UUID REFERENCES knowledge_sections(section_id) ON DELETE SET NULL,
    article_title TEXT NOT NULL,
    section_title TEXT NOT NULL,
    heading_path TEXT[] NOT NULL,
    page_start INTEGER NOT NULL,
    page_end INTEGER NOT NULL,
    source_bboxes JSONB NOT NULL DEFAULT '[]'::jsonb,
    content TEXT NOT NULL,
    source_excerpt TEXT NOT NULL,
    search_text TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'medical_manual',
    tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    content_hash TEXT NOT NULL,
    source_trust TEXT NOT NULL DEFAULT 'trusted',
    published_status TEXT NOT NULL DEFAULT 'published',
    embedding_model TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (document_id, content_hash)
);

CREATE INDEX IF NOT EXISTS knowledge_chunks_search_idx ON knowledge_chunks USING GIN (to_tsvector('simple', search_text));
CREATE INDEX IF NOT EXISTS knowledge_chunks_content_trgm_idx ON knowledge_chunks USING GIN (content gin_trgm_ops);
CREATE INDEX IF NOT EXISTS knowledge_chunks_document_idx ON knowledge_chunks(document_id, page_start);

CREATE TABLE IF NOT EXISTS embedding_cache (
    content_hash TEXT NOT NULL,
    model_name TEXT NOT NULL,
    vector JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (content_hash, model_name)
);

CREATE TABLE IF NOT EXISTS ingestion_runs (
    run_id UUID PRIMARY KEY,
    document_id UUID REFERENCES source_documents(document_id) ON DELETE SET NULL,
    source_sha256 TEXT NOT NULL,
    parsed_path TEXT NOT NULL,
    status TEXT NOT NULL,
    pages_processed INTEGER NOT NULL DEFAULT 0,
    chunks_written INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);
