from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_auth_service
from app.core.responses import ApiResponse, ok
from app.models.schemas import AuthData, LoginRequest, RegisterRequest
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=ApiResponse[AuthData])
def register(
    payload: RegisterRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> ApiResponse[AuthData]:
    return ok(service.register(payload))


@router.post("/login", response_model=ApiResponse[AuthData])
def login(
    payload: LoginRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> ApiResponse[AuthData]:
    return ok(service.login(payload))
