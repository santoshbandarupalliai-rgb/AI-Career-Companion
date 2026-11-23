"""Internship knowledge base: create, list/filter, semantic search, seed.

Visibility: sample postings are visible to everyone; a user-added posting is visible
only to the user who added it.

Embedding happens BEFORE the DB transaction opens, and writes
are batched (gotcha 5).
"""

import logging
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Internship, InternshipSkill, Skill
from app.rag import retriever
from app.rag.embeddings import embed_query
from app.schemas.internship import InternshipCreate, SkillInput
from app.seed.sample_internships import SAMPLES
from app.services import skills_catalog

log = logging.getLogger(__name__)

CORPUS = "internship"


class InternshipError(ValueError):
    pass


# ---------- indexing ----------

def index_text(
    *, title: str, company: str, location: str | None, work_mode: str | None, description: str,
    eligibility_text: str | None, skills: list[tuple[str, str]],
) -> str:
    """The text that gets embedded. skills: (display name, importance)."""
    req = [n for n, i in skills if i == "required"]
    pref = [n for n, i in skills if i == "preferred"]
    parts = [f"{title} at {company}"]
    if location or work_mode:
        loc = [x for x in (location, work_mode) if x]
        if len(loc) == 2 and loc[0].lower() == loc[1].lower():
            loc = loc[:1]
        parts.append("Location: " + ", ".join(loc))
    if req:
        parts.append("Required skills: " + ", ".join(req))
    if pref:
        parts.append("Preferred skills: " + ", ".join(pref))
    parts.append(description)
    if eligibility_text:
        parts.append("Eligibility: " + eligibility_text)
    return "\n\n".join(parts)


def _normalise_skills(inputs: list[SkillInput]) -> list[tuple[str, str, str, str | None]]:
    """-> [(canonical, display, importance, category)] de-duplicated; 'required' wins over 'preferred'."""
    out: dict[str, tuple[str, str, str, str | None]] = {}
    for s in inputs:
        canon = skills_catalog.canonicalize(s.name)
        if canon is None:
            continue
        key, display, category = canon
        if key not in out or s.importance == "required":
            out[key] = (key, display, s.importance, category)
    return list(out.values())


def _ensure_skills(db: Session, wanted: list[tuple[str, str, str, str | None]]) -> dict[str, Skill]:
    keys = [w[0] for w in wanted]
    skills = {s.canonical: s for s in db.scalars(select(Skill).where(Skill.canonical.in_(keys)))} if keys else {}
    for key, display, _, category in wanted:
        if key not in skills:
            skills[key] = Skill(canonical=key, name=display, category=category)
            db.add(skills[key])
    db.flush()
    return skills


def _add_internship(db: Session, *, fields: dict, skills_in: list[SkillInput], prepared) -> Internship:
    text, chunks_and_vectors = prepared
    wanted = _normalise_skills(skills_in)
    skill_rows = _ensure_skills(db, wanted)
    item = Internship(**fields)
    for key, _, importance, _ in wanted:
        item.skills.append(InternshipSkill(skill_id=skill_rows[key].id, importance=importance, skill=skill_rows[key]))
    db.add(item)
    db.flush()
    retriever.upsert_document(
        db, corpus=CORPUS, source_key=str(item.id), title=f"{item.title} at {item.company}",
        text=text, meta={"source": item.source}, prepared=chunks_and_vectors,
    )
    return item


def _prepare(fields: dict, skills_in: list[SkillInput]):
    wanted = _normalise_skills(skills_in)
    text = index_text(
        title=fields["title"], company=fields["company"], location=fields.get("location"),
        work_mode=fields.get("work_mode"), description=fields["description"],
        eligibility_text=fields.get("eligibility_text"), skills=[(d, i) for _, d, i, _ in wanted],
    )
    return text, retriever.prepare_chunks(text)


def create_user_internship(db: Session, user_id: uuid.UUID, payload: InternshipCreate) -> Internship:
    fields = payload.model_dump(exclude={"skills"})
    fields.update(source="user", created_by=user_id)
    prepared = _prepare(fields, payload.skills)  # slow: before the transaction
    item = _add_internship(db, fields=fields, skills_in=payload.skills, prepared=prepared)
    db.commit()
    return item


