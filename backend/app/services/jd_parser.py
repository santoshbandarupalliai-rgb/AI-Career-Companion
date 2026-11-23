"""Extract structured fields from a pasted job description.

Same safety model as resume_parser: Gemini extracts under an "only what is written"
prompt, then a deterministic grounding check drops any skill or detail that does not
appear in the pasted text. If the LLM is unavailable, a heuristic returns recognised
skills only and the user fills in the rest. The result is a *draft*; the user confirms it.
"""

import logging
import re

from pydantic import BaseModel, Field

from app.llm import LLMError, generate_structured
from app.services import skills_catalog
from app.services.resume_parser import _appears_in, _skill_grounded, _squash

log = logging.getLogger(__name__)

MAX_CHARS = 30_000
_WORK_MODES = {"remote", "onsite", "hybrid"}


class JDExtraction(BaseModel):
    title: str = ""
    company: str = ""
    location: str = ""
    work_mode: str = Field(default="", description="remote, onsite or hybrid; empty if not stated")
    stipend: str = Field(default="", description="exactly as written, e.g. '₹15,000/month'")
    duration: str = Field(default="", description="exactly as written, e.g. '3 months'")
    education_req: str = ""
    experience_req: str = ""
    eligibility_text: str = Field(default="", description="eligibility conditions copied from the text")
    apply_url: str = ""
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list, description="'nice to have' / 'preferred' / 'plus' skills")


SYSTEM_PROMPT = """You extract structured fields from an internship job description.
Rules:
- Copy information ONLY if it is explicitly written in the text. Never infer, guess, or add anything.
- If a field is not stated, leave it as an empty string or empty list.
- Skills: list each skill once, using the wording in the text. Put skills under "required" or "must have"
  in required_skills, and skills described as preferred, bonus, plus or nice-to-have in preferred_skills.
  If the text does not distinguish, treat them as required. Do not add related or implied skills.
- Keep stipend, duration and links exactly as written.
- work_mode must be one of: remote, onsite, hybrid (or empty)."""


def _text_contains(value: str, text_sq: str) -> bool:
    return _appears_in(value, text_sq)


def ground(ex: JDExtraction, text: str) -> list[str]:
    """Remove anything not found in the pasted text. Returns warnings."""
    warnings: list[str] = []
    text_lower = re.sub(r"\s+", " ", text.lower())
    text_sq = _squash(text)

    for field in ("company", "location", "stipend", "duration"):
        v = getattr(ex, field).strip()
        if v and not _text_contains(v, text_sq):
            warnings.append(f"Removed {field} '{v}': not found in the pasted text.")
            setattr(ex, field, "")
    if ex.apply_url.strip():
        check = re.sub(r"^https?://(www\.)?", "", ex.apply_url.strip())
        if not _text_contains(check, text_sq):
            warnings.append("Removed apply link: not found in the pasted text.")
            ex.apply_url = ""
    for field in ("education_req", "experience_req", "eligibility_text"):
        v = getattr(ex, field).strip()
        # Free-text requirements are paraphrased more often; require a loose word overlap instead of exact match.
        words = [w for w in re.findall(r"[a-z0-9+#]{4,}", v.lower())]
        if words and sum(1 for w in words if w in text_lower) / len(words) < 0.6:
            warnings.append(f"Removed {field.replace('_', ' ')}: it does not match the pasted text.")
            setattr(ex, field, "")

    mode = ex.work_mode.strip().lower().replace("-", "").replace(" ", "")
    mode = {"onsite": "onsite", "inoffice": "onsite", "wfh": "remote", "workfromhome": "remote"}.get(mode, mode)
    if mode not in _WORK_MODES:
        mode = ""
    elif not re.search(r"remote|work from home|wfh|on-?site|in-?office|hybrid", text_lower):
        mode = ""
    ex.work_mode = mode

    for group in ("required_skills", "preferred_skills"):
        kept, seen = [], set()
        for s in getattr(ex, group):
            s = s.strip()
            canon = skills_catalog.canonicalize(s)
            if not canon or canon[0] in seen:
                continue
            if _skill_grounded(s, text_lower, text_sq):
                kept.append(s)
                seen.add(canon[0])
            else:
                warnings.append(f"Removed skill '{s}': not found in the pasted text.")
        setattr(ex, group, kept)
    return warnings


def heuristic_extract(text: str) -> JDExtraction:
    ex = JDExtraction()
    for key in skills_catalog.find_known_skills(text):
        ex.required_skills.append(skills_catalog.display_name(key))
    if m := re.search(r"https?://\S+", text):
        ex.apply_url = m.group(0).rstrip(".,)")
    return ex


def extract_jd(text: str) -> tuple[JDExtraction, str, list[str]]:
    """Returns (extraction, method, warnings)."""
    warnings: list[str] = []
    body = text[:MAX_CHARS]
    if len(text) > MAX_CHARS:
        warnings.append("The text was very long; only the first part was analysed.")
    try:
        ex = generate_structured(f"Job description:\n<<<\n{body}\n>>>", JDExtraction, system=SYSTEM_PROMPT, temperature=0.0)
        method = "llm"
    except LLMError as exc:
        log.warning("JD extraction fell back to heuristic: %s", exc)
        ex = heuristic_extract(body)
        method = "heuristic"
        warnings.append("AI extraction was unavailable: only recognised skills were filled in. Please complete the rest.")
    warnings += ground(ex, text)
    return ex, method, warnings
