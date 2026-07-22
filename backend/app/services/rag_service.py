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
from app.services.profile_service import ProfileService
from app.services.qwen_client import QwenClient
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

    def send_message(self, user_id: str, conversation_id: str, payload: ChatQueryRequest) -> ChatMessage:
        conversation = self.repository.get_conversation(user_id, conversation_id)
        if conversation is None:
            raise AppError(status_code=404, code=40401, message="Conversation not found", error_type="not_found")

        created_at = utc_now()
        user_message = ChatMessage(
            message_id=str(uuid.uuid4()),
            role="user",
            content=payload.question,
            created_at=created_at,
        )
        assistant_message = self._answer(user_id, payload)

        conversation["messages"].append(user_message.model_dump(exclude_none=True))
        conversation["messages"].append(assistant_message.model_dump(exclude_none=True))
        conversation["title"] = payload.question[:24] or "Health chat"
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
            },
        )
        return assistant_message

    def _answer(self, user_id: str, payload: ChatQueryRequest) -> ChatMessage:
        profile_tags: list[str] = []
        profile_keywords: list[str] = []
        if payload.use_profile:
            profile_data = self.profile_service.get_profile(user_id)
            profile_tags = profile_data.tags
            profile_keywords = [item.keyword for item in profile_data.keywords]

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
            content = (
                "Your message contains possible emergency warning signs. Do not wait for online advice. "
                "Contact local emergency services or go to the emergency department immediately. "
                "This system provides health education only and cannot replace in-person medical care."
            )
            suggestions = [
                "Contact emergency services now.",
                "Keep the person safe and monitored while help is arranged.",
                "Prepare medical history, allergy history, medications, and recent reports if available.",
            ]
            evidence_available = bool(citations)
        elif not chunks:
            content = (
                "No sufficiently relevant authorized MSD knowledge block was retrieved, so the backend will not "
                "invent a medical explanation. Add symptom duration, associated symptoms, and relevant history, "
                "or consult a qualified clinician."
            )
            suggestions = [
                "Add symptom onset time, duration, and associated symptoms.",
                "Seek in-person care if symptoms persist, worsen, or feel concerning.",
            ]
            risk_level = "unknown"
            evidence_available = False
        else:
            generated = self.qwen_client.generate_answer(payload.question, profile_tags, chunks, profile_keywords)
            content = generated["answer"]
            suggestions = generated["suggestions"]
            risk_level = generated["risk_level"]
            evidence_available = True

        return ChatMessage(
            message_id=str(uuid.uuid4()),
            role="assistant",
            content=content,
            created_at=utc_now(),
            risk_level=risk_level,
            suggestions=suggestions,
            profile_tags_used=profile_tags,
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


def _has_red_flag(question: str) -> bool:
    normalized = question.lower()
    return any(keyword.lower() in normalized for keyword in RED_FLAG_KEYWORDS)
