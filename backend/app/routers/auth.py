from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user_any
from app.models import User
from app.schemas.auth import AuthResponse, LoginRequest, RefreshRequest, RegisterRequest, ResendOut, UserOut, VerifyEmailRequest
from app.services import auth_service, email_service
from app.services.auth_service import AuthError

router = APIRouter(prefix="/api/auth", tags=["Auth"])


def _raise(exc: AuthError) -> None:
    headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
    raise HTTPException(status_code=exc.status_code, detail=exc.message, headers=headers)


def _auth_response(user: User, access: str, refresh: str) -> AuthResponse:
    return AuthResponse(access_token=access, refresh_token=refresh, user=UserOut.model_validate(user))


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, background: BackgroundTasks, db: Session = Depends(get_db)) -> AuthResponse:
    """Create an account, sign the user in and email a verification link."""
    try:
        user = auth_service.register_user(db, payload.full_name, payload.email, payload.password)
    except AuthError as exc:
        _raise(exc)
    access, refresh = auth_service.issue_tokens(db, user)
    token = auth_service.create_verification_token(db, user)
    background.add_task(email_service.send_verification_email, user.email, user.full_name, token)
    return _auth_response(user, access, refresh)


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> AuthResponse:
    try:
        user = auth_service.authenticate(db, payload.email, payload.password)
    except AuthError as exc:
        _raise(exc)
    access, refresh = auth_service.issue_tokens(db, user)
    return _auth_response(user, access, refresh)


@router.post("/refresh", response_model=AuthResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> AuthResponse:
    """Exchange a refresh token for a new pair. The old refresh token is revoked."""
    try:
        user, access, new_refresh = auth_service.rotate_refresh(db, payload.refresh_token)
    except AuthError as exc:
        _raise(exc)
    return _auth_response(user, access, new_refresh)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: RefreshRequest, db: Session = Depends(get_db)) -> Response:
    auth_service.logout(db, payload.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user_any)) -> User:
    return user


@router.post("/verify-email", response_model=UserOut)
def verify_email(payload: VerifyEmailRequest, db: Session = Depends(get_db)) -> User:
    """Confirm an email address with the token from the verification link."""
    try:
        return auth_service.verify_email(db, payload.token)
    except AuthError as exc:
        _raise(exc)


@router.post("/resend-verification", response_model=ResendOut)
def resend_verification(
    background: BackgroundTasks, user: User = Depends(get_current_user_any), db: Session = Depends(get_db)
) -> ResendOut:
    if user.email_verified:
        return ResendOut(sent=False, already_verified=True, message="Your email is already verified.")
    wait = auth_service.seconds_until_resend(db, user)
    if wait > 0:
        raise HTTPException(status_code=429, detail=f"Please wait {wait} seconds before requesting another email.")
    token = auth_service.create_verification_token(db, user)
    background.add_task(email_service.send_verification_email, user.email, user.full_name, token)
    if email_service.smtp_configured():
        return ResendOut(sent=True, message="We sent you a new verification email.")
    return ResendOut(sent=False, message="Email sending is not configured on this server, so no email was sent. The link is in the server log.")
