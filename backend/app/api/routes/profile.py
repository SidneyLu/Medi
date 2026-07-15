from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user, get_profile_service
from app.core.responses import ApiResponse, ok
from app.models.schemas import ProfileData, ProfilePayload
from app.services.profile_service import ProfileService

router = APIRouter(prefix="/profile", tags=["profile"])


@router.put("", response_model=ApiResponse[ProfileData])
def upsert_profile(
    payload: ProfilePayload,
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    service: Annotated[ProfileService, Depends(get_profile_service)],
) -> ApiResponse[ProfileData]:
    return ok(service.upsert_profile(current_user["id"], payload))


@router.get("", response_model=ApiResponse[ProfileData])
def get_profile(
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    service: Annotated[ProfileService, Depends(get_profile_service)],
) -> ApiResponse[ProfileData]:
    return ok(service.get_profile(current_user["id"]))
