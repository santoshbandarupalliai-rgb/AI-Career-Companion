"""Password hashing and JWT helpers."""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import get_settings

ACCESS = "access"
REFRESH = "refresh"


class TokenError(Exception):
    """Raised for any invalid, expired or wrong-type token."""


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def _create_token(subject: str, token_type: str, lifetime: timedelta) -> tuple[str, datetime]:
    s = get_settings()
    now = datetime.now(timezone.utc)
    expires = now + lifetime
    payload = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": expires,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, s.secret_key, algorithm=s.jwt_algorithm), expires


def create_access_token(user_id: uuid.UUID) -> str:
    minutes = get_settings().access_token_expire_minutes
    return _create_token(str(user_id), ACCESS, timedelta(minutes=minutes))[0]


def create_refresh_token(user_id: uuid.UUID) -> tuple[str, datetime]:
    days = get_settings().refresh_token_expire_days
    return _create_token(str(user_id), REFRESH, timedelta(days=days))


def decode_token(token: str, expected_type: str) -> uuid.UUID:
    s = get_settings()
    try:
        payload = jwt.decode(
            token, s.secret_key, algorithms=[s.jwt_algorithm], options={"require": ["exp", "sub", "type"]}
        )
    except jwt.PyJWTError as exc:
        raise TokenError("Invalid or expired token") from exc
    if payload.get("type") != expected_type:
        raise TokenError("Wrong token type")
    try:
        return uuid.UUID(payload["sub"])
    except (ValueError, TypeError) as exc:
        raise TokenError("Invalid token subject") from exc


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
