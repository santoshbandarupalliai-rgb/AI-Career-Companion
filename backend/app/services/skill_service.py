"""Student skills: extracted vs verified vs rejected, kept strictly separate."""

import re
import uuid

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Skill, StudentSkill
from app.services import skills_catalog


class SkillError(ValueError):
    pass


def get_or_create_skill(db: Session, raw_name: str) -> Skill | None:
    canon = skills_catalog.canonicalize(raw_name)
    if canon is None:
        return None
    key, name, category = canon
    skill = db.scalar(select(Skill).where(Skill.canonical == key))
    if skill:
        return skill
    skill = Skill(canonical=key, name=name, category=category)
    try:
        with db.begin_nested():  # savepoint: a concurrent insert must not break the outer transaction
            db.add(skill)
    except IntegrityError:
        skill = db.scalar(select(Skill).where(Skill.canonical == key))
    return skill


def _evidence(raw_text: str, skill_name: str) -> str | None:
    m = re.search(re.escape(skill_name), raw_text, re.I)
    if not m:
        return None
    start, end = max(0, m.start() - 60), min(len(raw_text), m.end() + 60)
    return re.sub(r"\s+", " ", raw_text[start:end]).strip()[:300]


def sync_from_resume(db: Session, user_id: uuid.UUID, resume_id: uuid.UUID, names: list[str], raw_text: str) -> None:
    """Record resume skills as 'extracted'. Never overrides a student's verify/reject decision.

    Batched (a fixed handful of queries regardless of skill count) so it stays fast
    and less exposed to network hiccups. Does not commit. On a concurrent insert of
    the same new skill an IntegrityError is raised; the caller rolls back and retries.
    """
    wanted: dict[str, tuple[str, str, str | None]] = {}  # canonical -> (raw mention, display, category)
    for raw in names:
        canon = skills_catalog.canonicalize(raw)
        if canon and canon[0] not in wanted:
            wanted[canon[0]] = (raw, canon[1], canon[2])
    if not wanted:
        return

    skills = {s.canonical: s for s in db.scalars(select(Skill).where(Skill.canonical.in_(list(wanted))))}
    for key, (_, display, category) in wanted.items():
        if key not in skills:
            skills[key] = Skill(canonical=key, name=display, category=category)
            db.add(skills[key])
    db.flush()

    existing = {
        r.skill_id: r
        for r in db.scalars(
            select(StudentSkill).where(
                StudentSkill.user_id == user_id, StudentSkill.skill_id.in_([s.id for s in skills.values()])
            )
        )
    }
    for key, (raw, _, _) in wanted.items():
        skill = skills[key]
        row = existing.get(skill.id)
        evidence = _evidence(raw_text, raw)
        if row is None:
            db.add(
                StudentSkill(
                    user_id=user_id,
                    skill_id=skill.id,
                    status="extracted",
                    source="resume",
                    resume_id=resume_id,
                    evidence=evidence,
                )
            )
        elif row.status == "extracted":
            row.resume_id = resume_id
            row.evidence = evidence or row.evidence


def remove_unverified_from_resume(db: Session, user_id: uuid.UUID, resume_id: uuid.UUID) -> None:
    db.execute(
        delete(StudentSkill).where(
            StudentSkill.user_id == user_id,
            StudentSkill.resume_id == resume_id,
            StudentSkill.status == "extracted",
        )
    )


def list_skills(db: Session, user_id: uuid.UUID) -> dict[str, list[StudentSkill]]:
    rows = db.scalars(select(StudentSkill).where(StudentSkill.user_id == user_id)).all()
    groups: dict[str, list[StudentSkill]] = {"verified": [], "extracted": [], "rejected": []}
    for r in sorted(rows, key=lambda r: r.skill.name.lower()):
        groups[r.status].append(r)
    return groups


def _owned(db: Session, user_id: uuid.UUID, student_skill_id: uuid.UUID) -> StudentSkill:
    row = db.scalar(select(StudentSkill).where(StudentSkill.id == student_skill_id, StudentSkill.user_id == user_id))
    if row is None:
        raise SkillError("Skill not found")
    return row


def set_status(db: Session, user_id: uuid.UUID, student_skill_id: uuid.UUID, status: str) -> StudentSkill:
    row = _owned(db, user_id, student_skill_id)
    if status == "extracted" and row.source == "manual":
        raise SkillError("A skill you added yourself cannot be moved back to 'needs review'.")
    row.status = status
    db.commit()
    return row


def verify_many(db: Session, user_id: uuid.UUID, ids: list[uuid.UUID]) -> int:
    rows = db.scalars(
        select(StudentSkill).where(
            StudentSkill.user_id == user_id, StudentSkill.id.in_(ids), StudentSkill.status == "extracted"
        )
    ).all()
    for r in rows:
        r.status = "verified"
    db.commit()
    return len(rows)


def add_manual(db: Session, user_id: uuid.UUID, name: str) -> StudentSkill:
    skill = get_or_create_skill(db, name)
    if skill is None:
        raise SkillError("Enter a skill name")
    row = db.scalar(select(StudentSkill).where(StudentSkill.user_id == user_id, StudentSkill.skill_id == skill.id))
    if row is None:
        row = StudentSkill(user_id=user_id, skill_id=skill.id, status="verified", source="manual")
        db.add(row)
    else:
        row.status = "verified"  # adding a skill by hand is an explicit confirmation
    db.commit()
    db.refresh(row)
    return row


def delete_manual(db: Session, user_id: uuid.UUID, student_skill_id: uuid.UUID) -> None:
    row = _owned(db, user_id, student_skill_id)
    if row.source != "manual":
        raise SkillError("Resume skills can be rejected, not deleted.")
    db.delete(row)
    db.commit()


def verified_skill_names(db: Session, user_id: uuid.UUID) -> list[str]:
    return [r.skill.name for r in list_skills(db, user_id)["verified"]]
