from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import get_auth_service, get_current_user
from app.core.responses import ApiResponse, ok
from app.core.security import SESSION_COOKIE_NAME
from app.models.schemas import LoginRequest, RegisterRequest, UserData
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookie(response: Response, token: str, max_age: int) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )


@router.post("/register", response_model=ApiResponse[UserData], status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> ApiResponse[UserData]:
    user, token, max_age = service.register(payload)
    _set_session_cookie(response, token, max_age)
    return ok(user)


@router.post("/login", response_model=ApiResponse[UserData])
def login(
    payload: LoginRequest,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> ApiResponse[UserData]:
    user, token, max_age = service.login(payload)
    _set_session_cookie(response, token, max_age)
    return ok(user)


@router.post("/logout", response_model=ApiResponse[None])
def logout(response: Response) -> ApiResponse[None]:
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
    return ok(None)


@router.get("/me", response_model=ApiResponse[UserData])
def me(
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> ApiResponse[UserData]:
    return ok(service.to_user_data(current_user))
