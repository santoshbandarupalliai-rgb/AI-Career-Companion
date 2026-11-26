"""Application tracker. Every function takes user_id and only touches that user's rows.

Status changes are logged as ApplicationEvent rows. Any transition is allowed (students
correct mistakes), but a change to the same status is rejected so the history stays clean.
Company and role of an application linked to a posting are copied from that posting,
never typed in, so a tracked posting cannot be misrepresented.
"""

import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models import Application, ApplicationEvent, Internship, Resume
from app.models.application import APPLICATION_STATUSES
from app.models.user import utcnow
from app.schemas.application import ApplicationCreate, ApplicationUpdate
from app.services import internship_service

STATUS_LABELS = {
    "saved": "Saved", "applied": "Applied", "oa": "Online assessment", "interview": "Interview",
    "offer": "Offer", "rejected": "Rejected", "withdrawn": "Withdrawn",
}


class ApplicationError(ValueError):
    """Invalid request (400)."""


class ApplicationConflict(ApplicationError):
    """The posting is already tracked (409)."""


class ApplicationNotFound(LookupError):
    pass


def _owned_resume(db: Session, user_id: uuid.UUID, resume_id: uuid.UUID | None) -> None:
    if resume_id is None:
        return
    if db.scalar(select(Resume.id).where(Resume.id == resume_id, Resume.user_id == user_id)) is None:
        raise ApplicationError("Resume not found")


def get(db: Session, user_id: uuid.UUID, application_id: uuid.UUID) -> Application:
    app = db.scalar(
        select(Application)
        .where(Application.id == application_id, Application.user_id == user_id)
        .options(selectinload(Application.events))
    )
    if app is None:
        raise ApplicationNotFound("Application not found")
    return app


def list_applications(db: Session, user_id: uuid.UUID, status: str | None = None) -> tuple[list[Application], dict[str, int]]:
    q = select(Application).where(Application.user_id == user_id)
    if status:
        q = q.where(Application.status == status)
    items = list(db.scalars(q.order_by(Application.updated_at.desc())))
    counts = {s: 0 for s in APPLICATION_STATUSES}
    for s, n in db.execute(
        select(Application.status, func.count()).where(Application.user_id == user_id).group_by(Application.status)
    ):
        counts[s] = n
    return items, counts


def find_by_internship(db: Session, user_id: uuid.UUID, internship_id: uuid.UUID) -> Application | None:
    return db.scalar(select(Application).where(Application.user_id == user_id, Application.internship_id == internship_id))


def create(db: Session, user_id: uuid.UUID, payload: ApplicationCreate) -> Application:
    company, role = payload.company, payload.role
    if payload.internship_id:
        try:
            item = internship_service.get_internship(db, user_id, payload.internship_id)
        except internship_service.InternshipError:
            raise ApplicationError("Internship not found")
        if find_by_internship(db, user_id, item.id) is not None:
            raise ApplicationConflict(f"'{item.title}' at {item.company} is already in your tracker")
        company, role = item.company, item.title
    _owned_resume(db, user_id, payload.resume_id)

    applied_on = payload.applied_on
    if applied_on is None and payload.status not in ("saved", "withdrawn"):
        applied_on = date.today()  # past 'saved' means it was sent; the student can correct the date
    now = utcnow()
    app = Application(
        user_id=user_id, internship_id=payload.internship_id, company=company[:200], role=role[:200],
        status=payload.status, applied_on=applied_on, deadline=payload.deadline, resume_id=payload.resume_id,
        notes=(payload.notes or "").strip() or None, created_at=now, updated_at=now,
    )
    app.events.append(ApplicationEvent(user_id=user_id, from_status=None, to_status=payload.status, created_at=now))
    db.add(app)
    try:
        db.commit()
    except IntegrityError:  # concurrent duplicate add
        db.rollback()
        raise ApplicationConflict("This internship is already in your tracker")
    return app


DEMO_NOTE = "Applied through the app (demo: nothing was sent to the company)"


