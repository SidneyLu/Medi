import re
from functools import lru_cache

from app.core.config import get_settings
from app.models.schemas import KnowledgeChunkData
from app.services.embedding_service import EmbeddingService
from app.services.knowledge_repository import KnowledgeImportRepository
from app.services.milvus_service import MilvusService
from app.services.storage import Store

EMBEDDING_MODEL_NAME = "BAAI/bge-small-zh-v1.5"
EMBEDDING_DIMENSION = 512


@lru_cache(maxsize=1)
def _get_embedding_service() -> EmbeddingService:
    return EmbeddingService(
        model_name=EMBEDDING_MODEL_NAME,
        device="cpu",
        expected_dimension=EMBEDDING_DIMENSION,
        normalize_embeddings=True,
    )


@lru_cache(maxsize=1)
def _get_knowledge_repository() -> KnowledgeImportRepository:
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required for local vector knowledge search")
    return KnowledgeImportRepository(settings.database_url)


@lru_cache(maxsize=1)
def _get_milvus_service() -> MilvusService:
    settings = get_settings()
    if not settings.milvus_uri:
        raise RuntimeError("MILVUS_URI is required for local vector knowledge search")
    service = MilvusService(
        uri=settings.milvus_uri,
        token=settings.milvus_token,
        collection_name=settings.milvus_collection or "medical_chunks",
        dimension=EMBEDDING_DIMENSION,
    )
    service.connect()
    service.load_existing_collection()
    return service


class KnowledgeService:
    def __init__(self, store: Store) -> None:
        self.store = store
        self.settings = get_settings()

    def search(
        self,
        query: str,
        tags: list[str] | None = None,
        limit: int = 5,
        category: str | None = None,
    ) -> list[KnowledgeChunkData]:
        query_text = query.strip()
        if not query_text:
            raise ValueError("query must not be empty")
        if not isinstance(limit, int) or limit < 1 or limit > 50:
            raise ValueError("limit must be an integer from 1 to 50")

        if not self.settings.database_url or not self.settings.milvus_uri:
            return self._legacy_search(query_text, tags, limit, category)

        try:
            return self._local_vector_search(query_text, tags, limit, category)
        except Exception:
            return self._legacy_search(query_text, tags, limit, category)

    def _local_vector_search(
        self,
        query: str,
        tags: list[str] | None,
        limit: int,
        category: str | None,
    ) -> list[KnowledgeChunkData]:
        embedding_service = _get_embedding_service()
        repository = _get_knowledge_repository()
        milvus_service = _get_milvus_service()

        query_embedding = embedding_service.encode_query(query)
        semantic_hits = milvus_service.search(
            query_embedding,
            limit=50,
            model_name=EMBEDDING_MODEL_NAME,
        )
        lexical_hits = repository.lexical_search(query, limit=50, category=category)
        if not semantic_hits and not lexical_hits:
            return []

        chunk_ids = _unique_ids(
            [str(hit["chunk_id"]) for hit in semantic_hits],
            [str(row["chunk_id"]) for row in lexical_hits],
        )
        rows = repository.get_chunks_by_ids(chunk_ids)
        rows_by_id = {str(row["chunk_id"]): row for row in rows}

        for hit in semantic_hits:
            chunk_id = str(hit["chunk_id"])
            row = rows_by_id.get(chunk_id)
            if row is None:
                raise RuntimeError(f"PostgreSQL row not found for chunk_id {chunk_id}")
            self._validate_hit_row(hit, row)

        fused_scores = _rrf_fuse(semantic_hits, lexical_hits)
        ordered_chunk_ids = sorted(
            fused_scores,
            key=lambda chunk_id: (
                -fused_scores[chunk_id],
                _rank_of(semantic_hits, chunk_id),
                _rank_of(lexical_hits, chunk_id),
                chunk_id,
            ),
        )

        results: list[KnowledgeChunkData] = []
        for chunk_id in ordered_chunk_ids:
            row = rows_by_id.get(chunk_id)
            if row is None:
                raise RuntimeError(f"PostgreSQL row not found for chunk_id {chunk_id}")
            if category and row["category"] != category:
                continue
            results.append(
                KnowledgeChunkData(
                    chunk_id=str(row["chunk_id"]),
                    article_title=str(row["article_title"]),
                    section_title=str(row["section_title"]),
                    source_url=str(row["source_url"]),
                    category=str(row["category"]),
                    content=str(row["content"]),
                    score=float(fused_scores[chunk_id]),
                    tags=list(row.get("tags") or []),
                    version_label=row.get("version_label"),
                    revised_at=row.get("revised_at"),
                )
            )
            if len(results) >= limit:
                break
        return results

    @staticmethod
    def _validate_hit_row(hit: dict, row: dict) -> None:
        chunk_id = str(hit["chunk_id"])
        if str(row.get("content_hash")) != str(hit.get("content_hash")):
            raise RuntimeError(f"content_hash mismatch for chunk_id {chunk_id}")
        if str(row.get("model_name")) != EMBEDDING_MODEL_NAME:
            raise RuntimeError(f"model_name mismatch for chunk_id {chunk_id}")
        if str(row.get("document_id")) != str(hit.get("document_id")):
            raise RuntimeError(f"document_id mismatch for chunk_id {chunk_id}")
        if int(row.get("pdf_page")) != int(hit.get("pdf_page")):
            raise RuntimeError(f"pdf_page mismatch for chunk_id {chunk_id}")

    def _legacy_search(
        self,
        query: str,
        tags: list[str] | None,
        limit: int,
        category: str | None,
    ) -> list[KnowledgeChunkData]:
        query_tokens = _tokenize(query)
        profile_tags = set(tags or [])
        scored: list[KnowledgeChunkData] = []

        for chunk in self.store.list_knowledge_chunks():
            if category and chunk["category"] != category:
                continue
            score = _score_chunk(chunk, query, query_tokens, profile_tags)
            if score <= 0:
                continue
            scored.append(
                KnowledgeChunkData(
                    chunk_id=chunk["chunk_id"],
                    article_title=chunk["article_title"],
                    section_title=chunk["section_title"],
                    source_url=chunk["source_url"],
                    category=chunk["category"],
                    content=chunk["content"],
                    score=score,
                    tags=chunk["tags"],
                    version_label=chunk.get("version_label"),
                    revised_at=chunk.get("revised_at"),
                )
            )

        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:limit]


