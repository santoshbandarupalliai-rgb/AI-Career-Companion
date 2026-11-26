import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.profile import Skill
from app.models.types import EmbeddingType, JSONType
from app.models.user import utcnow


class Internship(Base):
    """An internship posting. `source='sample'` rows are fictional seed data and are labelled as such in the UI."""

    __tablename__ = "internships"
    __table_args__ = (
        CheckConstraint("source IN ('sample','user')", name="source_valid"),
        CheckConstraint("work_mode IN ('remote','onsite','hybrid') OR work_mode IS NULL", name="work_mode_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    company: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str | None] = mapped_column(String(150))
    work_mode: Mapped[str | None] = mapped_column(String(20))
    stipend: Mapped[str | None] = mapped_column(String(100))
    duration: Mapped[str | None] = mapped_column(String(100))
    education_req: Mapped[str | None] = mapped_column(String(300))
    experience_req: Mapped[str | None] = mapped_column(String(300))
    eligibility_text: Mapped[str | None] = mapped_column(Text)
    apply_url: Mapped[str | None] = mapped_column(String(500))
    source: Mapped[str] = mapped_column(String(10), nullable=False, default="user")
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Stable key so re-running the seed never duplicates sample postings.
    seed_key: Mapped[str | None] = mapped_column(String(100), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    skills: Mapped[list["InternshipSkill"]] = relationship(
        back_populates="internship", cascade="all, delete-orphan", lazy="selectin"
    )


class InternshipSkill(Base):
    __tablename__ = "internship_skills"
    __table_args__ = (
        UniqueConstraint("internship_id", "skill_id", name="uq_internship_skills_internship_skill"),
        CheckConstraint("importance IN ('required','preferred')", name="importance_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    internship_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("internships.id", ondelete="CASCADE"), index=True, nullable=False
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), nullable=False)
    importance: Mapped[str] = mapped_column(String(10), nullable=False, default="required")

    internship: Mapped[Internship] = relationship(back_populates="skills")
    skill: Mapped[Skill] = relationship(lazy="joined")


class RagDocument(Base):
    """A source document in a retrieval corpus ('internship' now, 'product' in Phase 4)."""

    __tablename__ = "rag_documents"
    __table_args__ = (
        CheckConstraint("corpus IN ('internship','product','prep_doc')", name="corpus_valid"),
        UniqueConstraint("corpus", "source_key", name="uq_rag_documents_corpus_source_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    corpus: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    source_key: Mapped[str] = mapped_column(String(200), nullable=False)  # e.g. internship id, or doc path
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # skip re-embedding unchanged text
    meta: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    chunks: Mapped[list["RagChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="RagChunk.chunk_index"
    )


class RagChunk(Base):
    __tablename__ = "rag_chunks"
    __table_args__ = (
        Index(
            "ix_rag_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rag_documents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    corpus: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # denormalised for filtered search
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(EmbeddingType, nullable=False)

    document: Mapped[RagDocument] = relationship(back_populates="chunks")
