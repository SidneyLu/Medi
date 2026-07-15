from app.core.responses import AppError
from app.core.security import create_access_token, hash_password, verify_password
from app.models.schemas import AuthData, LoginRequest, RegisterRequest
from app.services.storage import Store


class AuthService:
    def __init__(self, store: Store) -> None:
        self.store = store

    def register(self, payload: RegisterRequest) -> AuthData:
        user = self.store.create_user(payload.email, hash_password(payload.password))
        if user is None:
            raise AppError(status_code=409, code=40901, message="Email already registered")
        token, expires_in = create_access_token(user["id"], user["email"])
        self.store.add_audit_log(user["id"], "auth.register", {"email": user["email"]})
        return AuthData(
            user_id=user["id"],
            email=user["email"],
            access_token=token,
            token_type="bearer",
            expires_in=expires_in,
        )

    def login(self, payload: LoginRequest) -> AuthData:
        user = self.store.get_user_by_email(payload.email)
        if user is None or not verify_password(payload.password, user["password_hash"]):
            raise AppError(status_code=401, code=40108, message="Invalid email or password")
        token, expires_in = create_access_token(user["id"], user["email"])
        self.store.add_audit_log(user["id"], "auth.login", {"email": user["email"]})
        return AuthData(
            user_id=user["id"],
            access_token=token,
            token_type="bearer",
            expires_in=expires_in,
        )
