import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.llm import LLMError
from app.models import InterviewItem, InterviewSession, User
from app.schemas.interview import AnswerIn, ItemOut, SessionCreate, SessionDetail, SessionSummary
from app.services import interview_service
from app.services.interview_service import InterviewError, NotFound
from app.services.internship_service import InternshipError

router = APIRouter(prefix="/api/interview", tags=["Interview Prep"])


def _item(i: InterviewItem) -> ItemOut:
    return ItemOut(id=i.id, position=i.position, question=i.question, category=i.category, difficulty=i.difficulty,
                   user_answer=i.user_answer, score=i.score, feedback=i.feedback, answered_at=i.answered_at)


def _summary(s: InterviewSession) -> SessionSummary:
    scores = [i.score for i in s.items if i.score is not None]
    return SessionSummary(id=s.id, role=s.role, internship_id=s.internship_id, created_at=s.created_at, total=len(s.items),
                          answered=len(scores), average_score=round(sum(scores) / len(scores), 1) if scores else None)


def _llm_503(exc: LLMError) -> HTTPException:
    return HTTPException(status_code=503, detail=str(exc) or "The AI service is unavailable right now.")


@router.get("/sessions", response_model=list[SessionSummary])
def list_sessions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [_summary(s) for s in interview_service.list_sessions(db, user.id)]


@router.post("/sessions", response_model=SessionDetail, status_code=status.HTTP_201_CREATED)
async def create_session(payload: SessionCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Generate practice questions for a role and/or internship. Nothing is created if the AI cannot produce questions."""
    try:
        s = await run_in_threadpool(
            interview_service.create_session, db, user.id, role=payload.role, internship_id=payload.internship_id, count=payload.count
        )
    except InternshipError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except InterviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except LLMError as exc:
        raise _llm_503(exc)
    return SessionDetail(session=_summary(s), items=[_item(i) for i in s.items])


@router.get("/sessions/{session_id}", response_model=SessionDetail)
def get_session(session_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        s = interview_service.get_session(db, user.id, session_id)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return SessionDetail(session=_summary(s), items=[_item(i) for i in s.items])


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(session_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        interview_service.delete_session(db, user.id, session_id)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/sessions/{session_id}/items/{item_id}/answer", response_model=ItemOut)
async def answer(
    session_id: uuid.UUID, item_id: uuid.UUID, payload: AnswerIn,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """Score an answer against a fixed rubric. The answer is saved only if scoring succeeds."""
    try:
        item = await run_in_threadpool(interview_service.answer_item, db, user.id, session_id, item_id, payload.answer)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except InterviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except LLMError as exc:
        raise _llm_503(exc)
    return _item(item)
