from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.core.config import get_settings


@dataclass
class RetrievedChunk:
    text: str
    metadata: dict[str, Any]
    score: float


class LLMService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.enabled = bool(self.settings.dashscope_api_key and self.settings.dashscope_api_key != "replace-me")
        self.base_url = self.settings.dashscope_base_url.rstrip("/")
        self.chat: ChatOpenAI | None = None
        self.embeddings: OpenAIEmbeddings | None = None
        if self.enabled:
            self.chat = ChatOpenAI(
                api_key=self.settings.dashscope_api_key,
                base_url=self.base_url,
                model=self.settings.chat_model,
                temperature=0.2,
            )
            self.embeddings = OpenAIEmbeddings(
                api_key=self.settings.dashscope_api_key,
                base_url=self.base_url,
                model=self.settings.embedding_model,
                dimensions=self.settings.embedding_dim,
            )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not self.embeddings:
            return [self._hash_embedding(text) for text in texts]
        return self.embeddings.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        if not self.embeddings:
            return self._hash_embedding(text)
        return self.embeddings.embed_query(text)

    def rerank(self, query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        if not chunks:
            return []
        if not self.enabled:
            return sorted(chunks, key=lambda chunk: self._keyword_score(query, chunk.text), reverse=True)

        url = f"{self.base_url}/reranks"
        payload = {
            "model": self.settings.rerank_model,
            "query": query,
            "documents": [chunk.text for chunk in chunks],
            "top_n": min(6, len(chunks)),
        }
        headers = {"Authorization": f"Bearer {self.settings.dashscope_api_key}"}
        try:
            with httpx.Client(timeout=30) as client:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
            ranked: list[RetrievedChunk] = []
            for item in data.get("data", []):
                index = item.get("index")
                if index is None or index >= len(chunks):
                    continue
                ranked.append(
                    RetrievedChunk(
                        text=chunks[index].text,
                        metadata=chunks[index].metadata,
                        score=float(item.get("relevance_score", 0)),
                    )
                )
            return ranked or chunks
        except Exception:
            return sorted(chunks, key=lambda chunk: self._keyword_score(query, chunk.text), reverse=True)

    def summarize(self, prompt: str, fallback: str) -> str:
        if not self.chat:
            return fallback
        try:
            response = self.chat.invoke(prompt)
            content = response.content
            if isinstance(content, str):
                return content
            return json.dumps(content, ensure_ascii=False)
        except Exception:
            return fallback

    def _hash_embedding(self, text: str) -> list[float]:
        size = self.settings.embedding_dim
        values = [0.0] * size
        for idx, char in enumerate(text[: min(len(text), size * 4)]):
            bucket = idx % size
            values[bucket] += (ord(char) % 97) / 97.0
        return values

    def _keyword_score(self, query: str, text: str) -> float:
        keywords = [keyword for keyword in query.lower().split() if keyword]
        lowered = text.lower()
        return sum(1 for keyword in keywords if keyword in lowered)
