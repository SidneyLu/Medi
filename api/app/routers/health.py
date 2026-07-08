from fastapi import APIRouter

from app.db.base import init_db
from app.services.vector_store import VectorStoreService

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    init_db()
    vector_store = VectorStoreService()
    vector_store.heartbeat()
    return {"status": "ok"}
