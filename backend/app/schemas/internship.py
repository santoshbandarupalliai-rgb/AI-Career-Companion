import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

WorkMode = Literal["remote", "onsite", "hybrid"]


class InternshipSkillOut(BaseModel):
    name: str
    category: str | None
    importance: Literal["required", "preferred"]


class InternshipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    company: str
    description: str
    location: str | None
    work_mode: str | None
    stipend: str | None
    duration: str | None
    education_req: str | None
    experience_req: str | None
    eligibility_text: str | None
    apply_url: str | None
    source: Literal["sample", "user"]
    is_active: bool
    created_at: datetime
    skills: list[InternshipSkillOut]
    # Only set for semantic search results.
    score: float | None = None
    snippet: str | None = None


class InternshipList(BaseModel):
    items: list[InternshipOut]
    total: int


class SkillInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    importance: Literal["required", "preferred"] = "required"


def _clean(v: str | None) -> str | None:
    v = (v or "").strip()
    return v or None


class InternshipCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    company: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=20, max_length=20000)
    location: str | None = Field(default=None, max_length=150)
    work_mode: WorkMode | None = None
    stipend: str | None = Field(default=None, max_length=100)
    duration: str | None = Field(default=None, max_length=100)
    education_req: str | None = Field(default=None, max_length=300)
    experience_req: str | None = Field(default=None, max_length=300)
    eligibility_text: str | None = Field(default=None, max_length=5000)
    apply_url: str | None = Field(default=None, max_length=500)
    skills: list[SkillInput] = Field(default_factory=list, max_length=40)

    @field_validator("location", "stipend", "duration", "education_req", "experience_req", "eligibility_text", "apply_url")
    @classmethod
    def _blank_to_none(cls, v):
        return _clean(v)

    @field_validator("apply_url")
    @classmethod
    def _url(cls, v):
        if v and not v.lower().startswith(("http://", "https://")):
            raise ValueError("Apply link must start with http:// or https://")
        return v


class ExtractRequest(BaseModel):
    text: str = Field(min_length=40, max_length=30000)


class ExtractedDraft(BaseModel):
    """A draft for the user to review and edit. Nothing is saved until they confirm."""

    title: str = ""
    company: str = ""
    location: str = ""
    work_mode: str = ""
    stipend: str = ""
    duration: str = ""
    education_req: str = ""
    experience_req: str = ""
    eligibility_text: str = ""
    apply_url: str = ""
    skills: list[SkillInput] = Field(default_factory=list)
    description: str
    method: Literal["llm", "heuristic"]
    warnings: list[str] = Field(default_factory=list)
