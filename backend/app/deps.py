"""Shared FastAPI dependencies."""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app import security
from app.config import get_settings
from app.db import get_db
from app.models import User

_bearer = HTTPBearer(auto_error=False)


def get_current_user_any(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """The signed-in user, verified or not. Used only by the endpoints an unverified user must reach."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if creds is None or creds.scheme.lower() != "bearer":
        raise unauthorized
    try:
        user_id = security.decode_token(creds.credentials, security.ACCESS)
    except security.TokenError:
        raise unauthorized
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorized
    return user


def get_current_user(user: User = Depends(get_current_user_any)) -> User:
    """The signed-in user. With REQUIRE_EMAIL_VERIFICATION on, unverified accounts are refused."""
    if get_settings().require_email_verification and not user.email_verified:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Please verify your email address to continue.")
    return user
