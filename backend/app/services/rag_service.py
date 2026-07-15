from app.models.schemas import ChatQueryData, ChatQueryRequest, Citation
from app.services.knowledge_service import KnowledgeService
from app.services.profile_service import ProfileService
from app.services.qwen_client import QwenClient
from app.services.storage import Store

RED_FLAG_KEYWORDS = [
    "胸痛",
    "呼吸困难",
    "意识障碍",
    "昏迷",
    "严重外伤",
    "大出血",
    "过敏性休克",
    "抽搐",
    "新生儿重度黄疸",
]


class RagService:
    def __init__(self, store: Store) -> None:
        self.store = store
        self.profile_service = ProfileService(store)
        self.knowledge_service = KnowledgeService(store)
        self.qwen_client = QwenClient()

    def query(self, user_id: str, payload: ChatQueryRequest) -> ChatQueryData:
        profile_tags: list[str] = []
        if payload.use_profile:
            profile_tags = self.profile_service.get_profile(user_id).tags

        risk_level = "high" if _has_red_flag(payload.question) else "unknown"
        chunks = self.knowledge_service.search(payload.question, tags=profile_tags, limit=5)
        citations = [
            Citation(
                chunk_id=chunk.chunk_id,
                article_title=chunk.article_title,
                section_title=chunk.section_title,
                source_url=chunk.source_url,
            )
            for chunk in chunks
        ]

        if risk_level == "high":
            answer = (
                "你的描述包含需要立即重视的高风险信号。请优先联系急救电话或尽快前往急诊，"
                "不要等待 AI 进一步判断。本系统只能提供科普参考，不能替代医生现场评估。"
            )
            suggestions = ["立即就医或联系急救", "保持患者安全体位", "准备既往病史、用药和检查报告"]
        elif not chunks:
            answer = "当前知识库没有检索到足够的 MSD 授权内容依据，因此不能生成医学判断。建议查看 MSD 原文或咨询医生。"
            suggestions = ["补充症状持续时间、伴随表现和既往病史", "必要时前往正规医疗机构就诊"]
            risk_level = "unknown"
        else:
            generated = self.qwen_client.generate_answer(
                question=payload.question,
                profile_tags=profile_tags,
                chunks=chunks,
            )
            answer = generated["answer"]
            suggestions = generated["suggestions"]
            risk_level = generated["risk_level"]

        self.store.add_audit_log(
            user_id,
            "chat.query",
            {
                "question": payload.question,
                "risk_level": risk_level,
                "chunk_ids": [item.chunk_id for item in chunks],
                "profile_tags_used": profile_tags,
            },
        )
        return ChatQueryData(
            question=payload.question,
            answer=answer,
            risk_level=risk_level,
            suggestions=suggestions,
            profile_tags_used=profile_tags,
            citations=citations,
        )


def _has_red_flag(question: str) -> bool:
    return any(keyword in question for keyword in RED_FLAG_KEYWORDS)
