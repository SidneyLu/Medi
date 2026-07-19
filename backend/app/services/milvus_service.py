from __future__ import annotations

import re
from typing import Any

import numpy as np

from app.core.config import get_settings

_HEX_64_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_SAFE_FILTER_TEXT_PATTERN = re.compile(r"^[A-Za-z0-9._:/-]{1,128}$")


def _validate_document_id(document_id: str) -> str:
    if not isinstance(document_id, str) or not _HEX_64_PATTERN.fullmatch(document_id):
        raise ValueError("document_id must be a 64-character lowercase hexadecimal string")
    return document_id


def _validate_filter_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not _SAFE_FILTER_TEXT_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} contains unsupported characters for Milvus filter")
    return value


def _escape_milvus_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


class MilvusService:
    """Milvus vector store for imported knowledge chunk embeddings."""

    def __init__(
        self,
        uri: str | None = None,
        token: str | None = None,
        collection_name: str | None = None,
        dimension: int = 512,
    ) -> None:
        settings = get_settings()
        self.uri = uri or settings.milvus_uri
        self.token = token if token is not None else settings.milvus_token
        self.collection_name = collection_name or settings.milvus_collection or "medical_chunks"
        self.dimension = dimension
        self._collection = None
        self._alias = "medi_knowledge_import"
        if not self.uri:
            raise RuntimeError("MILVUS_URI is required for MilvusService")

    def connect(self) -> None:
        from pymilvus import connections

        kwargs: dict[str, Any] = {"alias": self._alias, "uri": self.uri}
        if self.token:
            kwargs["token"] = self.token
        connections.connect(**kwargs)

    def ensure_collection(self) -> None:
        from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, utility

        if utility.has_collection(self.collection_name, using=self._alias):
            collection = Collection(self.collection_name, using=self._alias)
            self._validate_collection(collection)
            self._collection = collection
            self._load_collection(collection)
            return

        fields = [
            FieldSchema(name="chunk_id", dtype=DataType.VARCHAR, is_primary=True, max_length=64),
            FieldSchema(name="document_id", dtype=DataType.VARCHAR, max_length=64),
            FieldSchema(name="pdf_page", dtype=DataType.INT64),
            FieldSchema(name="chunk_index", dtype=DataType.INT64),
            FieldSchema(name="category", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="content_hash", dtype=DataType.VARCHAR, max_length=64),
            FieldSchema(name="model_name", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=self.dimension),
        ]
        schema = CollectionSchema(fields=fields, description="Medi knowledge chunk embeddings", enable_dynamic_field=False)
        collection = Collection(self.collection_name, schema=schema, using=self._alias)
        collection.create_index(
            field_name="embedding",
            index_params={
                "index_type": "HNSW",
                "metric_type": "COSINE",
                "params": {"M": 16, "efConstruction": 200},
            },
        )
        self._collection = collection
        self._load_collection(collection)

    def _load_collection(self, collection) -> None:
        try:
            collection.load()
        except Exception as exc:
            raise RuntimeError(f"failed to load Milvus collection {self.collection_name}") from exc

    def load_existing_collection(self) -> None:
        from pymilvus import Collection, utility

        if not utility.has_collection(self.collection_name, using=self._alias):
            raise RuntimeError(f"Milvus collection {self.collection_name} does not exist")
        collection = Collection(self.collection_name, using=self._alias)
        self._validate_collection(collection)
        self._collection = collection
        self._load_collection(collection)

    def _validate_collection(self, collection) -> None:
        from pymilvus import DataType

        fields = {field.name: field for field in collection.schema.fields}
        required = {
            "chunk_id",
            "document_id",
            "pdf_page",
            "chunk_index",
            "category",
            "content_hash",
            "model_name",
            "embedding",
        }
        missing = sorted(required - set(fields))
        if missing:
            raise RuntimeError(f"Milvus collection schema is incompatible: missing fields {missing}")

        if not fields["chunk_id"].is_primary or fields["chunk_id"].dtype != DataType.VARCHAR:
            raise RuntimeError("Milvus collection schema is incompatible: chunk_id must be VARCHAR primary key")
        if fields["embedding"].dtype != DataType.FLOAT_VECTOR:
            raise RuntimeError("Milvus collection schema is incompatible: embedding must be FLOAT_VECTOR")
        embedding_dim = int(fields["embedding"].params.get("dim", 0))
        if embedding_dim != self.dimension:
            raise RuntimeError(
                f"Milvus collection schema is incompatible: embedding dimension {embedding_dim}, expected {self.dimension}"
            )

        indexes = list(collection.indexes or [])
        vector_indexes = [index for index in indexes if getattr(index, "field_name", None) == "embedding"]
        if not vector_indexes:
            raise RuntimeError("Milvus collection index is incompatible: embedding HNSW/COSINE index is missing")
        params = getattr(vector_indexes[0], "params", {}) or {}
        metric_type = params.get("metric_type") or params.get("metric")
        index_type = params.get("index_type")
        if index_type and str(index_type).upper() != "HNSW":
            raise RuntimeError(f"Milvus collection index type is incompatible: {index_type}, expected HNSW")
        if metric_type and str(metric_type).upper() != "COSINE":
            raise RuntimeError(f"Milvus collection index metric is incompatible: {metric_type}, expected COSINE")

    @property
    def collection(self):
        if self._collection is None:
            raise RuntimeError("Milvus collection is not initialized; call connect() and ensure_collection() first")
        return self._collection

    def upsert_embeddings(self, records: list[dict[str, Any]], batch_size: int = 200) -> int:
        if not records:
            return 0
        total = 0
        for start in range(0, len(records), batch_size):
            batch = records[start : start + batch_size]
            data = [
                [str(row["chunk_id"]) for row in batch],
                [str(row["document_id"]) for row in batch],
                [int(row["pdf_page"]) for row in batch],
                [int(row["chunk_index"]) for row in batch],
                [str(row["category"])[:128] for row in batch],
                [str(row["content_hash"]) for row in batch],
                [str(row["model_name"])[:128] for row in batch],
                [row["embedding"] for row in batch],
            ]
            self.collection.upsert(data)
            total += len(batch)
        self.collection.flush()
        self.collection.load()
        return total

    def search(
        self,
        query_embedding,
        limit: int = 5,
        document_id: str | None = None,
        model_name: str | None = None,
    ) -> list[dict[str, Any]]:
        if not isinstance(limit, int) or limit < 1 or limit > 50:
            raise ValueError("limit must be an integer from 1 to 50")

        vector = np.asarray(query_embedding, dtype=np.float32)
        if vector.ndim != 1 or vector.shape[0] != self.dimension:
            raise ValueError(f"query_embedding must be a 1D vector with dimension {self.dimension}")
        if not np.isfinite(vector).all():
            raise ValueError("query_embedding must not contain NaN or Infinity")
        if float(np.linalg.norm(vector)) <= 0:
            raise ValueError("query_embedding L2 norm must be greater than 0")

        filters: list[str] = []
        if document_id:
            safe_document_id = _escape_milvus_string(_validate_document_id(document_id))
            filters.append(f'document_id == "{safe_document_id}"')
        if model_name:
            safe_model_name = _escape_milvus_string(_validate_filter_text(model_name, "model_name"))
            filters.append(f'model_name == "{safe_model_name}"')

        search_kwargs: dict[str, Any] = {
            "data": [vector.tolist()],
            "anns_field": "embedding",
            "param": {"metric_type": "COSINE", "params": {"ef": 64}},
            "limit": limit,
            "output_fields": [
                "chunk_id",
                "document_id",
                "pdf_page",
                "chunk_index",
                "category",
                "content_hash",
                "model_name",
            ],
        }
        if filters:
            search_kwargs["expr"] = " and ".join(filters)

        raw_results = self.collection.search(**search_kwargs)
        first_result_set = raw_results[0] if raw_results else []
        results: list[dict[str, Any]] = []
        for hit in first_result_set:
            entity = getattr(hit, "entity", None)
            getter = entity.get if entity is not None and hasattr(entity, "get") else None
            row = {
                "chunk_id": str(getter("chunk_id") if getter else hit.get("chunk_id")),
                "score": float(getattr(hit, "score", getattr(hit, "distance", 0.0))),
                "document_id": str(getter("document_id") if getter else hit.get("document_id")),
                "pdf_page": int(getter("pdf_page") if getter else hit.get("pdf_page")),
                "chunk_index": int(getter("chunk_index") if getter else hit.get("chunk_index")),
                "category": str(getter("category") if getter else hit.get("category")),
                "content_hash": str(getter("content_hash") if getter else hit.get("content_hash")),
                "model_name": str(getter("model_name") if getter else hit.get("model_name")),
            }
            results.append(row)
        return sorted(results, key=lambda item: item["score"], reverse=True)

    def count_by_document_id(self, document_id: str) -> int:
        safe_document_id = _validate_document_id(document_id)
        expr = f'document_id == "{safe_document_id}"'
        try:
            rows = self.collection.query(expr=expr, output_fields=["count(*)"])
            if rows and "count(*)" in rows[0]:
                return int(rows[0]["count(*)"])
        except Exception:
            pass

        if hasattr(self.collection, "query_iterator"):
            count = 0
            iterator = self.collection.query_iterator(
                expr=expr,
                output_fields=["chunk_id"],
                batch_size=1000,
            )
            try:
                while True:
                    batch = iterator.next()
                    if not batch:
                        break
                    count += len(batch)
            finally:
                close = getattr(iterator, "close", None)
                if close is not None:
                    close()
            return count

        count = 0
        offset = 0
        page_size = 1000
        while True:
            rows = self.collection.query(
                expr=expr,
                output_fields=["chunk_id"],
                limit=page_size,
                offset=offset,
            )
            count += len(rows)
            if len(rows) < page_size:
                return count
            offset += page_size

    def delete_by_document_id(self, document_id: str) -> int:
        safe_document_id = _validate_document_id(document_id)
        before = self.count_by_document_id(safe_document_id)
        self.collection.delete(expr=f'document_id == "{safe_document_id}"')
        self.collection.flush()
        self.collection.load()
        return before

    def close(self) -> None:
        from pymilvus import connections

        try:
            connections.disconnect(self._alias)
        finally:
            self._collection = None
