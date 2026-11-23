"""Career Assistant API. Entirely separate from the Product Assistant router (/api/chat/product)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.llm import LLMError
from app.models import ChatMessage, ChatSession, User
from app.schemas.chat import (
    ActionDecision,
    CareerMessageOut,
    CareerSendResponse,
    CareerSessionDetail,
    FeedbackIn,
    SendMessage,
    SessionCreate,
    SessionOut,
)
from app.services import career_actions, career_assistant, chat_repo
from app.services.chat_repo import ChatNotFound

router = APIRouter(prefix="/api/chat/career", tags=["Career Assistant"])
T = career_assistant.ASSISTANT_TYPE


def _session_out(s: ChatSession) -> SessionOut:
    return SessionOut(id=s.id, title=s.title, created_at=s.created_at, updated_at=s.updated_at)


def _msg_out(m: ChatMessage, rating: int | None = None) -> CareerMessageOut:
    calls = m.tool_calls or []
    steps = [{"tool": t["tool"], "args": t.get("args") or {}, "ok": t.get("ok", True), "summary": t.get("summary", "")}
             for t in calls if t.get("type") == "step"]
    actions = [{k: t.get(k) for k in ("id", "kind", "label", "state", "result")} for t in calls if t.get("type") == "action"]
    return CareerMessageOut(id=m.id, role=m.role, content=m.content, steps=steps, actions=actions, rating=rating,
                            created_at=m.created_at)


def _404(exc: Exception) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [_session_out(s) for s in chat_repo.list_sessions(db, user.id, T)]


@router.post("/sessions", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
def create_session(payload: SessionCreate | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    title = (payload.title.strip() if payload and payload.title else "") or "New chat"
    return _session_out(chat_repo.create_session(db, user.id, T, title))


@router.get("/sessions/{session_id}", response_model=CareerSessionDetail)
def get_session(session_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        session = chat_repo.get_session(db, user.id, T, session_id)
        messages = chat_repo.get_messages(db, user.id, T, session_id)
    except ChatNotFound as exc:
        raise _404(exc)
    ratings = chat_repo.feedback_for(db, user.id, [m.id for m in messages])
    return CareerSessionDetail(session=_session_out(session), messages=[_msg_out(m, ratings.get(m.id)) for m in messages])


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(session_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        chat_repo.delete_session(db, user.id, T, session_id)
    except ChatNotFound as exc:
        raise _404(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/sessions/{session_id}/messages", response_model=CareerSendResponse)
def send_message(
    session_id: uuid.UUID, payload: SendMessage, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    try:
        user_msg, asst_msg = career_assistant.run(db, user.id, session_id, payload.content)
        session = chat_repo.get_session(db, user.id, T, session_id)
    except ChatNotFound as exc:
        raise _404(exc)
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc) or "The AI service is unavailable right now. Please try again in a moment.")
    return CareerSendResponse(session=_session_out(session), user_message=_msg_out(user_msg), assistant_message=_msg_out(asst_msg))


@router.post("/messages/{message_id}/actions/{action_id}", response_model=CareerMessageOut)
def resolve_action(
    message_id: uuid.UUID, action_id: str, payload: ActionDecision,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    try:
        msg = career_actions.resolve(db, user.id, message_id, action_id[:20], payload.decision)
    except (ChatNotFound, career_actions.ActionNotFound) as exc:
        raise _404(exc)
    except career_actions.ActionAlreadyResolved as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    rating = chat_repo.feedback_for(db, user.id, [msg.id]).get(msg.id)
    return _msg_out(msg, rating)


@router.put("/messages/{message_id}/feedback", response_model=CareerMessageOut)
def rate_message(message_id: uuid.UUID, payload: FeedbackIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        msg = chat_repo.set_feedback(db, user.id, T, message_id, payload.rating)
    except ChatNotFound as exc:
        raise _404(exc)
    return _msg_out(msg, payload.rating)
