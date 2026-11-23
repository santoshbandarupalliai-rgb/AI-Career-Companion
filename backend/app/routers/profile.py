from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import StudentProfile, User
from app.schemas.profile import ProfileIn, ProfileOut

router = APIRouter(prefix="/api/profile", tags=["Profile"])

_FIELDS = list(ProfileIn.model_fields)


def _out(user: User, profile: StudentProfile | None) -> ProfileOut:
    values = {f: getattr(profile, f) if profile else None for f in _FIELDS}
    return ProfileOut(
        **values,
        full_name=user.full_name,
        email=user.email,
        updated_at=profile.updated_at if profile else None,
    )


@router.get("", response_model=ProfileOut)
def get_profile(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Returns empty fields until the student fills them in. Nothing is pre-filled."""
    profile = db.scalar(select(StudentProfile).where(StudentProfile.user_id == user.id))
    return _out(user, profile)


@router.put("", response_model=ProfileOut)
def update_profile(payload: ProfileIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    profile = db.scalar(select(StudentProfile).where(StudentProfile.user_id == user.id))
    if profile is None:
        profile = StudentProfile(user_id=user.id)
        db.add(profile)
    for field, value in payload.model_dump().items():
        setattr(profile, field, value)
    db.commit()
    db.refresh(profile)
    return _out(user, profile)
