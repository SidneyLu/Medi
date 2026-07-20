from app.models.schemas import ProfileData, ProfilePayload
from app.services.application_repository import ApplicationRepository
from app.services.label_rules import build_profile_tags


class ProfileService:
    def __init__(self, repository: ApplicationRepository) -> None:
        self.repository = repository

    def upsert_profile(self, user_id: str, payload: ProfilePayload) -> ProfileData:
        profile = payload.model_dump()
        tags = build_profile_tags(profile)
        self.repository.upsert_profile(user_id, profile, tags)
        self.repository.add_audit_log(user_id, "profile.upsert", {"tags": tags})
        return ProfileData(profile=payload, tags=tags)

    def get_profile(self, user_id: str) -> ProfileData:
        profile, tags = self.repository.get_profile(user_id)
        if profile is None:
            return ProfileData(profile=None, tags=[])
        return ProfileData(profile=ProfilePayload(**profile), tags=tags)