def apply(db: Session, user_id: uuid.UUID, internship_id: uuid.UUID, resume_id: uuid.UUID | None = None, notes: str | None = None) -> Application:
    """Demo 'Apply': record the application as Applied (creating it, or moving a Saved one forward).

    The posting must be visible to the student and the resume must be theirs; the active resume is used when none is
    chosen. An application that is already past Saved is a conflict. Nothing is sent anywhere.
    """
    try:
        item = internship_service.get_internship(db, user_id, internship_id)
    except internship_service.InternshipError:
        raise ApplicationError("Internship not found")
    _owned_resume(db, user_id, resume_id)
    if resume_id is None:
        resume_id = db.scalar(select(Resume.id).where(Resume.user_id == user_id, Resume.is_active.is_(True)))
    notes = (notes or "").strip() or None

    existing = find_by_internship(db, user_id, item.id)
    if existing is None:
        app = create(db, user_id, ApplicationCreate(internship_id=item.id, status="applied", resume_id=resume_id, notes=notes))
        app.events[0].note = DEMO_NOTE
        db.commit()
        return app
    if existing.status != "saved":
        raise ApplicationConflict(f"You have already applied to '{item.title}' at {item.company} (status: {STATUS_LABELS[existing.status]})")
    existing.resume_id = resume_id
    if notes:
        existing.notes = notes
    return change_status(db, user_id, existing.id, "applied", DEMO_NOTE)


def update(db: Session, user_id: uuid.UUID, application_id: uuid.UUID, payload: ApplicationUpdate) -> Application:
    app = get(db, user_id, application_id)
    data = payload.model_dump(exclude_unset=True)
    if ("company" in data or "role" in data) and app.internship_id is not None:
        # Linked postings keep the posting's company/role; silently ignore edits only if unchanged.
        if data.get("company", app.company) != app.company or data.get("role", app.role) != app.role:
            raise ApplicationError("Company and role come from the linked internship and cannot be edited")
    for key in ("company", "role"):
        if key in data and not data[key]:
            raise ApplicationError(f"{key.capitalize()} cannot be empty")
    if "resume_id" in data:
        _owned_resume(db, user_id, data["resume_id"])
    if "notes" in data:
        data["notes"] = (data["notes"] or "").strip() or None
    for key, value in data.items():
        setattr(app, key, value)
    app.updated_at = utcnow()
    db.commit()
    return app


def change_status(db: Session, user_id: uuid.UUID, application_id: uuid.UUID, status: str, note: str | None = None) -> Application:
    if status not in APPLICATION_STATUSES:
        raise ApplicationError("Unknown status")
    app = get(db, user_id, application_id)
    if app.status == status:
        raise ApplicationError(f"The application is already '{STATUS_LABELS[status]}'")
    now = utcnow()
    app.events.append(
        ApplicationEvent(user_id=user_id, from_status=app.status, to_status=status,
                         note=(note or "").strip()[:500] or None, created_at=now)
    )
    if app.applied_on is None and status not in ("saved", "withdrawn"):
        app.applied_on = now.date()
    app.status = status
    app.updated_at = now
    db.commit()
    return app


def delete(db: Session, user_id: uuid.UUID, application_id: uuid.UUID) -> None:
    app = get(db, user_id, application_id)
    db.delete(app)
    db.commit()


def describe(db: Session, apps: list[Application]) -> dict[uuid.UUID, tuple[str | None, str | None, str | None]]:
    """(internship source, resume name, posting stipend) per application, in two batched queries."""
    i_ids = {a.internship_id for a in apps if a.internship_id}
    r_ids = {a.resume_id for a in apps if a.resume_id}
    postings = {k: (src, stip) for k, src, stip in db.execute(select(Internship.id, Internship.source, Internship.stipend).where(Internship.id.in_(i_ids)))} if i_ids else {}
    names = {k: (lbl or fn) for k, fn, lbl in db.execute(select(Resume.id, Resume.original_filename, Resume.label).where(Resume.id.in_(r_ids)))} if r_ids else {}
    return {a.id: ((postings.get(a.internship_id) or (None, None))[0], names.get(a.resume_id), (postings.get(a.internship_id) or (None, None))[1]) for a in apps}
