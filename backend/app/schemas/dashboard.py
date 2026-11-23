from datetime import date

from pydantic import BaseModel, Field


class ProfileStatus(BaseModel):
    filled: int
    total: int
    missing: list[str] = Field(default_factory=list)  # labels of empty key fields


class ResumeStatus(BaseModel):
    count: int
    has_active: bool
    active_filename: str | None = None
    extraction_status: str | None = None


class SkillCounts(BaseModel):
    verified: int
    extracted: int  # found in a resume, waiting for the student's review
    rejected: int


class DeadlineOut(BaseModel):
    application_id: str
    company: str
    role: str
    status: str
    deadline: date
    days_left: int


class ApplicationSummary(BaseModel):
    total: int
    by_status: dict[str, int]
    upcoming_deadlines: list[DeadlineOut] = Field(default_factory=list)


class NextStep(BaseModel):
    message: str
    path: str
    label: str


class DashboardOut(BaseModel):
    profile: ProfileStatus
    resume: ResumeStatus
    skills: SkillCounts
    applications: ApplicationSummary
    next_step: NextStep
