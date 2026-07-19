from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np


QUERY_PREFIX = "为这个句子生成表示以用于检索相关文章："


@dataclass(frozen=True)
class EmbeddingConfig:
    model_name: str = "BAAI/bge-small-zh-v1.5"
    device: str = "cpu"
    batch_size: int = 32
    normalize_embeddings: bool = True
    expected_dimension: int = 512


class EmbeddingService:
    def __init__(
        self,
        *,
        model_name: str = "BAAI/bge-small-zh-v1.5",
        device: str = "cpu",
        batch_size: int = 32,
        normalize_embeddings: bool = True,
        expected_dimension: int = 512,
    ) -> None:
        self.config = EmbeddingConfig(
            model_name=model_name,
            device=resolve_device(device),
            batch_size=batch_size,
            normalize_embeddings=normalize_embeddings,
            expected_dimension=expected_dimension,
        )
        self._model = None

    @property
    def embedding_dimension(self) -> int:
        return self.config.expected_dimension

    def encode_documents(self, texts: Iterable[str]) -> np.ndarray:
        items = list(texts)
        if not items:
            return np.empty((0, self.embedding_dimension), dtype=np.float32)
        embeddings = self._model_instance().encode(
            items,
            batch_size=self.config.batch_size,
            convert_to_numpy=True,
            normalize_embeddings=self.config.normalize_embeddings,
            show_progress_bar=False,
        )
        return self._finalize_embeddings(embeddings)

    def encode_query(self, query: str) -> np.ndarray:
        text = f"{QUERY_PREFIX}{query}"
        embeddings = self.encode_documents([text])
        return embeddings[0]

    def _model_instance(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.config.model_name, device=self.config.device)
        return self._model

    def _finalize_embeddings(self, embeddings: np.ndarray) -> np.ndarray:
        array = np.asarray(embeddings, dtype=np.float32)
        if array.ndim == 1:
            array = array.reshape(1, -1)
        if array.ndim != 2:
            raise ValueError(f"embeddings must be 2D, got shape {array.shape}")
        if array.shape[1] != self.embedding_dimension:
            raise ValueError(f"embedding dimension mismatch: expected {self.embedding_dimension}, got {array.shape[1]}")
        if self.config.normalize_embeddings:
            array = normalize_rows(array)
        return array.astype(np.float32, copy=False)


def resolve_device(device: str) -> str:
    normalized = device.lower().strip()
    if normalized == "auto":
        try:
            import torch

            return "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            return "cpu"
    if normalized not in {"cpu", "cuda"}:
        raise ValueError("device must be cpu, cuda, or auto")
    return normalized


def normalize_rows(array: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(array, axis=1, keepdims=True)
    if np.any(norms == 0):
        raise ValueError("embedding contains zero vector and cannot be normalized")
    return array / norms
