import re
from collections import defaultdict

from app.models.schemas import KnowledgeChunkData
from app.services.storage import Store
from app.core.config import get_settings
from app.services.knowledge_repository import KnowledgeRepository
from app.services.milvus_store import MilvusStore
from app.services.qwen_retrieval import QwenEmbeddingClient, QwenRerankClient


class KnowledgeService:
    def __init__(self, store: Store) -> None:
        self.store = store
        self.settings = get_settings()
        self.repository = KnowledgeRepository(self.settings.database_url) if self.settings.database_url else None
        self.vector_store = MilvusStore(self.settings.milvus_uri, self.settings.milvus_collection, self.settings.milvus_token) if self.settings.milvus_uri else None
        self.embedding_client = QwenEmbeddingClient(self.settings)
        self.rerank_client = QwenRerankClient(self.settings)

    def search(
        self,
        query: str,
        tags: list[str] | None = None,
        limit: int = 5,
        category: str | None = None,
    ) -> list[KnowledgeChunkData]:
        if self.repository and self.vector_store and self.settings.qwen_api_key:
            try:
                return self._hybrid_search(query, limit)
            except Exception:
                # Local seed data remains usable during development or when external services are down.
                pass
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

    def _hybrid_search(self, query: str, limit: int) -> list[KnowledgeChunkData]:
        assert self.repository and self.vector_store
        lexical = self.repository.lexical_search(query, 30)
        vector = self.embedding_client.embed([query])[0]
        semantic_ids = self.vector_store.search(vector, 30)
        semantic = self.repository.chunks_by_ids([chunk_id for chunk_id, _ in semantic_ids])
        fused: dict[str, float] = defaultdict(float)
        for rank, row in enumerate(lexical, 1):
            fused[str(row["chunk_id"])] += 1 / (60 + rank)
        for rank, (chunk_id, _) in enumerate(semantic_ids, 1):
            fused[chunk_id] += 1 / (60 + rank)
        lexical_by_id = {str(row["chunk_id"]): row for row in lexical}
        candidates = {**semantic, **lexical_by_id}
        candidate_ids = sorted(fused, key=fused.get, reverse=True)[:40]
        reranked = self.rerank_client.rerank(query, [candidates[chunk_id]["content"] for chunk_id in candidate_ids], limit)
        ordered = [candidate_ids[index] for index, _ in reranked if 0 <= index < len(candidate_ids)]
        if not ordered:
            ordered = candidate_ids[:limit]
        return [self._to_schema(candidates[chunk_id], fused.get(chunk_id, 0.0)) for chunk_id in ordered[:limit]]

    @staticmethod
    def _to_schema(row: dict, score: float) -> KnowledgeChunkData:
        return KnowledgeChunkData(
            chunk_id=str(row["chunk_id"]), article_title=row["article_title"], section_title=row["section_title"],
            source_url=f"/api/v1/content/citations/{row['chunk_id']}", category=row["category"], content=row["content"],
            score=score, tags=row.get("tags", []), version_label=None, revised_at=None,
        )


def _tokenize(text: str) -> list[str]:
    tokens = [item.lower() for item in re.split(r"[\s,，。！？；;、]+", text) if len(item.strip()) >= 2]
    cjk_phrases = re.findall(r"[\u4e00-\u9fff]{2,}", text)
    tokens.extend(phrase for phrase in cjk_phrases if phrase not in tokens)
    return tokens


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
