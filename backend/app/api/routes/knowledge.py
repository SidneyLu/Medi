from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user, get_knowledge_service
from app.core.responses import ApiResponse, ok
from app.models.schemas import KnowledgeSearchData
from app.services.knowledge_service import KnowledgeService

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("/search", response_model=ApiResponse[KnowledgeSearchData])
def search_knowledge(
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
    q: str = Query(..., min_length=1, description="关键词或自然语言问题"),
    limit: int = Query(5, ge=1, le=20),
) -> ApiResponse[KnowledgeSearchData]:
    chunks = service.search(q, limit=limit)
    return ok(KnowledgeSearchData(query=q, chunks=chunks))
