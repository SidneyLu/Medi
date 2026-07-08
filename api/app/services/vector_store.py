from __future__ import annotations

from typing import Any

import chromadb

from app.core.config import get_settings


class VectorStoreService:
    def __init__(self) -> None:
        settings = get_settings()
        self.client = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)
        self.collection = self.client.get_or_create_collection(name=settings.chroma_collection_name)

    def heartbeat(self) -> bool:
        return bool(self.client.heartbeat())

    def upsert(self, ids: list[str], documents: list[str], metadatas: list[dict[str, Any]], embeddings: list[list[float]]) -> None:
        self.collection.upsert(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings)

    def delete_by_document(self, source_document_id: int) -> None:
        self.collection.delete(where={"source_document_id": source_document_id})

    def query(
        self,
        query_embedding: list[float],
        n_results: int = 6,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
