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


def create_access_token(user_id: str, email: str) -> tuple[str, int]:
    settings = get_settings()
    now = int(time.time())
    expires_at = now + settings.access_token_expire_seconds
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user_id,
        "email": email,
        "iat": now,
        "exp": expires_at,
        "jti": str(uuid.uuid4()),
    }
    signing_input = ".".join(
        [
            _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8")),
            _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
        ]
    )
    signature = hmac.new(
        settings.secret_key.encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{signing_input}.{_b64url_encode(signature)}", settings.access_token_expire_seconds


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        header_b64, payload_b64, signature_b64 = token.split(".", 2)
    except ValueError as exc:
        raise AppError(status_code=401, code=40104, message="Malformed access token") from exc

    signing_input = f"{header_b64}.{payload_b64}"
    expected_signature = hmac.new(
        settings.secret_key.encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    try:
        actual_signature = _b64url_decode(signature_b64)
        payload = json.loads(_b64url_decode(payload_b64))
    except (ValueError, json.JSONDecodeError) as exc:
        raise AppError(status_code=401, code=40105, message="Invalid access token") from exc

    if not hmac.compare_digest(expected_signature, actual_signature):
        raise AppError(status_code=401, code=40106, message="Invalid token signature")

    if int(payload.get("exp", 0)) < int(time.time()):
        raise AppError(status_code=401, code=40107, message="Access token expired")
    return payload
