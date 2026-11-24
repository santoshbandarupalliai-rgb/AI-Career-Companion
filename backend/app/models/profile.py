import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.types import JSONType
from app.models.user import utcnow


class StudentProfile(Base):
    """Student-entered profile. Starts empty: nothing is ever invented for the user."""

    __tablename__ = "student_profiles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    phone: Mapped[str | None] = mapped_column(String(30))
    college: Mapped[str | None] = mapped_column(String(200))
    degree: Mapped[str | None] = mapped_column(String(150))
    branch: Mapped[str | None] = mapped_column(String(150))
    cgpa: Mapped[float | None] = mapped_column(Float)
    graduation_year: Mapped[int | None] = mapped_column(Integer)
    target_role: Mapped[str | None] = mapped_column(String(150))
    location: Mapped[str | None] = mapped_column(String(150))
    bio: Mapped[str | None] = mapped_column(Text)
    linkedin_url: Mapped[str | None] = mapped_column(String(300))
    github_url: Mapped[str | None] = mapped_column(String(300))
    portfolio_url: Mapped[str | None] = mapped_column(String(300))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    label: Mapped[str | None] = mapped_column(String(100))  # optional friendly name, e.g. "Backend resume"
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # pending | complete | partial | failed
    extraction_status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    extraction: Mapped["ResumeExtraction | None"] = relationship(
        back_populates="resume", cascade="all, delete-orphan", uselist=False
    )


class ResumeExtraction(Base):
    """Latest structured extraction for a resume (one row per resume)."""

    __tablename__ = "resume_extractions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    resume_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("resumes.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    data: Mapped[dict] = mapped_column(JSONType, nullable=False)
    method: Mapped[str] = mapped_column(String(20), nullable=False)  # llm | heuristic
    model: Mapped[str | None] = mapped_column(String(100))
    warnings: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    resume: Mapped[Resume] = relationship(back_populates="extraction")


class Skill(Base):
    """Canonical skill vocabulary, shared by students and (later) internships."""

    __tablename__ = "skills"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    canonical: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str | None] = mapped_column(String(50))


class StudentSkill(Base):
    """A skill attached to a student.

    status:
      extracted: found in a resume, not yet confirmed by the student
      verified:  confirmed (or added) by the student
      rejected:  the student says it is wrong; never re-added automatically
    """

    __tablename__ = "student_skills"
    __table_args__ = (
        UniqueConstraint("user_id", "skill_id", name="uq_student_skills_user_skill"),
        CheckConstraint("status IN ('extracted','verified','rejected')", name="status_valid"),
        CheckConstraint("source IN ('resume','manual')", name="source_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    resume_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("resumes.id", ondelete="SET NULL"))
    evidence: Mapped[str | None] = mapped_column(String(300))  # snippet of resume text where it was found
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    skill: Mapped[Skill] = relationship(lazy="joined")
