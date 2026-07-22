import uuid

from app.core.responses import AppError
from app.models.schemas import (
    ChatMessage,
    ChatQueryRequest,
    Citation,
    Conversation,
    ConversationDetail,
    ConversationListData,
)
from app.services.application_repository import ApplicationRepository, utc_now
from app.services.knowledge_service import KnowledgeService
from app.services.label_rules import format_profile_context, humanize_profile_tags
from app.services.profile_service import ProfileService
from app.services.qwen_client import MAX_HISTORY_MESSAGES, QwenClient
from app.services.storage import Store

RED_FLAG_KEYWORDS = [
    "chest pain",
    "difficulty breathing",
    "shortness of breath",
    "loss of consciousness",
    "unconscious",
    "severe trauma",
    "major bleeding",
    "anaphylaxis",
    "convulsion",
    "seizure",
    "胸痛",
    "呼吸困难",
    "意识不清",
    "昏迷",
    "严重外伤",
    "大出血",
    "过敏性休克",
    "抽搐",
    "新生儿重度黄疸",
]

FOLLOW_UP_HINTS = (
    "那",
    "还有",
    "刚才",
    "上面",
    "这个",
    "那个",
    "继续",
    "怎么办",
    "如何",
    "呢",
    "吗",
    "同上",
    "之前",
    "刚刚",
)


