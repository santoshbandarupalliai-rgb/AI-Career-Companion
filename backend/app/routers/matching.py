import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.rag.embeddings import EmbeddingError
from app.schemas.matching import Explanation, GapReport, MatchList, MatchOut, PlanOut, PlanRequest
from app.services import matching_service, plan_service
from app.services.internship_service import InternshipError
from app.services.matching_service import GapTargetError

router = APIRouter(prefix="/api/matching", tags=["Matching"])
gap_router = APIRouter(prefix="/api/skill-gap", tags=["Skill Gap"])

_NO_EMBED = "The search model is unavailable right now. Please try again shortly."


def _not_found(exc: InternshipError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


@router.get("", response_model=MatchList)
def list_matches(
    limit: int = Query(50, ge=1, le=200),
    min_score: float = Query(0.0, ge=0, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Every visible internship scored against the signed-in student's verified skills (no AI involved)."""
    return matching_service.match_all(db, user.id, limit=limit, min_score=min_score)


@router.get("/{internship_id}", response_model=MatchOut)
def get_match(internship_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        return matching_service.match_one(db, user.id, internship_id)
    except InternshipError as exc:
        raise _not_found(exc)


@router.post("/{internship_id}/explain", response_model=Explanation)
def explain_match(internship_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """AI-written explanation of a score. The score is recomputed server-side; nothing is taken from the client."""
    try:
        match = matching_service.match_one(db, user.id, internship_id)
    except InternshipError as exc:
        raise _not_found(exc)
    return plan_service.explain_match(match)


def _gap(db: Session, user_id: uuid.UUID, internship_id: uuid.UUID | None, role: str | None) -> GapReport:
    try:
        return matching_service.gap_report(db, user_id, internship_id=internship_id, role=role)
    except InternshipError as exc:
        raise _not_found(exc)
    except GapTargetError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EmbeddingError:
        raise HTTPException(status_code=503, detail=_NO_EMBED)


@gap_router.get("", response_model=GapReport)
def skill_gap(
    internship_id: uuid.UUID | None = None,
    role: str | None = Query(None, min_length=2, max_length=150),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Missing skills for one internship, or aggregated across the best-matching postings for a role."""
    return _gap(db, user.id, internship_id, role)


@gap_router.post("/plan", response_model=PlanOut)
def learning_plan(payload: PlanRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """AI learning plan for the gap. The gap is recomputed server-side from the target; the client sends no skills."""
    gap = _gap(db, user.id, payload.internship_id, payload.role)
    plan, message = plan_service.make_plan(gap)
    return PlanOut(gap=gap, plan=plan, plan_available=plan is not None, message=message)
