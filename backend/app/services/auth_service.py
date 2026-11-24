"""Auth business logic. Routers stay thin and call these functions."""

import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import security
from app.config import get_settings
from app.models import EmailToken, RefreshToken, User

log = logging.getLogger(__name__)


class AuthError(Exception):
    def __init__(self, message: str, status_code: int = 401):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def register_user(db: Session, full_name: str, email: str, password: str) -> User:
    if db.scalar(select(User.id).where(User.email == email)):
        raise AuthError("An account with this email already exists", 409)
    user = User(full_name=full_name, email=email, hashed_password=security.hash_password(password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:  # race with a concurrent registration
        db.rollback()
        raise AuthError("An account with this email already exists", 409)
    db.refresh(user)
    log.info("user registered id=%s", user.id)
    return user


def authenticate(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == email))
    # Same message for unknown email and wrong password (no account enumeration).
    if user is None or not security.verify_password(password, user.hashed_password):
        raise AuthError("Invalid email or password", 401)
    if not user.is_active:
        raise AuthError("Account is disabled", 403)
    return user


def issue_tokens(db: Session, user: User) -> tuple[str, str]:
    access = security.create_access_token(user.id)
    refresh, expires = security.create_refresh_token(user.id)
    db.add(RefreshToken(user_id=user.id, token_hash=security.hash_token(refresh), expires_at=expires))
    db.commit()
    return access, refresh


def _find_valid_refresh(db: Session, token: str) -> RefreshToken:
    try:
        security.decode_token(token, security.REFRESH)
    except security.TokenError as exc:
        raise AuthError("Invalid refresh token") from exc
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == security.hash_token(token)))
    if row is None:
        raise AuthError("Invalid refresh token")
    expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
    if row.revoked or expires <= datetime.now(timezone.utc):
        if row.revoked:
            # A revoked token being replayed suggests theft: revoke the whole family.
            log.warning("revoked refresh token reused; revoking all sessions user=%s", row.user_id)
            revoke_all(db, row.user_id)
        raise AuthError("Refresh token expired or revoked")
    return row


def rotate_refresh(db: Session, token: str) -> tuple[User, str, str]:
    row = _find_valid_refresh(db, token)
    row.revoked = True
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        db.commit()
        raise AuthError("Account not available")
    access, refresh = issue_tokens(db, user)  # commits the revocation too
    return user, access, refresh


def logout(db: Session, token: str) -> None:
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == security.hash_token(token)))
    if row is not None and not row.revoked:
        row.revoked = True
        db.commit()


def revoke_all(db: Session, user_id: uuid.UUID) -> None:
    for row in db.scalars(
        select(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False))
    ):
        row.revoked = True
    db.commit()


# ---------- email verification ----------

RESEND_COOLDOWN_SECONDS = 60
PURPOSE = "verify_email"


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def create_verification_token(db: Session, user: User) -> str:
    """Issue a new one-time token (older unused ones stop working). Returns the raw token for the email."""
    for old in db.scalars(select(EmailToken).where(EmailToken.user_id == user.id, EmailToken.purpose == PURPOSE, EmailToken.used_at.is_(None))):
        old.used_at = datetime.now(timezone.utc)
    raw = secrets.token_urlsafe(32)
    hours = get_settings().verification_token_hours
    db.add(EmailToken(user_id=user.id, purpose=PURPOSE, token_hash=security.hash_token(raw),
                      expires_at=datetime.now(timezone.utc) + timedelta(hours=hours)))
    db.commit()
    return raw


def seconds_until_resend(db: Session, user: User) -> int:
    last = db.scalar(select(EmailToken.created_at).where(EmailToken.user_id == user.id, EmailToken.purpose == PURPOSE)
                     .order_by(EmailToken.created_at.desc()).limit(1))
    if last is None:
        return 0
    wait = RESEND_COOLDOWN_SECONDS - (datetime.now(timezone.utc) - _aware(last)).total_seconds()
    return max(0, int(wait) + (1 if wait > 0 else 0))


def verify_email(db: Session, token: str) -> User:
    """Mark the account's email as verified. A token works once and expires."""
    row = db.scalar(select(EmailToken).where(EmailToken.token_hash == security.hash_token(token), EmailToken.purpose == PURPOSE))
    if row is None or row.used_at is not None or _aware(row.expires_at) <= datetime.now(timezone.utc):
        raise AuthError("This verification link is invalid or has expired. Request a new one.", 400)
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise AuthError("Account not available", 400)
    row.used_at = datetime.now(timezone.utc)
    if user.email_verified_at is None:
        user.email_verified_at = datetime.now(timezone.utc)
    db.commit()
    log.info("email verified user=%s", user.id)
    return user
