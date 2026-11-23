import uuid
from typing import Literal

from pydantic import BaseModel, Field


class Factor(BaseModel):
    key: str
    label: str
    weight: float  # nominal weight (0..1)
    applicable: bool  # False when the posting or profile does not give enough information
    effective_weight: float  # weight after redistributing the weight of non-applicable factors
    value: float | None  # 0..1, None when not applicable
    contribution: float  # points added to the overall score (0..100)
    detail: str


class EligibilityCheck(BaseModel):
    key: str
    label: str
    status: Literal["met", "not_met", "unknown"]
    detail: str


class MatchOut(BaseModel):
    internship_id: uuid.UUID
    title: str
    company: str
    source: str
    overall: float  # 0..100
    factors: list[Factor]
    matched_required: list[str]
    missing_required: list[str]
    matched_preferred: list[str]
    missing_preferred: list[str]
    # Missing skills that appear in the student's resume but are not verified yet (not counted).
    unverified_in_resume: list[str]
    eligibility: list[EligibilityCheck]
    verified_skill_count: int
    notes: list[str] = Field(default_factory=list)


class MatchSummary(BaseModel):
    internship_id: uuid.UUID
    title: str
    company: str
    location: str | None
    work_mode: str | None
    source: str
    overall: float
    required_matched: int
    required_total: int
    missing_required: list[str]


class MatchList(BaseModel):
    items: list[MatchSummary]
    verified_skill_count: int
    notes: list[str] = Field(default_factory=list)


class Explanation(BaseModel):
    narrative: str | None
    available: bool
    message: str | None = None


class GapSkill(BaseModel):
    name: str
    importance: Literal["required", "preferred"]
    demand: int  # number of considered postings that ask for it
    of: int  # number of postings considered
    unverified_in_resume: bool  # it is in the resume but not verified yet


class GapTarget(BaseModel):
    type: Literal["internship", "role"]
    label: str
    postings_considered: list[str]


class GapReport(BaseModel):
    target: GapTarget
    acquired: list[str]
    critical: list[GapSkill]
    secondary: list[GapSkill]
    coverage: float | None  # share of the target's skill demand covered by verified skills, 0..100
    verified_skill_count: int
    notes: list[str] = Field(default_factory=list)


class PlanStep(BaseModel):
    skill: str
    why: str
    how_to_learn: str
    practice_project: str


class LearningPlan(BaseModel):
    summary: str = ""
    steps: list[PlanStep] = Field(default_factory=list)


class PlanOut(BaseModel):
    gap: GapReport
    plan: LearningPlan | None
    plan_available: bool
    message: str | None = None


class PlanRequest(BaseModel):
    internship_id: uuid.UUID | None = None
    role: str | None = Field(default=None, min_length=2, max_length=150)
