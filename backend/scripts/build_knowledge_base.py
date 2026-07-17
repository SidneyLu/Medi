"""Build PostgreSQL and Milvus knowledge stores from a completed MinerU output directory."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.services.knowledge_repository import KnowledgeRepository
from app.services.milvus_store import MilvusStore
from app.services.mineru_adapter import build_chunks, load_mineru_blocks
from app.services.qwen_retrieval import QwenEmbeddingClient


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest MinerU output into PostgreSQL and Milvus")
    parser.add_argument("--pdf", type=Path, required=True, help="Original PDF used by MinerU")
    parser.add_argument("--parsed-dir", type=Path, required=True, help="Directory containing MinerU JSON output")
    parser.add_argument("--title", default="默克家庭医学手册")
    parser.add_argument("--chunk-chars", type=int, default=900)
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args()
    if not args.pdf.is_file():
        raise SystemExit(f"PDF not found: {args.pdf}")
    if not args.parsed_dir.is_dir():
        raise SystemExit(f"MinerU output directory not found: {args.parsed_dir}")

    settings = get_settings()
    if not settings.database_url or not settings.milvus_uri:
        raise SystemExit("DATABASE_URL and MILVUS_URI must be configured")
    source_sha = sha256_file(args.pdf)
    blocks = load_mineru_blocks(args.parsed_dir)
    chunks = build_chunks(source_sha, args.title, blocks, args.chunk_chars)
    if not chunks:
        raise SystemExit("MinerU output produced no text chunks")

    import fitz
    pdf = fitz.open(args.pdf)
    page_count = pdf.page_count
    page_sizes = [(float(page.rect.width), float(page.rect.height)) for page in pdf]
    pdf.close()
    repository = KnowledgeRepository(settings.database_url)
    repository.initialize()
    run_id = repository.begin_run(source_sha, str(args.parsed_dir.resolve()))
    try:
        document_id = repository.upsert_document(args.pdf, args.title, source_sha, page_count)
        repository.upsert_pages(document_id, page_sizes)
        repository.upsert_chunks(document_id, chunks, settings.qwen_embedding_model)
        embedding_client = QwenEmbeddingClient(settings)
        vector_store = MilvusStore(settings.milvus_uri, settings.milvus_collection, settings.milvus_token)
        rows: list[dict] = []
        for start in range(0, len(chunks), args.batch_size):
            batch = chunks[start:start + args.batch_size]
            missing = [chunk for chunk in batch if repository.get_cached_embedding(chunk.content_hash, settings.qwen_embedding_model) is None]
            generated = embedding_client.embed([chunk.content for chunk in missing]) if missing else []
            for chunk, vector in zip(missing, generated):
                repository.put_cached_embedding(chunk.content_hash, settings.qwen_embedding_model, vector)
            for chunk in batch:
                vector = repository.get_cached_embedding(chunk.content_hash, settings.qwen_embedding_model)
                if vector is None:
                    raise RuntimeError(f"Embedding cache missing for {chunk.chunk_id}")
                rows.append({"chunk_id": chunk.chunk_id, "document_id": document_id, "page_start": chunk.page_start, "embedding": vector})
        vector_store.upsert(rows, len(rows[0]["embedding"]))
        repository.complete_run(run_id, document_id, page_count, len(chunks))
        print(f"Completed {len(chunks)} chunks for document {document_id}")
    except Exception as exc:
        repository.complete_run(run_id, None, 0, 0, str(exc))
        raise


if __name__ == "__main__":
    main()
