import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import Internship, User
from app.rag.embeddings import EmbeddingError
from app.schemas.internship import (
    ExtractedDraft,
    ExtractRequest,
    InternshipCreate,
    InternshipList,
    InternshipOut,
    InternshipSkillOut,
    SkillInput,
)
from app.services import internship_service, jd_parser
from app.services.internship_service import InternshipError

router = APIRouter(prefix="/api/internships", tags=["Internships"])

WorkModeQ = Literal["remote", "onsite", "hybrid"]
SourceQ = Literal["sample", "user"]


def _out(item: Internship, score: float | None = None, snippet: str | None = None) -> InternshipOut:
    skills = sorted(item.skills, key=lambda s: (s.importance != "required", s.skill.name.lower()))
    return InternshipOut(
        id=item.id, title=item.title, company=item.company, description=item.description,
        location=item.location, work_mode=item.work_mode, stipend=item.stipend, duration=item.duration,
        education_req=item.education_req, experience_req=item.experience_req,
        eligibility_text=item.eligibility_text, apply_url=item.apply_url, source=item.source,
        is_active=item.is_active, created_at=item.created_at,
        skills=[InternshipSkillOut(name=s.skill.name, category=s.skill.category, importance=s.importance) for s in skills],
        score=score, snippet=snippet,
    )


def _not_found(exc: InternshipError) -> HTTPException:
    code = 404 if "not found" in str(exc).lower() else 400
    return HTTPException(status_code=code, detail=str(exc))


def _embedding_unavailable(exc: EmbeddingError) -> HTTPException:
    return HTTPException(status_code=503, detail="The search model is unavailable right now. Please try again shortly.")


@router.get("", response_model=InternshipList)
def list_internships(
    q: str | None = Query(None, max_length=100),
    work_mode: WorkModeQ | None = None,
    location: str | None = Query(None, max_length=100),
    skill: str | None = Query(None, max_length=100),
    source: SourceQ | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items, total = internship_service.list_internships(
        db, user.id, q=q, work_mode=work_mode, location=location, skill=skill, source=source, limit=limit, offset=offset
    )
    return InternshipList(items=[_out(i) for i in items], total=total)


@router.get("/search", response_model=list[InternshipOut])
def search_internships(
    q: str = Query(..., min_length=2, max_length=300),
    work_mode: WorkModeQ | None = None,
    location: str | None = Query(None, max_length=100),
    skill: str | None = Query(None, max_length=100),
    source: SourceQ | None = None,
    limit: int = Query(10, ge=1, le=30),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        results = internship_service.semantic_search(
            db, user.id, q, work_mode=work_mode, location=location, skill=skill, source=source, limit=limit
        )
    except EmbeddingError as exc:
        raise _embedding_unavailable(exc)
    return [_out(item, round(score, 4), snippet[:300]) for item, score, snippet in results]


@router.post("/extract", response_model=ExtractedDraft)
def extract_from_jd(payload: ExtractRequest, user: User = Depends(get_current_user)):
    """Parse a pasted job description into an editable draft. Saves nothing."""
    ex, method, warnings = jd_parser.extract_jd(payload.text)
    skills = [SkillInput(name=n, importance="required") for n in ex.required_skills] + [
        SkillInput(name=n, importance="preferred") for n in ex.preferred_skills
    ]
    return ExtractedDraft(
        title=ex.title, company=ex.company, location=ex.location, work_mode=ex.work_mode, stipend=ex.stipend,
        duration=ex.duration, education_req=ex.education_req, experience_req=ex.experience_req,
        eligibility_text=ex.eligibility_text, apply_url=ex.apply_url, skills=skills,
        description=payload.text.strip(), method=method, warnings=warnings,
    )


@router.post("", response_model=InternshipOut, status_code=status.HTTP_201_CREATED)
def create_internship(payload: InternshipCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        item = internship_service.create_user_internship(db, user.id, payload)
    except EmbeddingError as exc:
        raise _embedding_unavailable(exc)
    return _out(item)


@router.get("/{internship_id}", response_model=InternshipOut)
def get_internship(internship_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        return _out(internship_service.get_internship(db, user.id, internship_id))
    except InternshipError as exc:
        raise _not_found(exc)


@router.delete("/{internship_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_internship(internship_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        internship_service.delete_user_internship(db, user.id, internship_id)
    except InternshipError as exc:
        raise _not_found(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
