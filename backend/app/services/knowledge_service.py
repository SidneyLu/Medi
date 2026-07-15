import re

from app.models.schemas import KnowledgeChunkData
from app.services.storage import Store


class KnowledgeService:
    def __init__(self, store: Store) -> None:
        self.store = store

    def search(
        self,
        query: str,
        tags: list[str] | None = None,
        limit: int = 5,
        category: str | None = None,
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
