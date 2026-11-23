"""Tailored resume and cover letter generation with a fact guard, plus approval-gated saving.

Safety design (see fact_guard.py):
- Employers, titles, dates, organisations and project names are NEVER produced by the model. The model refers to
  the student's real resume entries by index and only supplies rewritten bullets; headers and entry details are
  copied from the source.
- A resume's skills list can only contain VERIFIED skills.
- Everything the model writes is then checked for invented numbers, skills and names; problems are returned as flags.
- Nothing is saved until the student approves. Saving re-runs the checks on what the student submitted
  (they may have edited it) and requires explicit acknowledgement if anything is still flagged.
"""

import io
import logging
import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm import generate_structured
from app.models import GeneratedDocument, Internship, StudentProfile, User  # noqa: F401
from app.schemas.tailoring import (
    CoverLetterContent,
    CoverLetterLLM,
    Draft,
    EducationLine,
    Flag,
    ResumeContent,
    ResumeDraftLLM,
    ResumeEntry,
    ResumeHeader,
    SaveRequest,
)
from app.services import fact_guard, internship_service, resume_service, skill_service
from app.services.fact_guard import Source

log = logging.getLogger(__name__)

MAX_BULLETS = 4
MAX_ENTRIES = 6


class TailoringError(ValueError):
    pass


class NotFound(LookupError):
    pass


class NeedsAcknowledgement(Exception):
    def __init__(self, flags: list[Flag]):
        super().__init__("Some items are flagged. Review them and confirm to save.")
        self.flags = flags


@dataclass
class ProfileSnap:
    """Plain copy of the profile fields we need, so nothing touches the DB after the session is released."""

    target_role: str | None = None
    phone: str | None = None
    location: str | None = None
    links: list[str] = field(default_factory=list)


@dataclass
class SourceData:
    user_name: str
    email: str
    profile: ProfileSnap | None
    verified: dict[str, str]
    rejected: set[str]
    experience: list[dict] = field(default_factory=list)
    projects: list[dict] = field(default_factory=list)
    education: list[str] = field(default_factory=list)
    certifications: list[str] = field(default_factory=list)
    has_resume: bool = False

    def entry_text(self, kind: str, idx: int) -> str:
        e = (self.experience if kind == "experience" else self.projects)[idx]
        parts = [e.get("title") or e.get("name") or "", e.get("organization") or "", e.get("description") or "",
                 " ".join(e.get("bullets") or []), " ".join(e.get("technologies") or [])]
        return " ".join(p for p in parts if p)


# ---------- building the source ----------

