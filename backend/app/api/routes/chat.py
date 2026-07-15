from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user, get_rag_service
from app.core.responses import ApiResponse, ok
from app.models.schemas import ChatQueryData, ChatQueryRequest
from app.services.rag_service import RagService

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/query", response_model=ApiResponse[ChatQueryData])
def query(
    payload: ChatQueryRequest,
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    service: Annotated[RagService, Depends(get_rag_service)],
) -> ApiResponse[ChatQueryData]:
    return ok(service.query(current_user["id"], payload))
