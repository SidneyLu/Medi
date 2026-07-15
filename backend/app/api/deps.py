from functools import lru_cache
from typing import Annotated, Any

from fastapi import Cookie, Depends

from app.core.config import get_settings
from app.core.responses import AppError
from app.core.security import SESSION_COOKIE_NAME, decode_session_token
from app.services.auth_service import AuthService
from app.services.knowledge_service import KnowledgeService
from app.services.profile_service import ProfileService
from app.services.rag_service import RagService
from app.services.report_service import ReportService
from app.services.storage import Store


@lru_cache
def get_store() -> Store:
    settings = get_settings()
    store = Store(settings.database_path, settings.seed_knowledge_path)
    store.initialize()
    return store


def get_auth_service(store: Annotated[Store, Depends(get_store)]) -> AuthService:
    return AuthService(store)


def get_profile_service(store: Annotated[Store, Depends(get_store)]) -> ProfileService:
    return ProfileService(store)


def get_knowledge_service(store: Annotated[Store, Depends(get_store)]) -> KnowledgeService:
    return KnowledgeService(store)


def get_rag_service(store: Annotated[Store, Depends(get_store)]) -> RagService:
    return RagService(store)


def get_report_service(store: Annotated[Store, Depends(get_store)]) -> ReportService:
    return ReportService(store)


def get_current_user(
    store: Annotated[Store, Depends(get_store)],
    medi_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> dict[str, Any]:
    if not medi_session:
        raise AppError(status_code=401, code=40101, message="Not authenticated", error_type="request_failed")

    payload = decode_session_token(medi_session)
    user_id = payload.get("sub")
    if not user_id:
        raise AppError(status_code=401, code=40102, message="Invalid session", error_type="request_failed")

    user = store.get_user_by_id(user_id)
    if user is None:
        raise AppError(status_code=401, code=40103, message="User no longer exists", error_type="request_failed")
    return user
