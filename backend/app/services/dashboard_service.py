"""Dashboard status. Read-only, built from the existing services; it stores nothing and calls no LLM."""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Resume, StudentProfile
from app.schemas.dashboard import (
    ApplicationSummary,
    DashboardOut,
    DeadlineOut,
    NextStep,
    ProfileStatus,
    ResumeStatus,
    SkillCounts,
)
from app.services import application_service, resume_service, skill_service

# The fields the matching and tailoring features actually read.
PROFILE_KEYS = [
    ("college", "College"),
    ("degree", "Degree"),
    ("branch", "Branch"),
    ("graduation_year", "Graduation year"),
    ("cgpa", "CGPA"),
    ("target_role", "Target role"),
]
ACTIVE_STATUSES = ("saved", "applied", "oa", "interview")
MAX_DEADLINES = 5


def _profile_status(profile: StudentProfile | None) -> ProfileStatus:
    missing = [label for key, label in PROFILE_KEYS if profile is None or getattr(profile, key) in (None, "")]
    return ProfileStatus(filled=len(PROFILE_KEYS) - len(missing), total=len(PROFILE_KEYS), missing=missing)


def next_step(profile: ProfileStatus, resume: ResumeStatus, skills: SkillCounts, apps: ApplicationSummary) -> NextStep:
    """First unmet prerequisite wins, so a new student sees one clear action."""
    if not resume.has_active:
        return NextStep(message="Upload your resume so Career Companion can read your skills.", path="/profile", label="Upload a resume")
    if skills.verified == 0 and skills.extracted > 0:
        return NextStep(message="Verify your skills to get match scores. Only skills you confirm are used.", path="/resume", label="Review skills")
    if skills.verified == 0:
        return NextStep(message="Add the skills you have. Only skills you confirm are used for matching.", path="/resume", label="Add skills")
    if profile.filled < profile.total:
        return NextStep(message="Complete your profile (" + ", ".join(profile.missing) + ") for better matches.", path="/profile", label="Complete profile")
    if apps.total == 0:
        return NextStep(message="See which internships fit you, then track the ones you like.", path="/matching", label="View matches")
    if apps.upcoming_deadlines:
        d = apps.upcoming_deadlines[0]
        return NextStep(message=f"{d.role} at {d.company} is due in {d.days_left} day(s).", path="/applications", label="Open tracker")
    return NextStep(message="Practice interview questions for the roles you are tracking.", path="/interview", label="Practice interviews")


def build(db: Session, user_id: uuid.UUID, today: date | None = None) -> DashboardOut:
    today = today or date.today()
    profile = db.scalar(select(StudentProfile).where(StudentProfile.user_id == user_id))
    p = _profile_status(profile)

    resumes: list[Resume] = resume_service.list_for_user(db, user_id)
    active = next((r for r in resumes if r.is_active), None)
    r = ResumeStatus(
        count=len(resumes),
        has_active=active is not None,
        active_filename=active.original_filename if active else None,
        extraction_status=active.extraction_status if active else None,
    )

    groups = skill_service.list_skills(db, user_id)
    s = SkillCounts(verified=len(groups["verified"]), extracted=len(groups["extracted"]), rejected=len(groups["rejected"]))

    items, counts = application_service.list_applications(db, user_id)
    due = sorted(
        (a for a in items if a.deadline is not None and a.deadline >= today and a.status in ACTIVE_STATUSES),
        key=lambda a: a.deadline,
    )[:MAX_DEADLINES]
    apps = ApplicationSummary(
        total=sum(counts.values()),
        by_status=counts,
        upcoming_deadlines=[
            DeadlineOut(
                application_id=str(a.id), company=a.company, role=a.role, status=a.status,
                deadline=a.deadline, days_left=(a.deadline - today).days,
            )
            for a in due
        ],
    )
    return DashboardOut(profile=p, resume=r, skills=s, applications=apps, next_step=next_step(p, r, s, apps))
