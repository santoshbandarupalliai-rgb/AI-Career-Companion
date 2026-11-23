from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas.auth import AuthResponse, LoginRequest, RefreshRequest, RegisterRequest, UserOut
from app.services import auth_service
from app.services.auth_service import AuthError

router = APIRouter(prefix="/api/auth", tags=["Auth"])


def _raise(exc: AuthError) -> None:
    headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
    raise HTTPException(status_code=exc.status_code, detail=exc.message, headers=headers)


def _auth_response(user: User, access: str, refresh: str) -> AuthResponse:
    return AuthResponse(access_token=access, refresh_token=refresh, user=UserOut.model_validate(user))


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> AuthResponse:
    """Create an account and sign the user in straight away."""
    try:
        user = auth_service.register_user(db, payload.full_name, payload.email, payload.password)
    except AuthError as exc:
        _raise(exc)
    access, refresh = auth_service.issue_tokens(db, user)
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
def me(user: User = Depends(get_current_user)) -> User:
    return user
