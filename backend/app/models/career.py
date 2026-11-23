import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.types import JSONType
from app.models.user import utcnow


class GeneratedDocument(Base):
    """A tailored resume or cover letter the student reviewed and approved."""

    __tablename__ = "generated_documents"
    __table_args__ = (
        CheckConstraint("kind IN ('resume','cover_letter')", name="kind_valid"),
        Index("ix_generated_documents_user_created", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(15), nullable=False)
    internship_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("internships.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[dict] = mapped_column(JSONType, nullable=False)
    facts_used: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    flagged: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)  # flags the student acknowledged
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class InterviewSession(Base):
    __tablename__ = "interview_sessions"
    __table_args__ = (Index("ix_interview_sessions_user_created", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(150), nullable=False)
    internship_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("internships.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    items: Mapped[list["InterviewItem"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="InterviewItem.position"
    )


class InterviewItem(Base):
    __tablename__ = "interview_items"
    __table_args__ = (
        CheckConstraint("category IN ('technical','behavioral','resume','situational')", name="category_valid"),
        CheckConstraint("difficulty IN ('easy','medium','hard')", name="difficulty_valid"),
        CheckConstraint("score IS NULL OR (score >= 0 AND score <= 10)", name="score_range"),
        Index("ix_interview_items_user_session", "user_id", "session_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interview_sessions.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(15), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(10), nullable=False)
    user_answer: Mapped[str | None] = mapped_column(Text)
    score: Mapped[int | None] = mapped_column(Integer)
    feedback: Mapped[dict | None] = mapped_column(JSONType)  # strengths, improvements, outline
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    session: Mapped[InterviewSession] = relationship(back_populates="items")
