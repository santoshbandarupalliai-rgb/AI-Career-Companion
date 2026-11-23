"""Product Assistant API. Entirely separate from the (future) Career Assistant router."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.llm import LLMError
from app.models import ChatMessage, ChatSession, User
from app.rag.embeddings import EmbeddingError
from app.schemas.chat import (
    FeedbackIn,
    MessageOut,
    SendMessage,
    SendResponse,
    SessionCreate,
    SessionDetail,
    SessionOut,
)
from app.services import chat_repo, product_assistant
from app.services.chat_repo import ChatNotFound

router = APIRouter(prefix="/api/chat/product", tags=["Product Assistant"])
T = product_assistant.ASSISTANT_TYPE


def _session_out(s: ChatSession) -> SessionOut:
    return SessionOut(id=s.id, title=s.title, created_at=s.created_at, updated_at=s.updated_at)


def _msg_out(m: ChatMessage, rating: int | None = None) -> MessageOut:
    return MessageOut(id=m.id, role=m.role, content=m.content, citations=m.citations or [], rating=rating, created_at=m.created_at)


def _404(exc: ChatNotFound) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [_session_out(s) for s in chat_repo.list_sessions(db, user.id, T)]


@router.post("/sessions", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
def create_session(payload: SessionCreate | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    title = (payload.title.strip() if payload and payload.title else "") or "New chat"
    return _session_out(chat_repo.create_session(db, user.id, T, title))


@router.get("/sessions/{session_id}", response_model=SessionDetail)
def get_session(session_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        session = chat_repo.get_session(db, user.id, T, session_id)
        messages = chat_repo.get_messages(db, user.id, T, session_id)
    except ChatNotFound as exc:
        raise _404(exc)
    ratings = chat_repo.feedback_for(db, user.id, [m.id for m in messages])
    return SessionDetail(session=_session_out(session), messages=[_msg_out(m, ratings.get(m.id)) for m in messages])


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(session_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        chat_repo.delete_session(db, user.id, T, session_id)
    except ChatNotFound as exc:
        raise _404(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/sessions/{session_id}/messages", response_model=SendResponse)
def send_message(
    session_id: uuid.UUID, payload: SendMessage, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    try:
        _, _, user_msg, asst_msg = product_assistant.run(db, user.id, session_id, payload.content)
        session = chat_repo.get_session(db, user.id, T, session_id)
    except ChatNotFound as exc:
        raise _404(exc)
    except LLMError as exc:
        # LLMError messages are written to be user-safe (e.g. the rate-limit hint); see app/llm/client.py.
        raise HTTPException(status_code=503, detail=str(exc) or "The AI service is unavailable right now. Please try again in a moment.")
    except EmbeddingError:
        raise HTTPException(status_code=503, detail="The search model is unavailable right now. Please try again shortly.")
    return SendResponse(session=_session_out(session), user_message=_msg_out(user_msg), assistant_message=_msg_out(asst_msg))


@router.put("/messages/{message_id}/feedback", response_model=MessageOut)
def rate_message(message_id: uuid.UUID, payload: FeedbackIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        msg = chat_repo.set_feedback(db, user.id, T, message_id, payload.rating)
    except ChatNotFound as exc:
        raise _404(exc)
    return _msg_out(msg, payload.rating)
