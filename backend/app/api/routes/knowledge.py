from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user, get_knowledge_service, get_msd_web_service
from app.core.responses import ApiResponse, ok
from app.models.schemas import KnowledgeSearchData, MsdPageData, MsdSearchData, MsdSearchHit
from app.services.knowledge_service import KnowledgeService
from app.services.msd_web_service import MsdWebService

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


@router.get("/msd/search", response_model=ApiResponse[MsdSearchData])
def search_msd(
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    service: Annotated[MsdWebService, Depends(get_msd_web_service)],
    q: str = Query(..., min_length=1, description="MSD 站内搜索关键词"),
    limit: int = Query(5, ge=1, le=20),
) -> ApiResponse[MsdSearchData]:
    items = [MsdSearchHit(**item) for item in service.web_search(q, limit=limit)]
    return ok(MsdSearchData(query=q, items=items))


@router.get("/msd/page", response_model=ApiResponse[MsdPageData])
def extract_msd_page(
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    service: Annotated[MsdWebService, Depends(get_msd_web_service)],
    url: str = Query(..., min_length=8, description="msdmanuals.cn 主题页 URL"),
) -> ApiResponse[MsdPageData]:
    # web_extractor raises AppError for invalid/unreachable URLs
    page = service.web_extractor(url)
    return ok(
        MsdPageData(
            title=str(page.get("title") or ""),
            url=str(page.get("url") or ""),
            summary=str(page.get("summary") or ""),
        )
    )
