from functools import lru_cache
from typing import Annotated, Any

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings
from app.core.responses import AppError
from app.core.security import decode_access_token
from app.services.auth_service import AuthService
from app.services.knowledge_service import KnowledgeService
from app.services.profile_service import ProfileService
from app.services.rag_service import RagService
from app.services.report_service import ReportService
from app.services.storage import Store

bearer_scheme = HTTPBearer(auto_error=False)


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
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    store: Annotated[Store, Depends(get_store)],
) -> dict[str, Any]:
    if credentials is None:
        raise AppError(status_code=401, code=40101, message="Missing Authorization header")

    payload = decode_access_token(credentials.credentials)
    user_id = payload.get("sub")
    if not user_id:
        raise AppError(status_code=401, code=40102, message="Invalid access token")

    user = store.get_user_by_id(user_id)
    if user is None:
        raise AppError(status_code=401, code=40103, message="User no longer exists")
    return user
