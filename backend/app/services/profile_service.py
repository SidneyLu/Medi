from app.models.schemas import ProfileData, ProfilePayload
from app.services.label_rules import build_profile_tags
from app.services.storage import Store


class ProfileService:
    def __init__(self, store: Store) -> None:
        self.store = store

    def upsert_profile(self, user_id: str, payload: ProfilePayload) -> ProfileData:
        profile = payload.model_dump()
        tags = build_profile_tags(profile)
        self.store.upsert_profile(user_id, profile, tags)
        self.store.add_audit_log(user_id, "profile.upsert", {"tags": tags})
        return ProfileData(profile=payload, tags=tags)

    def get_profile(self, user_id: str) -> ProfileData:
        profile, tags = self.store.get_profile(user_id)
        if profile is None:
            return ProfileData(profile=None, tags=[])
        return ProfileData(profile=ProfilePayload(**profile), tags=tags)
