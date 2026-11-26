"""Loads data for the pure engine (match_engine) and orchestrates matching and skill gap.

No LLM here: scores and gaps are deterministic. The optional explanation/plan live in plan_service.
Similarity is computed in Python over the visible internships' chunk vectors; that is fine at
knowledge-base scale (tens to low hundreds of postings) and works the same on SQLite and Postgres.
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Internship, RagChunk, RagDocument, Resume, StudentProfile
from app.rag import embeddings
from app.rag.embeddings import EmbeddingError
from app.rag.retriever import _cosine
from app.schemas.matching import GapReport, GapTarget, MatchList, MatchOut, MatchSummary
from app.services import internship_service, match_engine, skill_service
from app.services.match_engine import PostingContext, ProfileContext

log = logging.getLogger(__name__)

CORPUS = "internship"
ROLE_TOP_K = 5
ROLE_MIN_SIMILARITY = 0.55  # same calibration as the Product Assistant's retrieval threshold


# ---------- profile ----------

def _profile_text(profile: StudentProfile | None, verified_names: list[str]) -> str | None:
    """Text describing the student, from VERIFIED data only. None when there is too little to compare."""
    parts: list[str] = []
    if profile and profile.target_role:
        parts.append(f"Target role: {profile.target_role}")
    if profile and (profile.degree or profile.branch):
        parts.append("Education: " + ", ".join(x for x in (profile.degree, profile.branch) if x))
    if verified_names:
        parts.append("Skills: " + ", ".join(verified_names))
    if profile and profile.bio:
        parts.append(profile.bio[:600])
    has_substance = bool(verified_names) or bool(profile and profile.target_role)
    return "\n".join(parts) if parts and has_substance else None


def build_profile(db: Session, user_id: uuid.UUID, *, with_vector: bool = True) -> ProfileContext:
    groups = skill_service.list_skills(db, user_id)
    verified = {r.skill.canonical: r.skill.name for r in groups["verified"]}
    unverified = {r.skill.canonical: r.skill.name for r in groups["extracted"]}
    profile = db.scalar(select(StudentProfile).where(StudentProfile.user_id == user_id))

    resume = db.scalar(select(Resume).where(Resume.user_id == user_id, Resume.is_active.is_(True)))
    projects = experience = 0
    if resume is not None and resume.extraction is not None:
        data = resume.extraction.data or {}
        projects = len(data.get("projects") or [])
        experience = len(data.get("experience") or [])

    ctx = ProfileContext(
        verified=verified, unverified=unverified,
        degree=profile.degree if profile else None, branch=profile.branch if profile else None,
        cgpa=profile.cgpa if profile else None, graduation_year=profile.graduation_year if profile else None,
        has_resume=resume is not None and resume.extraction is not None,
        project_count=projects, experience_count=experience,
    )
    text = _profile_text(profile, sorted(verified.values(), key=str.lower))
    db.rollback()  # end the read transaction before the (slower) embedding call
    if with_vector and text:
        try:
            ctx.profile_vector = embeddings.embed_documents([text])[0]
        except EmbeddingError:
            log.warning("profile embedding unavailable; semantic factor will be skipped")
    return ctx


# ---------- postings ----------

def _similarities(db: Session, internship_ids: list[uuid.UUID], vector: list[float] | None) -> dict[str, float]:
    """Best chunk cosine per internship (keyed by str(id))."""
    if vector is None or not internship_ids:
        return {}
    rows = db.execute(
        select(RagDocument.source_key, RagChunk.embedding)
        .join(RagChunk, RagChunk.document_id == RagDocument.id)
        .where(RagDocument.corpus == CORPUS, RagDocument.source_key.in_([str(i) for i in internship_ids]))
    )
    best: dict[str, float] = {}
    for key, emb in rows:
        s = _cosine(vector, list(emb))
        if s > best.get(key, -1.0):
            best[key] = s
    return best


def _posting(item: Internship, similarity: float | None) -> PostingContext:
    req = {s.skill.canonical: s.skill.name for s in item.skills if s.importance == "required"}
    pref = {s.skill.canonical: s.skill.name for s in item.skills if s.importance == "preferred"}
    return PostingContext(
        title=item.title, required=req, preferred=pref, education_req=item.education_req,
        experience_req=item.experience_req, eligibility_text=item.eligibility_text, similarity=similarity,
    )


# ---------- matching ----------

def match_one(db: Session, user_id: uuid.UUID, internship_id: uuid.UUID, profile: ProfileContext | None = None) -> MatchOut:
    item = internship_service.get_internship(db, user_id, internship_id)  # raises InternshipError if not visible
    profile = profile or build_profile(db, user_id)
    sims = _similarities(db, [item.id], profile.profile_vector)
    return match_engine.build_match(
        profile, _posting(item, sims.get(str(item.id))), internship_id=item.id, company=item.company, source=item.source
    )


def match_all(db: Session, user_id: uuid.UUID, *, limit: int = 50, min_score: float = 0.0) -> MatchList:
    profile = build_profile(db, user_id)
    items, _ = internship_service.list_internships(db, user_id, limit=500)
    sims = _similarities(db, [i.id for i in items], profile.profile_vector)
    summaries: list[MatchSummary] = []
    for it in items:
        m = match_engine.build_match(
            profile, _posting(it, sims.get(str(it.id))), internship_id=it.id, company=it.company, source=it.source
        )
        if m.overall < min_score:
            continue
        total_req = len(m.matched_required) + len(m.missing_required)
        summaries.append(
            MatchSummary(
                internship_id=it.id, title=it.title, company=it.company, location=it.location, work_mode=it.work_mode,
                stipend=it.stipend, duration=it.duration, source=it.source, overall=m.overall, required_matched=len(m.matched_required), required_total=total_req,
                missing_required=m.missing_required[:4],
            )
        )
    summaries.sort(key=lambda s: (-s.overall, s.title.lower()))
    notes: list[str] = []
    if not profile.verified:
        notes.append("You have no verified skills yet, so every score is 0. "
                     "Verify your skills on the Resume Parsing page and scores will be calculated.")
    return MatchList(items=summaries[:limit], verified_skill_count=len(profile.verified), notes=notes)


# ---------- skill gap ----------

class GapTargetError(ValueError):
    pass


def gap_report(
    db: Session, user_id: uuid.UUID, *, internship_id: uuid.UUID | None = None, role: str | None = None
) -> GapReport:
    if bool(internship_id) == bool(role):
        raise GapTargetError("Choose either an internship or a target role.")
    profile = build_profile(db, user_id, with_vector=False)
    if internship_id:
        item = internship_service.get_internship(db, user_id, internship_id)
        target = GapTarget(type="internship", label=f"{item.title} at {item.company}", postings_considered=[item.title])
        return match_engine.compute_gap(profile, [_posting(item, None)], target)

    role = role.strip()
    hits = internship_service.semantic_search(db, user_id, role, limit=ROLE_TOP_K)
    chosen = [i for i, score, _ in hits if score >= ROLE_MIN_SIMILARITY]
    target = GapTarget(type="role", label=role, postings_considered=[f"{i.title} at {i.company}" for i in chosen])
    return match_engine.compute_gap(profile, [_posting(i, None) for i in chosen], target)
