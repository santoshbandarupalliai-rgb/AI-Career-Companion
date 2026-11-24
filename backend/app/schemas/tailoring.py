import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Flag(BaseModel):
    where: str  # e.g. "summary", "experience.0.bullet.2", "cover_letter.p2.s1"
    kind: Literal["number", "skill", "name", "overlap"]
    text: str
    message: str
    severity: Literal["warning", "removed"] = "warning"


# ---------- LLM output (what the model may produce) ----------

class _BulletsFor(BaseModel):
    source_index: int = Field(description="Index of the source entry these bullets rewrite")
    bullets: list[str] = Field(default_factory=list)


class ResumeDraftLLM(BaseModel):
    summary: str = ""
    skills: list[str] = Field(default_factory=list)
    experience: list[_BulletsFor] = Field(default_factory=list)
    projects: list[_BulletsFor] = Field(default_factory=list)


class CoverLetterLLM(BaseModel):
    paragraphs: list[str] = Field(default_factory=list)


# ---------- stored / returned documents ----------

class ResumeHeader(BaseModel):
    name: str
    email: str = ""
    phone: str = ""
    location: str = ""
    links: list[str] = Field(default_factory=list)


class ResumeEntry(BaseModel):
    source_index: int
    title: str = ""  # experience title or project name: ALWAYS copied from the source, never from the model
    organization: str = ""
    start: str = ""
    end: str = ""
    technologies: list[str] = Field(default_factory=list)
    bullets: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("bullets")
    @classmethod
    def _bullet_len(cls, v):
        v = [b.strip() for b in v if b and b.strip()]
        if any(len(b) > 400 for b in v):
            raise ValueError("A bullet is too long (max 400 characters)")
        return v


class EducationLine(BaseModel):
    text: str


class ResumeContent(BaseModel):
    header: ResumeHeader
    summary: str = Field(default="", max_length=1500)
    skills: list[str] = Field(default_factory=list, max_length=40)
    experience: list[ResumeEntry] = Field(default_factory=list, max_length=12)
    projects: list[ResumeEntry] = Field(default_factory=list, max_length=12)
    education: list[EducationLine] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)


class CoverLetterContent(BaseModel):
    greeting: str = "Dear Hiring Manager,"
    paragraphs: list[str] = Field(default_factory=list, max_length=6)
    closing: str = "Sincerely,"
    name: str = ""

    @field_validator("paragraphs")
    @classmethod
    def _paras(cls, v):
        v = [p.strip() for p in v if p and p.strip()]
        if any(len(p) > 2000 for p in v):
            raise ValueError("A paragraph is too long (max 2000 characters)")
        return v


class GenerateRequest(BaseModel):
    internship_id: uuid.UUID
    kind: Literal["resume", "cover_letter"]
    resume_id: uuid.UUID | None = None  # which of the student's resumes to use; defaults to the active one


class Draft(BaseModel):
    """A generated draft. Nothing is saved until the student approves it."""

    kind: Literal["resume", "cover_letter"]
    internship_id: uuid.UUID
    title: str
    content: dict
    facts_used: list[str]
    flags: list[Flag]
    notes: list[str] = Field(default_factory=list)


class SaveRequest(BaseModel):
    kind: Literal["resume", "cover_letter"]
    internship_id: uuid.UUID | None = None
    title: str | None = Field(default=None, max_length=300)
    content: dict
    acknowledge_flags: bool = False


class DocumentOut(BaseModel):
    id: uuid.UUID
    kind: Literal["resume", "cover_letter"]
    internship_id: uuid.UUID | None
    title: str
    content: dict
    facts_used: list[str]
    flagged: list[Flag]
    created_at: datetime


class DocumentSummary(BaseModel):
    id: uuid.UUID
    kind: Literal["resume", "cover_letter"]
    title: str
    flagged_count: int
    created_at: datetime