def _tokenize(text: str) -> list[str]:
    tokens = [item.lower() for item in re.split(r"[\s,，。！？；;、]+", text) if len(item.strip()) >= 2]
    cjk_phrases = re.findall(r"[\u4e00-\u9fff]{2,}", text)
    tokens.extend(phrase for phrase in cjk_phrases if phrase not in tokens)
    return tokens


def _unique_ids(*groups: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for group in groups:
        for chunk_id in group:
            if chunk_id not in seen:
                seen.add(chunk_id)
                ordered.append(chunk_id)
    return ordered


def _rrf_fuse(semantic_hits: list[dict], lexical_hits: list[dict]) -> dict[str, float]:
    fused: dict[str, float] = {}
    for rank, hit in enumerate(semantic_hits, start=1):
        chunk_id = str(hit["chunk_id"])
        fused[chunk_id] = fused.get(chunk_id, 0.0) + 1 / (60 + rank)
    for rank, row in enumerate(lexical_hits, start=1):
        chunk_id = str(row["chunk_id"])
        fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.5 * (1 / (60 + rank))
    return fused


def _rank_of(items: list[dict], chunk_id: str) -> int:
    for rank, item in enumerate(items, start=1):
        if str(item["chunk_id"]) == chunk_id:
            return rank
    return 10_000


def _score_chunk(chunk: dict, query: str, query_tokens: list[str], profile_tags: set[str]) -> float:
    haystack = " ".join(
        [
            chunk["article_title"],
            chunk["section_title"],
            chunk["category"],
            chunk["content"],
            " ".join(chunk["tags"]),
        ]
    ).lower()
    score = 0.0
    if query.lower() in haystack:
        score += 4
    for token in query_tokens:
        if token in haystack:
            score += 2
    score += len(profile_tags.intersection(set(chunk["tags"]))) * 0.5
    return score
