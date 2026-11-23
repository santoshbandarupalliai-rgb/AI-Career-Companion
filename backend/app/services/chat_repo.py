"""Chat persistence. Every function REQUIRES user_id and assistant_type and filters on both.

This is the single place chat rows are read or written, so isolation between users,
sessions and assistants cannot be forgotten by a caller. A session that belongs to
another user or another assistant is indistinguishable from one that does not exist.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ChatMessage, ChatSession, MessageFeedback
from app.models.user import utcnow


class ChatNotFound(LookupError):
    pass


def create_session(db: Session, user_id: uuid.UUID, assistant_type: str, title: str = "New chat") -> ChatSession:
    s = ChatSession(user_id=user_id, assistant_type=assistant_type, title=title[:120])
    db.add(s)
    db.commit()
    return s


def list_sessions(db: Session, user_id: uuid.UUID, assistant_type: str) -> list[ChatSession]:
    return list(
        db.scalars(
            select(ChatSession)
            .where(ChatSession.user_id == user_id, ChatSession.assistant_type == assistant_type)
            .order_by(ChatSession.updated_at.desc())
        )
    )


def get_session(db: Session, user_id: uuid.UUID, assistant_type: str, session_id: uuid.UUID) -> ChatSession:
    s = db.scalar(
        select(ChatSession).where(
            ChatSession.id == session_id, ChatSession.user_id == user_id, ChatSession.assistant_type == assistant_type
        )
    )
    if s is None:
        raise ChatNotFound("Chat not found")
    return s


def get_messages(db: Session, user_id: uuid.UUID, assistant_type: str, session_id: uuid.UUID) -> list[ChatMessage]:
    """Messages of one session, oldest first. Verifies ownership of the session first."""
    get_session(db, user_id, assistant_type, session_id)
    return list(
        db.scalars(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id, ChatMessage.user_id == user_id)
            .order_by(ChatMessage.created_at, ChatMessage.seq)
        )
    )


def add_turn(
    db: Session,
    user_id: uuid.UUID,
    assistant_type: str,
    session_id: uuid.UUID,
    user_text: str,
    assistant_text: str,
    citations: list[dict],
    tool_calls: list[dict] | None = None,
) -> tuple[ChatMessage, ChatMessage]:
    """Store one question/answer pair and touch the session. Commits."""
    session = get_session(db, user_id, assistant_type, session_id)
    first = db.scalar(select(ChatMessage.id).where(ChatMessage.session_id == session.id).limit(1)) is None
    now = utcnow()
    u = ChatMessage(session_id=session.id, user_id=user_id, seq=0, role="user", content=user_text, created_at=now)
    a = ChatMessage(
        session_id=session.id, user_id=user_id, seq=1, role="assistant", content=assistant_text,
        citations=citations, tool_calls=tool_calls or [], created_at=now,
    )
    db.add_all([u, a])
    if first and session.title == "New chat":
        session.title = (" ".join(user_text.split()))[:60] or "New chat"
    session.updated_at = now
    db.commit()
    return u, a


def delete_session(db: Session, user_id: uuid.UUID, assistant_type: str, session_id: uuid.UUID) -> None:
    s = get_session(db, user_id, assistant_type, session_id)
    db.delete(s)
    db.commit()


def set_summary(db: Session, user_id: uuid.UUID, assistant_type: str, session_id: uuid.UUID, summary: str, count: int) -> None:
    s = get_session(db, user_id, assistant_type, session_id)
    s.summary, s.summarized_count = summary, count
    db.commit()


def get_assistant_message(
    db: Session, user_id: uuid.UUID, assistant_type: str, message_id: uuid.UUID, *, for_update: bool = False
) -> ChatMessage:
    """An assistant message in one of this user's sessions of this assistant type, else ChatNotFound."""
    q = (
        select(ChatMessage)
        .join(ChatSession, ChatSession.id == ChatMessage.session_id)
        .where(
            ChatMessage.id == message_id,
            ChatMessage.user_id == user_id,
            ChatMessage.role == "assistant",
            ChatSession.user_id == user_id,
            ChatSession.assistant_type == assistant_type,
        )
    )
    if for_update:
        q = q.with_for_update(of=ChatMessage).execution_options(populate_existing=True)  # fresh tool_calls
    msg = db.scalar(q)
    if msg is None:
        raise ChatNotFound("Message not found")
    return msg


def set_tool_calls(msg: ChatMessage, tool_calls: list[dict]) -> None:
    """Replace a message's tool_calls (a new list, so the JSON column is marked dirty). Caller commits."""
    msg.tool_calls = [dict(t) for t in tool_calls]


def set_feedback(
    db: Session, user_id: uuid.UUID, assistant_type: str, message_id: uuid.UUID, rating: int
) -> ChatMessage:
    """Rate an assistant message. The message must be in one of this user's sessions of this assistant type."""
    msg = db.scalar(
        select(ChatMessage)
        .join(ChatSession, ChatSession.id == ChatMessage.session_id)
        .where(
            ChatMessage.id == message_id,
            ChatMessage.user_id == user_id,
            ChatMessage.role == "assistant",
            ChatSession.user_id == user_id,
            ChatSession.assistant_type == assistant_type,
        )
    )
    if msg is None:
        raise ChatNotFound("Message not found")
    row = db.scalar(select(MessageFeedback).where(MessageFeedback.message_id == msg.id, MessageFeedback.user_id == user_id))
    if row is None:
        db.add(MessageFeedback(message_id=msg.id, user_id=user_id, rating=rating))
    else:
        row.rating = rating
    db.commit()
    return msg


def feedback_for(db: Session, user_id: uuid.UUID, message_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not message_ids:
        return {}
    rows = db.execute(
        select(MessageFeedback.message_id, MessageFeedback.rating).where(
            MessageFeedback.user_id == user_id, MessageFeedback.message_id.in_(message_ids)
        )
    )
    return {m: r for m, r in rows}
