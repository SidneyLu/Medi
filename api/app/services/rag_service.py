from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ProductSku, SourceDocument
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.common import Citation, CompareTable, RelatedSku
from app.services.llm_service import LLMService, RetrievedChunk
from app.services.product_service import ProductService
from app.services.vector_store import VectorStoreService


STRUCTURED_KEYWORDS = {"价格", "参数", "配置", "上市", "变化", "时间线", "对比", "电池", "芯片", "内存"}
UNSTRUCTURED_KEYWORDS = {"口碑", "评价", "体验", "优点", "缺点", "拍照", "手感", "讨论", "评测"}


class RagService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.product_service = ProductService(db)
        self.llm_service = LLMService()
        self.vector_store = VectorStoreService()

    def answer(self, payload: ChatRequest) -> ChatResponse:
        query_type = self._classify_query(payload.question)
        all_sku_ids = payload.sku_ids + [sku_id for sku_id in payload.comparison_sku_ids if sku_id not in payload.sku_ids]
        compare_table = self.product_service.build_compare_table(all_sku_ids) if len(all_sku_ids) >= 2 else None
        structured_summary, missing_fields = self.product_service.build_structured_summary(all_sku_ids)
        timeline = self.product_service.list_timeline(all_sku_ids[0]) if all_sku_ids else []
        related = [RelatedSku(**item) for item in self.product_service.get_related_skus(all_sku_ids)]

        structured_text = structured_summary if query_type in {"structured", "hybrid"} else ""
        citations: list[Citation] = []
        evidence_chunks: list[RetrievedChunk] = []
        if query_type in {"unstructured", "hybrid"}:
            evidence_chunks = self._retrieve_chunks(payload)
            citations = self._chunks_to_citations(evidence_chunks)

        fallback = self._fallback_answer(query_type, structured_text, evidence_chunks)
        prompt = self._build_prompt(payload.question, query_type, structured_text, evidence_chunks)
        answer_text = self.llm_service.summarize(prompt, fallback)

        return ChatResponse(
            answer_text=answer_text,
            citations=citations,
            compare_table=compare_table if compare_table is not None else CompareTable(),
            timeline_events=timeline,
            related_skus=related,
            missing_fields=missing_fields,
            generated_at=datetime.utcnow(),
        )

    def _classify_query(self, question: str) -> str:
        score_structured = sum(1 for keyword in STRUCTURED_KEYWORDS if keyword in question)
        score_unstructured = sum(1 for keyword in UNSTRUCTURED_KEYWORDS if keyword in question)
        if score_structured and score_unstructured:
            return "hybrid"
        if score_structured:
            return "structured"
        if score_unstructured:
            return "unstructured"
        return "hybrid"

    def _retrieve_chunks(self, payload: ChatRequest) -> list[RetrievedChunk]:
        query_embedding = self.llm_service.embed_query(payload.question)
        where: dict[str, Any] | None = None
        sku_ids = payload.sku_ids or payload.comparison_sku_ids
        if sku_ids:
            where = {"sku_id": {"$in": sku_ids}}
        result = self.vector_store.query(query_embedding=query_embedding, n_results=8, where=where)
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        chunks = [
            RetrievedChunk(text=document, metadata=metadata, score=1 - float(distances[index] or 0))
            for index, (document, metadata) in enumerate(zip(documents, metadatas))
        ]
        ranked = self.llm_service.rerank(payload.question, chunks)
        return ranked[:5]

    def _chunks_to_citations(self, chunks: list[RetrievedChunk]) -> list[Citation]:
        citations: list[Citation] = []
        for chunk in chunks:
            citations.append(
                Citation(
                    title=chunk.metadata.get("title", "未命名文档"),
                    url=chunk.metadata.get("url", ""),
                    source_type=chunk.metadata.get("source_type", "unknown"),
                    crawled_at=datetime.fromisoformat(chunk.metadata["crawled_at"]) if chunk.metadata.get("crawled_at") else None,
                    snippet=chunk.text[:180],
                )
            )
        return citations

    def _fallback_answer(self, query_type: str, structured_text: str, chunks: list[RetrievedChunk]) -> str:
        if query_type == "structured":
            return structured_text
        if query_type == "unstructured":
            if not chunks:
                return "当前没有命中可用的评测或社区内容。"
            return "基于检索到的资料，主要观点如下：\n" + "\n".join(f"- {chunk.text[:100]}" for chunk in chunks[:3])
        return structured_text + ("\n\n补充观点：\n" + "\n".join(f"- {chunk.text[:100]}" for chunk in chunks[:3]) if chunks else "")

    def _build_prompt(self, question: str, query_type: str, structured_text: str, chunks: list[RetrievedChunk]) -> str:
        evidence = "\n\n".join(
            f"[{index + 1}] {chunk.metadata.get('title', '文档')}\n{chunk.text}" for index, chunk in enumerate(chunks)
        )
        return (
            "你是数码竞品分析助手。请只基于给定证据回答，不要编造不存在的字段。"
            f"\n问题：{question}"
            f"\n问题类型：{query_type}"
            f"\n结构化信息：\n{structured_text or '无'}"
            f"\n非结构化证据：\n{evidence or '无'}"
            "\n请输出一段简洁中文总结，优先指出差异、优缺点和不确定项。"
        )
