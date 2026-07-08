from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.chat import ChatRequest
from app.services.rag_service import RagService

router = APIRouter(tags=["chat"])


@router.post("/chat")
def chat(payload: ChatRequest, db: Session = Depends(get_db)):
    service = RagService(db)
    return service.answer(payload)