class RagService:
    def __init__(self, repository: ApplicationRepository, store: Store) -> None:
        self.repository = repository
        self.store = store
        self.profile_service = ProfileService(repository)
        self.knowledge_service = KnowledgeService(store)
        self.qwen_client = QwenClient()

    def list_conversations(self, user_id: str) -> ConversationListData:
        conversations = [
            Conversation(
                conversation_id=item["conversation_id"],
                title=item["title"],
                updated_at=item["updated_at"],
                preview=item["preview"],
            )
            for item in self.repository.list_conversations(user_id)
        ]
        return ConversationListData(items=conversations, next_cursor=None)

    def create_conversation(self, user_id: str) -> ConversationDetail:
        return self._to_detail(self.repository.create_conversation(user_id))

    def get_conversation(self, user_id: str, conversation_id: str) -> ConversationDetail:
        conversation = self.repository.get_conversation(user_id, conversation_id)
        if conversation is None:
            raise AppError(status_code=404, code=40401, message="Conversation not found", error_type="not_found")
        return self._to_detail(conversation)

    def delete_conversation(self, user_id: str, conversation_id: str) -> None:
        if not self.repository.delete_conversation(user_id, conversation_id):
            raise AppError(status_code=404, code=40401, message="Conversation not found", error_type="not_found")
        self.repository.add_audit_log(user_id, "chat.delete", {"conversation_id": conversation_id})

    def send_message(self, user_id: str, conversation_id: str, payload: ChatQueryRequest) -> ChatMessage:
        conversation = self.repository.get_conversation(user_id, conversation_id)
        if conversation is None:
            raise AppError(status_code=404, code=40401, message="Conversation not found", error_type="not_found")

        history = _normalize_history(conversation.get("messages") or []) if payload.use_memory else []
        created_at = utc_now()
        user_message = ChatMessage(
            message_id=str(uuid.uuid4()),
            role="user",
            content=payload.question,
            created_at=created_at,
        )
        assistant_message = self._answer(user_id, payload, history)

        conversation["messages"].append(user_message.model_dump(exclude_none=True))
        conversation["messages"].append(assistant_message.model_dump(exclude_none=True))
        if not conversation.get("title") or conversation["title"] in {
            "New conversation",
            "New health chat",
            "Health chat",
            "新咨询",
        }:
            conversation["title"] = payload.question[:24] or "健康咨询"
        conversation["preview"] = assistant_message.content[:80]
        conversation["updated_at"] = assistant_message.created_at
        self.repository.update_conversation(user_id, conversation)
        self.repository.add_audit_log(
            user_id,
            "chat.message",
            {
                "conversation_id": conversation_id,
                "question": payload.question,
                "risk_level": assistant_message.risk_level,
                "evidence_available": assistant_message.evidence_available,
                "history_turns": len(history),
            },
        )
        return assistant_message

    def _answer(self, user_id: str, payload: ChatQueryRequest, history: list[dict]) -> ChatMessage:
        profile_tags: list[str] = []
        profile_context = ""
        profile_keywords: list[str] = []
        if payload.use_profile:
            profile_data = self.profile_service.get_profile(user_id)
            profile_tags = list(profile_data.tags)
            profile_keywords = [item.keyword for item in profile_data.keywords]
            if profile_data.profile is not None:
                profile_context = format_profile_context(profile_data.profile.model_dump())

        risk_level = "high" if _has_red_flag(payload.question) else "unknown"
        retrieval_query = _build_retrieval_query(payload.question, history)
        chunks = self.knowledge_service.search(retrieval_query, tags=profile_tags, limit=5)
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
            content = (
                "您描述的内容可能涉及紧急情况警示信号。请不要等待线上回复。"
                "请立即联系当地急救服务或前往急诊。本系统仅提供健康科普，不能替代现场医疗救治。"
            )
            if profile_context:
                content += "\n\n就医时可携带/告知的个人健康信息：\n" + profile_context
            suggestions = [
                "立即联系急救服务。",
                "在等待救援时尽量保证安全并持续观察。",
                "如条件允许，准备病史、过敏史、用药和近期报告。",
            ]
            evidence_available = bool(citations)
        elif not chunks:
            content = (
                "未检索到足够相关的授权 MSD 知识块，因此后端不会编造医学解释。"
                "请补充症状持续时间、伴随表现和相关病史，或线下咨询合格医生。"
            )
            if history:
                content += "\n\n系统已读取本会话前序对话，但仍缺少匹配知识来源；可换一种更具体的描述继续追问。"
            if profile_context:
                content += "\n\n已读取到你的健康画像：\n" + profile_context
            suggestions = [
                "补充症状出现时间、持续时长和伴随症状。",
                "若症状持续、加重或令人担心，请及时线下就医。",
            ]
            risk_level = "unknown"
            evidence_available = False
        else:
            generated = self.qwen_client.generate_answer(
                payload.question,
                profile_tags,
                chunks,
                profile_context=profile_context,
                history=history,
                profile_keywords=profile_keywords,
            )
            content = generated["answer"]
            suggestions = generated["suggestions"]
            risk_level = generated["risk_level"]
            evidence_available = True

        display_tags = humanize_profile_tags(profile_tags) if profile_tags else []
        if profile_context and not display_tags:
            display_tags = ["已使用健康画像"]
        if history:
            display_tags = ["多轮会话记忆", *display_tags]

        return ChatMessage(
            message_id=str(uuid.uuid4()),
            role="assistant",
            content=content,
            created_at=utc_now(),
            risk_level=risk_level,
            suggestions=suggestions,
            profile_tags_used=display_tags,
            citations=citations,
            evidence_available=evidence_available,
        )

    def _to_detail(self, conversation: dict) -> ConversationDetail:
        return ConversationDetail(
            conversation_id=conversation["conversation_id"],
            title=conversation["title"],
            updated_at=conversation["updated_at"],
            preview=conversation["preview"],
            messages=[ChatMessage(**item) for item in conversation["messages"]],
        )


def _normalize_history(messages: list[dict]) -> list[dict]:
    cleaned: list[dict] = []
    for item in messages:
        role = item.get("role")
        content = str(item.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        cleaned.append({"role": role, "content": content})
    if len(cleaned) > MAX_HISTORY_MESSAGES:
        return cleaned[-MAX_HISTORY_MESSAGES:]
    return cleaned


def _build_retrieval_query(question: str, history: list[dict]) -> str:
    """Expand short follow-ups with recent user utterances for better retrieval."""
    prior_users = [item["content"] for item in history if item.get("role") == "user"]
    if not prior_users:
        return question

    recent = prior_users[-2:]
    compact = question.strip()
    looks_like_follow_up = len(compact) <= 24 or any(hint in compact for hint in FOLLOW_UP_HINTS)
    if looks_like_follow_up:
        return "；".join([*recent, compact])
    if recent:
        return f"{recent[-1]}；{compact}"
    return compact


def _has_red_flag(question: str) -> bool:
    normalized = question.lower()
    return any(keyword.lower() in normalized for keyword in RED_FLAG_KEYWORDS)
