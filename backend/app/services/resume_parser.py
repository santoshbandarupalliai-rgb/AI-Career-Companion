"""Turn raw resume text into structured data.

Primary path: Gemini with a strict JSON schema and an "extract only, never infer" prompt.
Then a deterministic grounding check removes any skill or contact detail that does
not actually appear in the resume text. If the LLM is unavailable or fails, a
heuristic parser (regex + skill catalog) produces a partial result instead.
"""

import logging
import re

from pydantic import BaseModel, Field

from app.config import get_settings
from app.llm import LLMError, generate_structured
from app.services import skills_catalog

log = logging.getLogger(__name__)

MAX_LLM_CHARS = 30_000


# ---------- schema (shared by the LLM and the API) ----------

class PersonalInfo(BaseModel):
    name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    linkedin: str = ""
    github: str = ""
    portfolio: str = ""


class SkillGroups(BaseModel):
    technical: list[str] = Field(default_factory=list, description="Programming languages, frameworks, libraries, databases, cloud, concepts")
    tools: list[str] = Field(default_factory=list, description="Developer tools and platforms, e.g. Git, Docker, VS Code")
    soft: list[str] = Field(default_factory=list, description="Soft skills explicitly listed")


class Education(BaseModel):
    institution: str = ""
    degree: str = ""
    field: str = ""
    start: str = ""
    end: str = ""
    score: str = Field(default="", description="CGPA / percentage exactly as written")


class Experience(BaseModel):
    title: str = ""
    organization: str = ""
    start: str = ""
    end: str = ""
    location: str = ""
    bullets: list[str] = Field(default_factory=list)


class Project(BaseModel):
    name: str = ""
    technologies: list[str] = Field(default_factory=list)
    description: str = ""
    link: str = ""


class Certification(BaseModel):
    name: str = ""
    issuer: str = ""
    year: str = ""


class ResumeData(BaseModel):
    personal: PersonalInfo = Field(default_factory=PersonalInfo)
    summary: str = ""
    skills: SkillGroups = Field(default_factory=SkillGroups)
    education: list[Education] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)


class ParseResult(BaseModel):
    data: ResumeData
    method: str  # llm | heuristic
    model: str | None = None
    status: str  # complete | partial
    warnings: list[str] = Field(default_factory=list)


SYSTEM_PROMPT = """You extract structured data from a student's resume.
Rules:
- Copy information ONLY if it is explicitly written in the resume text. Never infer, guess, or add anything.
- If a field is not present, leave it as an empty string or empty list.
- Skills: list each skill once, using the wording in the resume. Include skills from a skills section
  AND technologies explicitly named in projects or experience. Do not add related or implied skills.
- Keep dates, CGPA and percentages exactly as written.
- Experience = jobs and internships only. Academic or personal projects go in projects.
- Do not rewrite or improve bullet points; copy them (you may trim whitespace)."""


# ---------- grounding (deterministic anti-hallucination check) ----------

def _squash(text: str) -> str:
    return re.sub(r"[^a-z0-9+#]", "", text.lower())


def _appears_in(value: str, haystack_squashed: str) -> bool:
    v = _squash(value)
    return bool(v) and v in haystack_squashed


def _skill_grounded(skill: str, text_lower: str, text_squashed: str) -> bool:
    """A skill is grounded if it, or one of its known aliases, appears in the resume text."""
    if _appears_in(skill, text_squashed) and len(_squash(skill)) >= 3:
        return True
    canon = skills_catalog.canonicalize(skill)
    if not canon:
        return False
    key = canon[0]
    candidates = {skill.lower(), key, canon[1].lower()}
    candidates |= {a for a, k in skills_catalog._ALIAS_TO_KEY.items() if k == key}
    for c in candidates:
        if not c:
            continue
        pattern = r"(?<![a-z0-9+#.])" + re.escape(c) + r"(?![a-z0-9+#])"
        if re.search(pattern, text_lower):
            return True
    return False


