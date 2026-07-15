import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from typing import Any

from app.core.config import get_settings
from app.core.responses import AppError


SESSION_COOKIE_NAME = "medi_session"


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return f"pbkdf2_sha256${_b64url_encode(salt)}${_b64url_encode(digest)}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, salt_b64, digest_b64 = stored_hash.split("$", 2)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    salt = _b64url_decode(salt_b64)
    expected = _b64url_decode(digest_b64)
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return hmac.compare_digest(actual, expected)


def create_session_token(user_id: str, email: str) -> tuple[str, int]:
    settings = get_settings()
    now = int(time.time())
    expires_at = now + settings.session_expire_seconds
    payload = {
        "sub": user_id,
        "email": email,
        "iat": now,
        "exp": expires_at,
        "jti": str(uuid.uuid4()),
    }
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(
        settings.secret_key.encode("utf-8"),
        payload_b64.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{payload_b64}.{_b64url_encode(signature)}", settings.session_expire_seconds


def decode_session_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload_b64, signature_b64 = token.split(".", 1)
    except ValueError as exc:
        raise AppError(status_code=401, code=40104, message="Malformed session token", error_type="request_failed") from exc

    expected_signature = hmac.new(
        settings.secret_key.encode("utf-8"),
        payload_b64.encode("ascii"),
        hashlib.sha256,
    ).digest()
    try:
        actual_signature = _b64url_decode(signature_b64)
        payload = json.loads(_b64url_decode(payload_b64))
    except (ValueError, json.JSONDecodeError) as exc:
        raise AppError(status_code=401, code=40105, message="Invalid session token", error_type="request_failed") from exc

    if not hmac.compare_digest(expected_signature, actual_signature):
        raise AppError(status_code=401, code=40106, message="Invalid session signature", error_type="request_failed")

    if int(payload.get("exp", 0)) < int(time.time()):
        raise AppError(status_code=401, code=40107, message="Session expired", error_type="request_failed")
    return payload
