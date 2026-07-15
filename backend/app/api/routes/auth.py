from typing import Annotated, Any

from fastapi import APIRouter, Depends, status

from app.api.deps import get_auth_service, get_current_user
from app.core.responses import ApiResponse, ok
from app.models.schemas import AuthSessionData, LoginRequest, RegisterRequest, UserData
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def _to_auth_session(user: UserData, token: str, expires_in: int) -> AuthSessionData:
    return AuthSessionData(
        user_id=user.user_id,
        email=user.email,
        nickname=user.nickname,
        access_token=token,
        token_type="bearer",
        expires_in=expires_in,
    )


@router.post("/register", response_model=ApiResponse[AuthSessionData], status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> ApiResponse[AuthSessionData]:
    user, token, expires_in = service.register(payload)
    return ok(_to_auth_session(user, token, expires_in))


@router.post("/login", response_model=ApiResponse[AuthSessionData])
def login(
    payload: LoginRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> ApiResponse[AuthSessionData]:
    user, token, expires_in = service.login(payload)
    return ok(_to_auth_session(user, token, expires_in))


@router.post("/logout", response_model=ApiResponse[None])
def logout() -> ApiResponse[None]:
    # Token is cleared on the client; server is currently stateless for access tokens.
    return ok(None)


@router.get("/me", response_model=ApiResponse[UserData])
def me(
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> ApiResponse[UserData]:
    return ok(service.to_user_data(current_user))
