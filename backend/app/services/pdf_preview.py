from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from app.core.config import Settings
from app.services.knowledge_repository import KnowledgeRepository


class PdfPreviewService:
    def __init__(self, repository: KnowledgeRepository, settings: Settings) -> None:
        self.repository = repository
        self.settings = settings

    def preview_path(self, document_id: str, page_number: int) -> Path:
        document = self.repository.get_document(document_id)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        if page_number < 1 or page_number > document["page_count"]:
            raise HTTPException(status_code=404, detail="Page not found")
        page = self.repository.get_page(document_id, page_number)
        if page and page.get("preview_path") and Path(page["preview_path"]).exists():
            return Path(page["preview_path"])
        return self._render(document_id, page_number, Path(document["source_path"]))

    def _render(self, document_id: str, page_number: int, source_path: Path) -> Path:
        if not source_path.exists():
            raise HTTPException(status_code=404, detail="Source PDF is unavailable")
        try:
            import fitz
        except ImportError as exc:
            raise HTTPException(status_code=503, detail="PDF preview support is not installed") from exc
        target = self.settings.preview_dir / document_id / f"{page_number}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        document = fitz.open(source_path)
        try:
            page = document.load_page(page_number - 1)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(self.settings.preview_scale, self.settings.preview_scale), alpha=False)
            pixmap.save(target)
            self.repository.set_preview_path(document_id, page_number, str(target), float(pixmap.width), float(pixmap.height))
        finally:
            document.close()
        return target
