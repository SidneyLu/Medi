from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import SourceDocument
from app.db.session import get_db

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("/{document_id}")
def get_source(document_id: int, db: Session = Depends(get_db)):
    document = db.execute(select(SourceDocument).where(SourceDocument.id == document_id)).scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=404, detail="source document not found")
    return {
        "document_id": document.id,
        "sku_id": document.sku_id,
        "source_type": document.source_type,
        "title": document.title,
        "url": document.url,
        "published_at": document.published_at,
        "crawled_at": document.crawled_at,
        "raw_storage_path": document.raw_storage_path,
        "clean_text_path": document.clean_text_path,
    }