def _flatten(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [t for v in value.values() for t in _flatten(v)]
    if isinstance(value, list):
        return [t for v in value for t in _flatten(v)]
    return []


def load_source(db: Session, user: User) -> tuple[Source, SourceData]:
    groups = skill_service.list_skills(db, user.id)
    verified = {r.skill.canonical: r.skill.name for r in groups["verified"]}
    rejected = {r.skill.canonical for r in groups["rejected"]}
    profile = db.scalar(select(StudentProfile).where(StudentProfile.user_id == user.id))
    resume = resume_service.active_resume(db, user.id)
    data = resume.extraction.data if resume is not None and resume.extraction is not None else {}

    snap = ProfileSnap(
        target_role=profile.target_role, phone=profile.phone, location=profile.location,
        links=[u for u in (profile.linkedin_url, profile.github_url, profile.portfolio_url) if u],
    ) if profile else None
    sd = SourceData(user_name=user.full_name, email=user.email, profile=snap, verified=verified, rejected=rejected,
                    has_resume=bool(data))
    sd.experience = [e for e in (data.get("experience") or []) if isinstance(e, dict)]
    sd.projects = [p for p in (data.get("projects") or []) if isinstance(p, dict)]
    sd.certifications = [c.get("name", "") for c in (data.get("certifications") or []) if isinstance(c, dict) and c.get("name")]

    if profile and (profile.college or profile.degree):
        bits = [", ".join(x for x in (profile.degree, profile.branch) if x), profile.college,
                str(profile.graduation_year) if profile.graduation_year else "", f"CGPA {profile.cgpa:g}" if profile.cgpa is not None else ""]
        sd.education.append(" · ".join(b for b in bits if b))
    else:
        for e in data.get("education") or []:
            if isinstance(e, dict):
                bits = [", ".join(x for x in (e.get("degree"), e.get("field")) if x), e.get("institution"),
                        " – ".join(x for x in (e.get("start"), e.get("end")) if x), e.get("score")]
                line = " · ".join(b for b in bits if b)
                if line:
                    sd.education.append(line)

    # Corpus = everything the student has said about themselves, EXCLUDING the resume's skills section
    # (unverified skills must not count as evidence).
    texts = [user.full_name]
    if profile:
        texts += [str(v) for v in (profile.college, profile.degree, profile.branch, profile.cgpa, profile.graduation_year,
                                   profile.target_role, profile.location, profile.bio) if v not in (None, "")]
    texts += list(verified.values()) + sd.education
    for key in ("summary", "experience", "projects", "education", "certifications", "achievements"):
        texts += _flatten(data.get(key))
    return Source(corpus="\n".join(texts), verified=verified, rejected=rejected), sd


def _posting_text(item: Internship) -> str:
    skills = ", ".join(s.skill.name for s in item.skills)
    return "\n".join(x for x in (item.title, item.company, item.location, item.description, item.eligibility_text,
                                 item.education_req, item.experience_req, skills) if x)


def _header(sd: SourceData) -> ResumeHeader:
    p = sd.profile
    return ResumeHeader(name=sd.user_name, email=sd.email, phone=(p.phone if p and p.phone else ""),
                        location=(p.location if p and p.location else ""), links=list(p.links) if p else [])


# ---------- prompts ----------

RESUME_SYSTEM = """You tailor a student's resume content for one internship posting.
Hard rules:
- Use ONLY the facts in the STUDENT SOURCE. Never add or change facts, numbers, dates, employers, tools or achievements.
- Experience and projects: refer to source entries by their [index]. For each entry you choose to include, return rewritten bullets
  (at most 4, each one sentence, starting with a strong verb) that rephrase ONLY what that entry says. You may reorder and tighten,
  and mirror the posting's wording ONLY for things the entry already says. Omit entries that are irrelevant to the posting.
- skills: choose ONLY from the VERIFIED SKILLS list, most relevant to the posting first.
- summary: 2-3 sentences about the student using only the source facts. Do not claim experience the source does not show.
- Do not invent metrics. Do not add links. Keep a plain professional tone."""

LETTER_SYSTEM = """You write a cover letter body for a student applying to one internship.
Hard rules:
- Use ONLY the facts in the STUDENT SOURCE and the POSTING. Never invent experience, skills, numbers, achievements or company facts.
- Only claim skills from the VERIFIED SKILLS list. You may say the student is keen to learn a posting skill they do not have,
  but must not say they know it.
- Write 3 short paragraphs (about 170-230 words in total): why this role, the evidence from the student's real projects/experience,
  and a brief close. First person, plain and sincere.
- Do not include a greeting, sign-off, the student's name, placeholders, or links."""


def _source_prompt(sd: SourceData, item: Internship, *, for_letter: bool = False) -> str:
    p = sd.profile
    lines = [f"POSTING: {item.title} at {item.company}"]
    req = [s.skill.name for s in item.skills if s.importance == "required"]
    pref = [s.skill.name for s in item.skills if s.importance == "preferred"]
    if req:
        lines.append("Required skills: " + ", ".join(req))
    if pref:
        lines.append("Preferred skills: " + ", ".join(pref))
    lines.append("Description:\n<<<\n" + item.description[:3000] + "\n>>>")
    lines.append("\nSTUDENT SOURCE")
    if p and p.target_role:
        lines.append(f"Target role: {p.target_role}")
    if sd.education:
        lines.append("Education: " + "; ".join(sd.education))
    lines.append("VERIFIED SKILLS: " + (", ".join(sorted(sd.verified.values(), key=str.lower)) or "none"))
    if sd.experience:
        lines.append("Experience entries:")
        for i, e in enumerate(sd.experience):
            lines.append(f"[{i}] {e.get('title','')} at {e.get('organization','')} ({e.get('start','')} - {e.get('end','')})")
            lines += [f"    - {b}" for b in (e.get("bullets") or [])]
    if sd.projects:
        lines.append("Projects:")
        for i, pr in enumerate(sd.projects):
            lines.append(f"[{i}] {pr.get('name','')}; technologies: {', '.join(pr.get('technologies') or [])}")
            if pr.get("description"):
                lines.append(f"    {pr['description']}")
    if sd.certifications:
        lines.append("Certifications: " + "; ".join(sd.certifications))
    return "\n".join(lines)


# ---------- generation ----------

def _require_material(sd: SourceData) -> None:
    if not sd.verified and not sd.experience and not sd.projects:
        raise TailoringError(
            "Add some material first: verify your skills and upload a resume. Nothing is invented on your behalf."
        )


def _entry(kind: str, idx: int, sd: SourceData, bullets: list[str]) -> ResumeEntry:
    e = (sd.experience if kind == "experience" else sd.projects)[idx]
    if kind == "experience":
        return ResumeEntry(source_index=idx, title=e.get("title", ""), organization=e.get("organization", ""),
                           start=e.get("start", ""), end=e.get("end", ""), bullets=bullets)
    return ResumeEntry(source_index=idx, title=e.get("name", ""), technologies=[t for t in (e.get("technologies") or []) if t],
                       bullets=bullets)


def _source_bullets(kind: str, idx: int, sd: SourceData) -> list[str]:
    e = (sd.experience if kind == "experience" else sd.projects)[idx]
    if kind == "experience":
        return [b for b in (e.get("bullets") or []) if b][:MAX_BULLETS]
    return [e["description"]] if e.get("description") else []


def _clean_bullets(bullets: list[str]) -> list[str]:
    out, seen = [], set()
    for b in bullets:
        b = re.sub(r"\s+", " ", b).strip().lstrip("-•* ").strip()
        if b and b.lower() not in seen:
            seen.add(b.lower())
            out.append(b[:400])
    return out[:MAX_BULLETS]


def _assemble_entries(kind: str, llm_entries, sd: SourceData, src: Source, notes: list[str]):
    entries: list[ResumeEntry] = []
    flags: list[Flag] = []
    seen: set[int] = set()
    pool = sd.experience if kind == "experience" else sd.projects
    for item in llm_entries:
        idx = item.source_index
        if not (0 <= idx < len(pool)) or idx in seen:
            notes.append(f"Ignored a {kind} entry the AI referred to that does not exist in your resume.")
            continue
        seen.add(idx)
        bullets = _clean_bullets(item.bullets) or _source_bullets(kind, idx, sd)
        pos = len(entries)
        ref = sd.entry_text(kind, idx)
        for bi, b in enumerate(bullets):
            flags += fact_guard.check_text(b, src, f"{kind}.{pos}.bullet.{bi}", ref_text=ref)
        entries.append(_entry(kind, idx, sd, bullets))
        if len(entries) >= MAX_ENTRIES:
            break
    return entries, flags


def generate(db: Session, user: User, internship_id: uuid.UUID, kind: str) -> Draft:
    item = internship_service.get_internship(db, user.id, internship_id)  # raises if not visible
    src, sd = load_source(db, user)
    _require_material(sd)
    prompt = _source_prompt(sd, item)
    posting = _posting_text(item)
    title = item.title
    company = item.company
    db.rollback()  # no transaction open during the LLM call

    notes: list[str] = []
    if kind == "resume":
        out = generate_structured(prompt, ResumeDraftLLM, system=RESUME_SYSTEM, temperature=0.3)
        flags: list[Flag] = []
        skills, f = fact_guard.filter_skills(out.skills, src)
        flags += f
        exp, f = _assemble_entries("experience", out.experience, sd, src, notes)
        flags += f
        proj, f = _assemble_entries("projects", out.projects, sd, src, notes)
        flags += f
        summary = re.sub(r"\s+", " ", out.summary).strip()[:1500]
        flags = fact_guard.check_text(summary, src, "summary") + flags
        content = ResumeContent(header=_header(sd), summary=summary, skills=skills, experience=exp, projects=proj,
                                education=[EducationLine(text=t) for t in sd.education], certifications=sd.certifications)
        if not (exp or proj) and (sd.experience or sd.projects):
            notes.append("The AI did not select any experience or projects. You can regenerate or add them back by editing.")
        if not sd.has_resume:
            notes.append("You have no parsed resume, so this draft has no experience or projects. Upload a resume on the Profile page.")
        facts = _facts_used(sd, content)
        return Draft(kind="resume", internship_id=internship_id, title=f"Resume for {title} at {company}",
                     content=content.model_dump(), facts_used=facts, flags=flags, notes=notes)

    # cover letter
    out = generate_structured(prompt, CoverLetterLLM, system=LETTER_SYSTEM, temperature=0.4)
    paras = [re.sub(r"\s+", " ", p).strip() for p in out.paragraphs if p and p.strip()][:5]
    if not paras:
        raise TailoringError("The AI did not return a usable letter. Please try again.")
    letter_src = Source(corpus=src.corpus, verified=src.verified, rejected=src.rejected, extra_text=posting)
    flags = fact_guard.check_letter(paras, letter_src)
    content = CoverLetterContent(paragraphs=paras, name=sd.user_name)
    facts = ["Posting: " + f"{title} at {company}"] + _facts_used(sd, None)
    return Draft(kind="cover_letter", internship_id=internship_id, title=f"Cover letter for {title} at {company}",
                 content=content.model_dump(), facts_used=facts, flags=flags, notes=notes)


def _facts_used(sd: SourceData, content: ResumeContent | None) -> list[str]:
    facts: list[str] = []
    if content is not None:
        facts += [f"Experience: {e.title} at {e.organization}".strip() for e in content.experience]
        facts += [f"Project: {e.title}" for e in content.projects]
        if content.skills:
            facts.append("Verified skills: " + ", ".join(content.skills))
    else:
        facts.append("Verified skills: " + (", ".join(sorted(sd.verified.values(), key=str.lower)) or "none"))
        facts += [f"Experience: {e.get('title','')} at {e.get('organization','')}".strip() for e in sd.experience]
        facts += [f"Project: {p.get('name','')}" for p in sd.projects]
    if sd.education:
        facts.append("Education: " + sd.education[0])
    return facts


# ---------- saving (approval) ----------

def _revalidate_resume(raw: dict, sd: SourceData, src: Source) -> tuple[ResumeContent, list[Flag]]:
    try:
        c = ResumeContent.model_validate(raw)
    except Exception as exc:
        raise TailoringError("The resume content is not valid.") from exc
    flags: list[Flag] = []
    skills, f = fact_guard.filter_skills(c.skills, src)
    flags += f
    c.skills = skills
    rebuilt: dict[str, list[ResumeEntry]] = {"experience": [], "projects": []}
    for kind, entries in (("experience", c.experience), ("projects", c.projects)):
        pool = sd.experience if kind == "experience" else sd.projects
        for pos, e in enumerate(entries):
            if not (0 <= e.source_index < len(pool)):
                raise TailoringError(f"A {kind} entry does not match anything in your resume.")
            bullets = _clean_bullets(e.bullets)
            ref = sd.entry_text(kind, e.source_index)
            for bi, b in enumerate(bullets):
                flags += fact_guard.check_text(b, src, f"{kind}.{pos}.bullet.{bi}", ref_text=ref)
            rebuilt[kind].append(_entry(kind, e.source_index, sd, bullets))  # details always copied from the source
    c.experience, c.projects = rebuilt["experience"], rebuilt["projects"]
    c.summary = re.sub(r"\s+", " ", c.summary).strip()
    flags = fact_guard.check_text(c.summary, src, "summary") + flags
    c.header = _header(sd)
    c.education = [EducationLine(text=t) for t in sd.education]
    c.certifications = sd.certifications
    return c, flags


def save(db: Session, user: User, req: SaveRequest) -> GeneratedDocument:
    item = internship_service.get_internship(db, user.id, req.internship_id) if req.internship_id else None
    src, sd = load_source(db, user)
    posting = _posting_text(item) if item else ""
    uid, item_id = user.id, (item.id if item else None)
    label = f"{item.title} at {item.company}" if item else ""
    db.rollback()  # release the read transaction; only plain values are used below

    if req.kind == "resume":
        content, flags = _revalidate_resume(req.content, sd, src)
        facts = _facts_used(sd, content)
        default_title = f"Resume for {label}" if label else "Tailored resume"
    else:
        try:
            c = CoverLetterContent.model_validate(req.content)
        except Exception as exc:
            raise TailoringError("The cover letter content is not valid.") from exc
        if not c.paragraphs:
            raise TailoringError("The cover letter is empty.")
        if len(c.greeting) > 120 or len(c.closing) > 120:
            raise TailoringError("The greeting or closing is too long.")
        c.name = sd.user_name
        letter_src = Source(corpus=src.corpus, verified=src.verified, rejected=src.rejected, extra_text=posting)
        flags = fact_guard.check_letter(c.paragraphs, letter_src)
        content = c
        facts = ([f"Posting: {label}"] if label else []) + _facts_used(sd, None)
        default_title = f"Cover letter for {label}" if label else "Cover letter"

    warnings = [f for f in flags if f.severity == "warning"]
    if warnings and not req.acknowledge_flags:
        raise NeedsAcknowledgement(flags)

    doc = GeneratedDocument(
        user_id=uid, kind=req.kind, internship_id=item_id,
        title=(req.title or default_title)[:300], content=content.model_dump(), facts_used=facts,
        flagged=[f.model_dump() for f in flags],
    )
    db.add(doc)
    db.commit()
    return doc


def list_documents(db: Session, user_id: uuid.UUID) -> list[GeneratedDocument]:
    return list(db.scalars(select(GeneratedDocument).where(GeneratedDocument.user_id == user_id).order_by(GeneratedDocument.created_at.desc())))


def get_document(db: Session, user_id: uuid.UUID, doc_id: uuid.UUID) -> GeneratedDocument:
    doc = db.scalar(select(GeneratedDocument).where(GeneratedDocument.id == doc_id, GeneratedDocument.user_id == user_id))
    if doc is None:
        raise NotFound("Document not found")
    return doc


def delete_document(db: Session, user_id: uuid.UUID, doc_id: uuid.UUID) -> None:
    db.delete(get_document(db, user_id, doc_id))
    db.commit()


# ---------- DOCX export ----------

def to_docx(doc: GeneratedDocument) -> bytes:
    from docx import Document
    from docx.shared import Pt

    d = Document()
    d.styles["Normal"].font.name = "Calibri"
    d.styles["Normal"].font.size = Pt(10.5)
    c = doc.content
    if doc.kind == "cover_letter":
        d.add_paragraph(c.get("greeting", ""))
        for p in c.get("paragraphs", []):
            d.add_paragraph(p)
        d.add_paragraph(c.get("closing", ""))
        d.add_paragraph(c.get("name", ""))
    else:
        h = c.get("header", {})
        d.add_heading(h.get("name", ""), level=0)
        contact = " | ".join(x for x in [h.get("email"), h.get("phone"), h.get("location"), *h.get("links", [])] if x)
        if contact:
            d.add_paragraph(contact)
        if c.get("summary"):
            d.add_heading("Summary", level=1)
            d.add_paragraph(c["summary"])
        if c.get("skills"):
            d.add_heading("Skills", level=1)
            d.add_paragraph(", ".join(c["skills"]))
        if c.get("experience"):
            d.add_heading("Experience", level=1)
            for e in c["experience"]:
                head = f"{e.get('title','')}" + (f", {e['organization']}" if e.get("organization") else "")
                dates = " – ".join(x for x in (e.get("start"), e.get("end")) if x)
                d.add_paragraph(head + (f"  ({dates})" if dates else "")).runs[0].bold = True
                for b in e.get("bullets", []):
                    d.add_paragraph(b, style="List Bullet")
        if c.get("projects"):
            d.add_heading("Projects", level=1)
            for e in c["projects"]:
                tech = f"  [{', '.join(e['technologies'])}]" if e.get("technologies") else ""
                d.add_paragraph(e.get("title", "") + tech).runs[0].bold = True
                for b in e.get("bullets", []):
                    d.add_paragraph(b, style="List Bullet")
        if c.get("education"):
            d.add_heading("Education", level=1)
            for e in c["education"]:
                d.add_paragraph(e.get("text", ""))
        if c.get("certifications"):
            d.add_heading("Certifications", level=1)
            for t in c["certifications"]:
                d.add_paragraph(t, style="List Bullet")
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()
