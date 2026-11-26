import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Status = Literal["saved", "applied", "oa", "interview", "offer", "rejected", "withdrawn"]


def _clean(v):
    if isinstance(v, str):
        v = " ".join(v.split())
        return v or None
    return v


class ApplicationCreate(BaseModel):
    """Track a posting from the knowledge base (internship_id) or an external one (company + role)."""

    internship_id: uuid.UUID | None = None
    company: str | None = Field(default=None, max_length=200)
    role: str | None = Field(default=None, max_length=200)
    status: Status = "saved"
    applied_on: date | None = None
    deadline: date | None = None
    resume_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator("company", "role", mode="before")
    @classmethod
    def _clean_text(cls, v):
        return _clean(v)

    @model_validator(mode="after")
    def _target(self):
        if not self.internship_id and not (self.company and self.role):
            raise ValueError("Choose an internship, or enter both company and role")
        return self


class ApplicationUpdate(BaseModel):
    """Fields that can be edited. Status changes go through the status endpoint (they are logged)."""

    company: str | None = Field(default=None, max_length=200)
    role: str | None = Field(default=None, max_length=200)
    applied_on: date | None = None
    deadline: date | None = None
    resume_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator("company", "role", mode="before")
    @classmethod
    def _clean_text(cls, v):
        return _clean(v)


class StatusChange(BaseModel):
    status: Status
    note: str | None = Field(default=None, max_length=500)


class EventOut(BaseModel):
    id: uuid.UUID
    from_status: str | None
    to_status: str
    note: str | None
    created_at: datetime


class ApplicationOut(BaseModel):
    id: uuid.UUID
    internship_id: uuid.UUID | None
    internship_source: str | None  # 'sample' | 'user' | None (external or posting deleted)
    company: str
    role: str
    status: Status
    applied_on: date | None
    deadline: date | None
    resume_id: uuid.UUID | None
    resume_name: str | None
    stipend: str | None = None  # from the linked posting, when it states one
    notes: str | None
    created_at: datetime
    updated_at: datetime


class ApplicationDetail(ApplicationOut):
    events: list[EventOut]


class ApplicationList(BaseModel):
    items: list[ApplicationOut]
    counts: dict[str, int]  # per status, over all of this user's applications


class ApplyRequest(BaseModel):
    """Demo 'Apply': records an application as Applied in the tracker. Nothing is sent to any company."""

    internship_id: uuid.UUID
    resume_id: uuid.UUID | None = None  # defaults to the active resume
    notes: str | None = Field(default=None, max_length=1000)
