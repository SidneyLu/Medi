from __future__ import annotations

import math
import time
from collections.abc import Sequence

import httpx

from app.core.config import Settings


class QwenEmbeddingClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not self.settings.qwen_api_key:
            raise RuntimeError("DASHSCOPE_API_KEY or QWEN_API_KEY is required for embeddings")
        response = self._post("/embeddings", {"model": self.settings.qwen_embedding_model, "input": list(texts)})
        payload = response.json()
        items = sorted(payload.get("data", []), key=lambda item: item.get("index", 0))
        vectors = [self._normalize(list(item["embedding"])) for item in items]
        if len(vectors) != len(texts):
            raise RuntimeError("Embedding API returned an unexpected vector count")
        return vectors

    def _post(self, path: str, body: dict) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = httpx.post(f"{self.settings.qwen_base_url}{path}", json=body, headers={"Authorization": f"Bearer {self.settings.qwen_api_key}"}, timeout=self.settings.qwen_timeout_seconds)
                response.raise_for_status()
                return response
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                time.sleep(2 ** attempt)
        raise RuntimeError("Qwen embedding request failed") from last_error

    @staticmethod
    def _normalize(vector: list[float]) -> list[float]:
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector


class QwenRerankClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def rerank(self, query: str, documents: Sequence[str], top_n: int) -> list[tuple[int, float]]:
        if not documents:
            return []
        if not self.settings.qwen_api_key or not self.settings.qwen_rerank_url:
            return [(index, 0.0) for index in range(min(top_n, len(documents)))]
        body = {"model": self.settings.qwen_rerank_model, "query": query, "documents": list(documents), "top_n": min(top_n, len(documents))}
        try:
            response = httpx.post(self.settings.qwen_rerank_url, json=body, headers={"Authorization": f"Bearer {self.settings.qwen_api_key}"}, timeout=self.settings.qwen_timeout_seconds)
            response.raise_for_status()
            results = response.json().get("results", [])
            return [(int(item["index"]), float(item.get("relevance_score", item.get("score", 0)))) for item in results]
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            return [(index, 0.0) for index in range(min(top_n, len(documents)))]
