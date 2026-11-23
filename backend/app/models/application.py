import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.user import utcnow

APPLICATION_STATUSES = ("saved", "applied", "oa", "interview", "offer", "rejected", "withdrawn")
_STATUS_SQL = ",".join(f"'{s}'" for s in APPLICATION_STATUSES)


class Application(Base):
    """One internship the student is tracking, from 'saved' to an outcome."""

    __tablename__ = "applications"
    __table_args__ = (
        CheckConstraint(f"status IN ({_STATUS_SQL})", name="status_valid"),
        # NULL internship_id (an external posting) never collides; a posting can be tracked once.
        UniqueConstraint("user_id", "internship_id", name="uq_applications_user_internship"),
        Index("ix_applications_user_updated", "user_id", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    internship_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("internships.id", ondelete="SET NULL"))
    company: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(15), nullable=False, default="saved")
    applied_on: Mapped[date | None] = mapped_column(Date)
    deadline: Mapped[date | None] = mapped_column(Date)
    resume_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("resumes.id", ondelete="SET NULL"))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    events: Mapped[list["ApplicationEvent"]] = relationship(
        back_populates="application", cascade="all, delete-orphan", order_by="ApplicationEvent.created_at"
    )


class ApplicationEvent(Base):
    """Status history. from_status is NULL for the event that created the application."""

    __tablename__ = "application_events"
    __table_args__ = (Index("ix_application_events_application_created", "application_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(15))
    to_status: Mapped[str] = mapped_column(String(15), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    application: Mapped[Application] = relationship(back_populates="events")
