from app.core.responses import AppError
from app.core.security import create_session_token, hash_password, verify_password
from app.models.schemas import LoginRequest, RegisterRequest, UserData
from app.services.application_repository import ApplicationRepository


class AuthService:
    def __init__(self, repository: ApplicationRepository) -> None:
        self.repository = repository

    def register(self, payload: RegisterRequest) -> tuple[UserData, str, int]:
        user = self.repository.create_user(payload.email, hash_password(payload.password))
        if user is None:
            raise AppError(status_code=409, code=40901, message="Email already registered", error_type="request_failed")
        token, max_age = create_session_token(user["id"], user["email"])
        self.repository.add_audit_log(user["id"], "auth.register", {"email": user["email"]})
        return self.to_user_data(user), token, max_age

    def login(self, payload: LoginRequest) -> tuple[UserData, str, int]:
        user = self.repository.get_user_by_email(payload.email)
        if user is None or not verify_password(payload.password, user["password_hash"]):
            raise AppError(status_code=401, code=40108, message="Invalid email or password", error_type="request_failed")
        token, max_age = create_session_token(user["id"], user["email"])
        self.repository.add_audit_log(user["id"], "auth.login", {"email": user["email"]})
        return self.to_user_data(user), token, max_age

    def to_user_data(self, user: dict) -> UserData:
        profile, _tags = self.repository.get_profile(user["id"])
        nickname = (profile or {}).get("nickname") or user["email"].split("@", 1)[0]
        return UserData(user_id=user["id"], email=user["email"], nickname=nickname)
