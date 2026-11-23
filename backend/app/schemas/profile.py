import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

_URL_RE = re.compile(r"^(https?://)?([\w-]+\.)+[\w-]{2,}(/\S*)?$", re.I)


def _blank_to_none(v):
    if isinstance(v, str):
        v = " ".join(v.split())
        return v or None
    return v


class ProfileIn(BaseModel):
    """All fields optional; empty strings clear a field."""

    phone: str | None = Field(default=None, max_length=30)
    college: str | None = Field(default=None, max_length=200)
    degree: str | None = Field(default=None, max_length=150)
    branch: str | None = Field(default=None, max_length=150)
    cgpa: float | None = Field(default=None, ge=0, le=10)
    graduation_year: int | None = Field(default=None, ge=1990, le=2100)
    target_role: str | None = Field(default=None, max_length=150)
    location: str | None = Field(default=None, max_length=150)
    bio: str | None = Field(default=None, max_length=2000)
    linkedin_url: str | None = Field(default=None, max_length=300)
    github_url: str | None = Field(default=None, max_length=300)
    portfolio_url: str | None = Field(default=None, max_length=300)

    @field_validator("phone", "college", "degree", "branch", "target_role", "location", mode="before")
    @classmethod
    def _clean_text(cls, v):
        return _blank_to_none(v)

    @field_validator("bio", mode="before")
    @classmethod
    def _clean_bio(cls, v):
        if isinstance(v, str):
            return v.strip() or None
        return v

    @field_validator("cgpa", "graduation_year", mode="before")
    @classmethod
    def _empty_number(cls, v):
        return None if v == "" else v

    @field_validator("phone")
    @classmethod
    def _phone(cls, v):
        if v and not re.fullmatch(r"[+\d][\d\s()-]{6,28}", v):
            raise ValueError("Enter a valid phone number")
        return v

    @field_validator("linkedin_url", "github_url", "portfolio_url", mode="before")
    @classmethod
    def _url(cls, v):
        v = _blank_to_none(v)
        if v is None:
            return None
        if not _URL_RE.match(v):
            raise ValueError("Enter a valid URL")
        return v if v.lower().startswith(("http://", "https://")) else "https://" + v


class ProfileOut(ProfileIn):
    model_config = ConfigDict(from_attributes=True)

    full_name: str
    email: str
    updated_at: datetime | None = None


class ResumeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    original_filename: str
    content_type: str
    size_bytes: int
    page_count: int | None
    is_active: bool
    extraction_status: str
    uploaded_at: datetime


class ExtractionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    data: dict
    method: str
    model: str | None
    warnings: list[str]
    created_at: datetime


class ResumeDetail(ResumeOut):
    raw_text: str
    extraction: ExtractionOut | None


class SkillOut(BaseModel):
    id: uuid.UUID
    name: str
    category: str | None
    status: str
    source: str
    evidence: str | None
    resume_id: uuid.UUID | None


class SkillsResponse(BaseModel):
    verified: list[SkillOut]
    extracted: list[SkillOut]
    rejected: list[SkillOut]


class SkillStatusUpdate(BaseModel):
    status: str = Field(pattern="^(extracted|verified|rejected)$")


class SkillCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class BulkVerify(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
