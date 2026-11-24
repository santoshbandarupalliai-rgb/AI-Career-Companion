import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Category = Literal["technical", "behavioral", "resume", "situational"]
Difficulty = Literal["easy", "medium", "hard"]


# ---------- LLM output ----------

class QuestionLLM(BaseModel):
    question: str
    category: Category
    difficulty: Difficulty


class QuestionsLLM(BaseModel):
    questions: list[QuestionLLM] = Field(default_factory=list)


class EvaluationLLM(BaseModel):
    """Rubric: relevance and accuracy (0-4) + structure and clarity (0-3) + depth and examples (0-3)."""

    relevance: int = Field(ge=0, le=4)
    structure: int = Field(ge=0, le=3)
    depth: int = Field(ge=0, le=3)
    strengths: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    answer_outline: str = ""


# ---------- API ----------

class SessionCreate(BaseModel):
    role: str | None = Field(default=None, min_length=2, max_length=150)
    internship_id: uuid.UUID | None = None
    resume_id: uuid.UUID | None = None  # which resume to ask about; defaults to the active one
    count: int = Field(default=8, ge=3, le=10)


class Feedback(BaseModel):
    relevance: int
    structure: int
    depth: int
    strengths: list[str]
    improvements: list[str]
    answer_outline: str


class ItemOut(BaseModel):
    id: uuid.UUID
    position: int
    question: str
    category: Category
    difficulty: Difficulty
    user_answer: str | None
    score: int | None
    feedback: Feedback | None
    answered_at: datetime | None


class SessionSummary(BaseModel):
    id: uuid.UUID
    role: str
    internship_id: uuid.UUID | None
    created_at: datetime
    total: int
    answered: int
    average_score: float | None


class SessionDetail(BaseModel):
    session: SessionSummary
    items: list[ItemOut]


class AnswerIn(BaseModel):
    answer: str = Field(min_length=10, max_length=3000)

    @field_validator("answer")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 10:
            raise ValueError("Write at least a sentence before submitting")
        return v


class CategoryResult(BaseModel):
    category: Category
    answered: int
    average: float


class ReportOut(BaseModel):
    """Diagnostic summary of a practice session, computed from the saved scores (no AI call)."""

    total: int
    answered: int
    unanswered: int
    average_score: float | None
    level: str
    level_note: str
    by_category: list[CategoryResult]
    strongest: Category | None
    weakest: Category | None
    top_strengths: list[str]
    top_improvements: list[str]
