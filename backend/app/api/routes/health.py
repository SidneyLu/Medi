from fastapi import APIRouter

from app.core.responses import ApiResponse, ok

router = APIRouter(tags=["health"])


@router.get("/health", response_model=ApiResponse[dict[str, str]])
def health_check() -> ApiResponse[dict[str, str]]:
    return ok({"status": "ok", "service": "medi-backend"})
