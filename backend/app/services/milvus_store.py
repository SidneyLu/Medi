from __future__ import annotations

from typing import Any

from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, connections, utility


class MilvusStore:
    def __init__(self, uri: str, collection_name: str, token: str | None = None) -> None:
        self.uri = uri
        self.collection_name = collection_name
        self.token = token

    def _collection(self, dimension: int | None = None) -> Collection:
        connections.connect(alias="medical", uri=self.uri, token=self.token)
        if not utility.has_collection(self.collection_name, using="medical"):
            if not dimension:
                raise RuntimeError("A vector dimension is required to create the Milvus collection")
            fields = [
                FieldSchema("chunk_id", DataType.VARCHAR, is_primary=True, max_length=36),
                FieldSchema("document_id", DataType.VARCHAR, max_length=36),
                FieldSchema("page_start", DataType.INT64),
                FieldSchema("embedding", DataType.FLOAT_VECTOR, dim=dimension),
            ]
            collection = Collection(self.collection_name, CollectionSchema(fields, "Medical manual chunks"), using="medical")
            collection.create_index("embedding", {"index_type": "HNSW", "metric_type": "COSINE", "params": {"M": 16, "efConstruction": 200}})
        else:
            collection = Collection(self.collection_name, using="medical")
        collection.load()
        return collection

    def upsert(self, rows: list[dict[str, Any]], dimension: int) -> None:
        if not rows:
            return
        collection = self._collection(dimension)
        fields = {field.name: field for field in collection.schema.fields}
        actual_dimension = fields["embedding"].params.get("dim")
        if int(actual_dimension) != dimension:
            raise RuntimeError(f"Milvus collection dimension is {actual_dimension}, not {dimension}")
        collection.upsert([[row["chunk_id"] for row in rows], [row["document_id"] for row in rows], [row["page_start"] for row in rows], [row["embedding"] for row in rows]])
        collection.flush()

    def search(self, vector: list[float], limit: int = 30) -> list[tuple[str, float]]:
        collection = self._collection()
        results = collection.search([vector], "embedding", {"metric_type": "COSINE", "params": {"ef": 80}}, limit=limit, output_fields=["chunk_id"])
        return [(str(hit.entity.get("chunk_id")), float(hit.score)) for hit in results[0]]
