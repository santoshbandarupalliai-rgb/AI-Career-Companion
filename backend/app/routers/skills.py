import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import StudentSkill, User
from app.schemas.profile import BulkVerify, SkillCreate, SkillOut, SkillsResponse, SkillStatusUpdate
from app.services import skill_service
from app.services.skill_service import SkillError

router = APIRouter(prefix="/api/skills", tags=["Skills"])


def _out(row: StudentSkill) -> SkillOut:
    return SkillOut(
        id=row.id,
        name=row.skill.name,
        category=row.skill.category,
        status=row.status,
        source=row.source,
        evidence=row.evidence,
        resume_id=row.resume_id,
    )


def _bad(exc: SkillError) -> HTTPException:
    code = 404 if str(exc) == "Skill not found" else 400
    return HTTPException(status_code=code, detail=str(exc))


@router.get("", response_model=SkillsResponse)
def my_skills(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    groups = skill_service.list_skills(db, user.id)
    return SkillsResponse(**{k: [_out(r) for r in v] for k, v in groups.items()})


@router.post("", response_model=SkillOut, status_code=status.HTTP_201_CREATED)
def add_skill(payload: SkillCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        return _out(skill_service.add_manual(db, user.id, payload.name))
    except SkillError as exc:
        raise _bad(exc)


@router.patch("/{skill_id}", response_model=SkillOut)
def update_status(
    skill_id: uuid.UUID, payload: SkillStatusUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    try:
        return _out(skill_service.set_status(db, user.id, skill_id, payload.status))
    except SkillError as exc:
        raise _bad(exc)


@router.post("/verify", response_model=dict)
def verify_many(payload: BulkVerify, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {"verified": skill_service.verify_many(db, user.id, payload.ids)}


@router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_skill(skill_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        skill_service.delete_manual(db, user.id, skill_id)
    except SkillError as exc:
        raise _bad(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