def seed_samples(db: Session) -> int:
    """Insert any sample postings that are missing. Idempotent. Returns how many were added."""
    existing = set(db.scalars(select(Internship.seed_key).where(Internship.seed_key.is_not(None))))
    todo = [s for s in SAMPLES if s["seed_key"] not in existing]
    if not todo:
        return 0
    prepared = []
    for s in todo:  # embed everything first, in one go per posting, before touching the DB
        skills_in = [SkillInput(name=n, importance="required") for n in s["required"]] + [
            SkillInput(name=n, importance="preferred") for n in s["preferred"]
        ]
        fields = _sample_fields(s)
        prepared.append((fields, skills_in, _prepare(fields, skills_in)))
    for fields, skills_in, prep in prepared:
        _add_internship(db, fields=fields, skills_in=skills_in, prepared=prep)
    db.commit()
    return len(todo)


def _sample_fields(s: dict) -> dict:
    keys = ("title", "company", "location", "work_mode", "stipend", "duration", "education_req", "experience_req", "description")
    f = {k: s.get(k) for k in keys}
    f.update(source="sample", seed_key=s["seed_key"], created_by=None, apply_url=None, eligibility_text=None)
    return f


# ---------- reading ----------

def _visible(user_id: uuid.UUID):
    return or_(Internship.source == "sample", Internship.created_by == user_id)


def _filters(user_id, *, q, work_mode, location, skill, source):
    conds = [_visible(user_id), Internship.is_active.is_(True)]
    if q:
        like = f"%{q.lower()}%"
        conds.append(or_(func.lower(Internship.title).like(like), func.lower(Internship.company).like(like)))
    if work_mode:
        conds.append(Internship.work_mode == work_mode)
    if location:
        conds.append(func.lower(Internship.location).like(f"%{location.lower()}%"))
    if source:
        conds.append(Internship.source == source)
    if skill:
        canon = skills_catalog.canonicalize(skill)
        key = canon[0] if canon else skill.lower()
        conds.append(
            Internship.id.in_(
                select(InternshipSkill.internship_id).join(Skill, Skill.id == InternshipSkill.skill_id).where(Skill.canonical == key)
            )
        )
    return conds


def list_internships(
    db: Session, user_id: uuid.UUID, *, q=None, work_mode=None, location=None, skill=None, source=None,
    limit: int = 20, offset: int = 0,
) -> tuple[list[Internship], int]:
    conds = _filters(user_id, q=q, work_mode=work_mode, location=location, skill=skill, source=source)
    total = db.scalar(select(func.count()).select_from(Internship).where(*conds)) or 0
    items = db.scalars(
        select(Internship).where(*conds).order_by(Internship.created_at.desc(), Internship.title).limit(limit).offset(offset)
    ).all()
    return list(items), total


def get_internship(db: Session, user_id: uuid.UUID, internship_id: uuid.UUID) -> Internship:
    item = db.scalar(select(Internship).where(Internship.id == internship_id, _visible(user_id)))
    if item is None:
        raise InternshipError("Internship not found")
    return item


def delete_user_internship(db: Session, user_id: uuid.UUID, internship_id: uuid.UUID) -> None:
    item = get_internship(db, user_id, internship_id)
    if item.source != "user" or item.created_by != user_id:
        raise InternshipError("Sample postings cannot be deleted.")
    retriever.delete_document(db, CORPUS, str(item.id))
    db.delete(item)
    db.commit()


def semantic_search(
    db: Session, user_id: uuid.UUID, query: str, *, work_mode=None, location=None, skill=None, source=None, limit: int = 10,
) -> list[tuple[Internship, float, str]]:
    """Returns [(internship, similarity, best matching passage)], best first."""
    conds = _filters(user_id, q=None, work_mode=work_mode, location=location, skill=skill, source=source)
    items = {str(i.id): i for i in db.scalars(select(Internship).where(*conds))}
    if not items:
        return []
    vector = embed_query(query)
    hits = retriever.search(db, vector, corpus=CORPUS, limit=limit, allowed_source_keys=set(items))
    return [(items[h.source_key], h.score, h.content) for h in hits if h.source_key in items]
