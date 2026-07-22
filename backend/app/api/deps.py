from functools import lru_cache
from typing import Annotated, Any

from fastapi import Depends, Header

from app.core.config import get_settings
from app.core.responses import AppError
from app.core.security import decode_session_token
from app.services.application_repository import ApplicationRepository
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


@lru_cache
def get_application_repository() -> ApplicationRepository:
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required for Medi application data")
    repository = ApplicationRepository(settings.database_url)
    repository.initialize()
    return repository


def get_auth_service(repository: Annotated[ApplicationRepository, Depends(get_application_repository)]) -> AuthService:
    return AuthService(repository)


def get_profile_service(repository: Annotated[ApplicationRepository, Depends(get_application_repository)]) -> ProfileService:
    return ProfileService(repository)


def get_knowledge_service(store: Annotated[Store, Depends(get_store)]) -> KnowledgeService:
    return KnowledgeService(store)


def get_rag_service(
    repository: Annotated[ApplicationRepository, Depends(get_application_repository)],
    store: Annotated[Store, Depends(get_store)],
) -> RagService:
    return RagService(repository, store)


@lru_cache
def get_report_service() -> ReportService:
    # Cache the service so PaddleOCR model stays loaded across uploads.
    return ReportService(get_application_repository(), get_store())


def get_current_user(
    repository: Annotated[ApplicationRepository, Depends(get_application_repository)],
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AppError(status_code=401, code=40101, message="Not authenticated", error_type="request_failed")

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise AppError(status_code=401, code=40101, message="Not authenticated", error_type="request_failed")

    payload = decode_session_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise AppError(status_code=401, code=40102, message="Invalid session", error_type="request_failed")

    user = repository.get_user_by_id(user_id)
    if user is None:
        raise AppError(status_code=401, code=40103, message="User no longer exists", error_type="request_failed")
    return user