def ground(data: ResumeData, raw_text: str) -> list[str]:
    """Remove ungrounded skills and contact details in place. Returns warnings."""
    warnings: list[str] = []
    text_lower = re.sub(r"\s+", " ", raw_text.lower())
    text_sq = _squash(raw_text)

    for group in ("technical", "tools", "soft"):
        kept, seen = [], set()
        for s in getattr(data.skills, group):
            s = s.strip()
            canon = skills_catalog.canonicalize(s)
            if not canon or canon[0] in seen:
                continue
            if _skill_grounded(s, text_lower, text_sq):
                kept.append(s)
                seen.add(canon[0])
            else:
                warnings.append(f"Removed skill '{s}': not found in the resume text.")
        setattr(data.skills, group, kept)

    for project in data.projects:
        kept = []
        for t in project.technologies:
            if _skill_grounded(t.strip(), text_lower, text_sq):
                kept.append(t.strip())
            else:
                warnings.append(f"Removed technology '{t}' from project '{project.name}': not in the resume text.")
        project.technologies = kept

    p = data.personal
    for field in ("email", "phone", "linkedin", "github", "portfolio"):
        value = getattr(p, field).strip()
        if not value:
            continue
        check = value
        if field in ("linkedin", "github", "portfolio"):
            check = re.sub(r"^https?://(www\.)?", "", value)
        if not _appears_in(check, text_sq):
            warnings.append(f"Removed {field}: not found in the resume text.")
            setattr(p, field, "")
    return warnings


# ---------- heuristic fallback ----------

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?:\+?\d{1,3}[\s-]?)?(?:\(?\d{3,5}\)?[\s-]?)?\d{3,5}[\s-]?\d{4,5}")
_LINKEDIN = re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/in/[\w-]+/?", re.I)
_GITHUB = re.compile(r"(?:https?://)?(?:www\.)?github\.com/[\w-]+/?", re.I)


def heuristic_parse(raw_text: str) -> ResumeData:
    data = ResumeData()
    if m := _EMAIL.search(raw_text):
        data.personal.email = m.group(0)
    for m in _PHONE.finditer(raw_text):
        digits = re.sub(r"\D", "", m.group(0))
        if 10 <= len(digits) <= 13:
            data.personal.phone = m.group(0).strip()
            break
    if m := _LINKEDIN.search(raw_text):
        data.personal.linkedin = m.group(0)
    if m := _GITHUB.search(raw_text):
        data.personal.github = m.group(0)
    # Name: first short line that is not contact info.
    for line in raw_text.splitlines()[:5]:
        line = line.strip()
        if line and len(line) <= 40 and not any(ch.isdigit() for ch in line) and "@" not in line:
            data.personal.name = line
            break
    for key in skills_catalog.find_known_skills(raw_text):
        cat = skills_catalog.category_of(key)
        target = data.skills.soft if cat == "soft" else data.skills.tools if cat in ("tool", "devops") else data.skills.technical
        target.append(skills_catalog.display_name(key))
    return data


# ---------- entry point ----------

def parse_resume(raw_text: str) -> ParseResult:
    text = raw_text[:MAX_LLM_CHARS]
    warnings: list[str] = []
    if len(raw_text) > MAX_LLM_CHARS:
        warnings.append("Resume text was very long; only the first part was analysed.")
    try:
        data = generate_structured(
            f"Resume text:\n<<<\n{text}\n>>>", ResumeData, system=SYSTEM_PROMPT, temperature=0.0
        )
        warnings += ground(data, raw_text)
        return ParseResult(
            data=data, method="llm", model=get_settings().gemini_model, status="complete", warnings=warnings
        )
    except LLMError as exc:
        log.warning("LLM extraction failed, using heuristic parser: %s", exc)
        data = heuristic_parse(raw_text)
        warnings += ground(data, raw_text)
        warnings.insert(
            0,
            "AI extraction was unavailable, so only contact details and recognised skills were extracted. "
            "Use 'Re-run extraction' later for full results.",
        )
        return ParseResult(data=data, method="heuristic", status="partial", warnings=warnings)


def all_skills(data: ResumeData) -> list[str]:
    """Every skill mention: skill sections plus project technologies, de-duplicated by canonical key."""
    out, seen = [], set()
    for s in data.skills.technical + data.skills.tools + data.skills.soft + [t for p in data.projects for t in p.technologies]:
        canon = skills_catalog.canonicalize(s)
        if canon and canon[0] not in seen:
            seen.add(canon[0])
            out.append(s)
    return out
