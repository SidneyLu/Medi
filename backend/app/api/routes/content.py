from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.responses import ApiResponse, AppError, ok
from app.models.schemas import CitationDetail, PdfBoundingBox
from app.services.knowledge_repository import KnowledgeRepository
from app.services.pdf_preview import PdfPreviewService

router = APIRouter(prefix="/content", tags=["content"])


def _repository() -> KnowledgeRepository:
    settings = get_settings()
    if not settings.database_url:
        raise AppError(status_code=503, code=50301, message="PDF knowledge database is not configured", error_type="service_unavailable")
    return KnowledgeRepository(settings.database_url)


@router.get("/citations/{chunk_id}", response_model=ApiResponse[CitationDetail])
def get_citation(chunk_id: str, current_user: Annotated[dict[str, Any], Depends(get_current_user)]) -> ApiResponse[CitationDetail]:
    repository = _repository()
    row = repository.get_citation(chunk_id)
    if not row:
        raise AppError(status_code=404, code=40411, message="Citation not found", error_type="not_found")
    width = float(row.get("width") or 1)
    height = float(row.get("height") or 1)
    boxes = []
    for item in row.get("source_bboxes", []):
        bbox = item.get("bbox")
        if not bbox or len(bbox) != 4:
            continue
        normalized = [max(0, min(100, float(bbox[0]) / width * 100)), max(0, min(100, float(bbox[1]) / height * 100)), max(0, min(100, float(bbox[2]) / width * 100)), max(0, min(100, float(bbox[3]) / height * 100))]
        boxes.append(PdfBoundingBox(page=item.get("page", row["page_start"]), bbox=normalized))
    detail = CitationDetail(
        chunk_id=str(row["chunk_id"]), document_id=str(row["document_id"]), document_title=row["document_title"],
        section_title=row["section_title"], heading_path=row["heading_path"], page_start=row["page_start"], page_end=row["page_end"],
        page_count=row["page_count"], source_excerpt=row["source_excerpt"], document_version=row["source_sha256"][:12],
        source_bboxes=boxes, preview_url=f"/api/v1/content/documents/{row['document_id']}/pages/{row['page_start']}/preview",
    )
    return ok(detail)


@router.get("/documents/{document_id}/pages/{page_number}/preview", response_class=FileResponse)
def get_page_preview(document_id: str, page_number: int, current_user: Annotated[dict[str, Any], Depends(get_current_user)]) -> FileResponse:
    settings = get_settings()
    repository = _repository()
    preview = PdfPreviewService(repository, settings).preview_path(document_id, page_number)
    return FileResponse(preview, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})
