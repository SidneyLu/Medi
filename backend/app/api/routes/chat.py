from typing import Annotated, Any

from fastapi import APIRouter, Depends, status

from app.api.deps import get_current_user, get_rag_service
from app.core.responses import ApiResponse, ok
from app.models.schemas import ChatMessage, ChatQueryRequest, ConversationDetail, ConversationListData
from app.services.rag_service import RagService

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("/conversations", response_model=ApiResponse[ConversationListData])
def list_conversations(
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    service: Annotated[RagService, Depends(get_rag_service)],
) -> ApiResponse[ConversationListData]:
    return ok(service.list_conversations(current_user["id"]))


@router.post("/conversations", response_model=ApiResponse[ConversationDetail], status_code=status.HTTP_201_CREATED)
def create_conversation(
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    service: Annotated[RagService, Depends(get_rag_service)],
) -> ApiResponse[ConversationDetail]:
    return ok(service.create_conversation(current_user["id"]))


@router.get("/conversations/{conversation_id}", response_model=ApiResponse[ConversationDetail])
def get_conversation(
    conversation_id: str,
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    service: Annotated[RagService, Depends(get_rag_service)],
) -> ApiResponse[ConversationDetail]:
    return ok(service.get_conversation(current_user["id"], conversation_id))


@router.delete("/conversations/{conversation_id}", response_model=ApiResponse[None])
def delete_conversation(
    conversation_id: str,
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    service: Annotated[RagService, Depends(get_rag_service)],
) -> ApiResponse[None]:
    service.delete_conversation(current_user["id"], conversation_id)
    return ok(None)


@router.post("/conversations/{conversation_id}/messages", response_model=ApiResponse[ChatMessage])
def send_message(
    conversation_id: str,
    payload: ChatQueryRequest,
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    service: Annotated[RagService, Depends(get_rag_service)],
) -> ApiResponse[ChatMessage]:
    return ok(service.send_message(current_user["id"], conversation_id, payload))
