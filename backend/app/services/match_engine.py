"""Deterministic, explainable match scoring and skill-gap computation. Pure functions: no DB, no LLM.

    overall = 0.50 required-skill coverage
            + 0.15 preferred-skill coverage
            + 0.20 semantic similarity (profile text vs posting text, rescaled to 0..1)
            + 0.10 education fit   (stated requirement vs profile degree/branch)
            + 0.05 experience fit  (stated requirement vs resume projects/experience)

Principles:
- Only VERIFIED skills count. Skills found in the resume but not verified are shown as a hint, never scored.
- Nothing is guessed. If a posting or profile does not give enough information for a factor, the factor is
  marked not applicable and its weight is redistributed over the others, and the response says so.
- Eligibility checks (graduation year, minimum CGPA) are shown only when the posting states them, and are
  not part of the score.
- The LLM is never involved here.
"""

import re
from dataclasses import dataclass, field

from app.schemas.matching import EligibilityCheck, Factor, GapReport, GapSkill, GapTarget, MatchOut

WEIGHTS = {"required": 0.50, "preferred": 0.15, "semantic": 0.20, "education": 0.10, "experience": 0.05}
LABELS = {
    "required": "Required skills",
    "preferred": "Preferred skills",
    "semantic": "Overall relevance to your profile",
    "education": "Education fit",
    "experience": "Experience fit",
}
# bge-small cosine between a profile text and a posting, measured on real data: the weakest fits sit around 0.54-0.63
# and the best fits around 0.76-0.79. Below SEM_LOW counts as unrelated, SEM_HIGH and above as a strong fit.
SEM_LOW, SEM_HIGH = 0.50, 0.80


@dataclass
class ProfileContext:
    verified: dict[str, str]  # canonical -> display name
    unverified: dict[str, str]  # extracted (not yet verified), canonical -> display name
    degree: str | None = None
    branch: str | None = None
    cgpa: float | None = None
    graduation_year: int | None = None
    has_resume: bool = False
    project_count: int = 0
    experience_count: int = 0
    profile_vector: list[float] | None = None  # embedding of the profile text; None if unavailable


@dataclass
class PostingContext:
    title: str
    required: dict[str, str] = field(default_factory=dict)  # canonical -> display
    preferred: dict[str, str] = field(default_factory=dict)
    education_req: str | None = None
    experience_req: str | None = None
    eligibility_text: str | None = None
    similarity: float | None = None  # raw cosine similarity to the profile, None if unavailable


# ---------- education ----------

_FAMILIES_LONG = {
    "cs": ("computer science", "computer engineering", "information technology", "software", "artificial intelligence",
           "data science", "machine learning", "informatics"),
    "elec": ("electronics", "electrical", "instrumentation", "telecommunication"),
    "stats": ("statistics", "mathematics", "maths"),
    "commerce": ("commerce", "business administration", "management"),
    "design": ("design", "hci"),
}
_FAMILIES_ABBR = {  # matched case-sensitively as whole words ("IT" must not match the pronoun "it")
    "cs": ("CS", "CSE", "IT", "AI", "ML", "AIML", "DS", "ISE"),
    "elec": ("ECE", "EEE", "EE", "E&TC"),
    "commerce": ("BCom", "B.Com", "MBA", "BBA"),
}
_LEVELS = {
    "engineering": (r"\bb\.?\s?tech\b", r"\bb\.e\b",r"\bm\.?\s?tech\b", r"\bengineering\b"),
    "computer_apps": (r"\bbca\b", r"\bmca\b", r"\bb\.?\s?sc\b", r"\bm\.?\s?sc\b"),
}
_GENERIC_ANY = re.compile(r"\b(any|all)\s+(degree|branch(es)?|stream(s)?|discipline(s)?|background)\b", re.I)


def _families(text: str) -> set[str]:
    out: set[str] = set()
    low = text.lower()
    for fam, words in _FAMILIES_LONG.items():
        if any(re.search(r"\b" + re.escape(w) + r"\b", low) for w in words):
            out.add(fam)
    for fam, words in _FAMILIES_ABBR.items():
        if any(re.search(r"(?<![A-Za-z&.])" + re.escape(w) + r"(?![A-Za-z])", text) for w in words):
            out.add(fam)
    return out


def _levels(text: str) -> set[str]:
    low = text.lower()
    return {lvl for lvl, pats in _LEVELS.items() if any(re.search(p, low) for p in pats)}


def education_fit(profile: ProfileContext, req: str | None) -> tuple[float | None, str]:
    if not req or not req.strip():
        return None, "The posting does not state an education requirement."
    mine = " ".join(x for x in (profile.degree, profile.branch) if x).strip()
    if not mine:
        return None, "Add your degree and branch to your profile to check this."
    if _GENERIC_ANY.search(req):
        return 1.0, "The posting is open to any degree or branch."
    want_fams, have_fams = _families(req), _families(mine)
    if want_fams:
        if want_fams & have_fams:
            return 1.0, "Your branch matches a field the posting names."
        return 0.0, (
            f"The posting names a different field than your profile ('{mine}'). "
            "You may still qualify: check with the employer."
        )
    want_lvls, have_lvls = _levels(req), _levels(mine)
    if want_lvls:
        if want_lvls & have_lvls:
            return 1.0, "Your degree matches the level the posting names."
        return 0.0, f"The posting names a different degree than your profile ('{mine}'). Check with the employer."
    return None, "The education requirement could not be compared automatically."


# ---------- experience ----------

_NO_EXPERIENCE = re.compile(r"\b(no prior|none required|none\b|not required|no experience|fresher|freshers welcome)", re.I)


def experience_fit(profile: ProfileContext, req: str | None) -> tuple[float | None, str]:
    if not req or not req.strip():
        return None, "The posting does not state an experience requirement."
    if _NO_EXPERIENCE.search(req):
        return 1.0, "The posting says no prior experience is required."
    if not profile.has_resume:
        return None, "Upload a resume to check this against your projects and experience."
    n = profile.project_count + profile.experience_count
    if n > 0:
        return 1.0, (
            f"The posting asks for hands-on work; your active resume lists {profile.project_count} project(s) "
            f"and {profile.experience_count} experience entr{'y' if profile.experience_count == 1 else 'ies'}."
        )
    return 0.0, "The posting asks for hands-on work; no projects or experience were found in your active resume."


# ---------- eligibility (shown, not scored) ----------

_YEAR_RANGE = re.compile(r"\b(20\d\d)\s*(?:-|–|to)\s*(20\d\d)\b")
_YEAR = re.compile(r"\b(20\d\d)\b")
_CGPA_A = re.compile(r"(?:cgpa|gpa)\D{0,20}(\d{1,2}(?:\.\d+)?)", re.I)
_CGPA_B = re.compile(r"(\d{1,2}(?:\.\d+)?)\s*\+?\s*(?:cgpa|gpa)", re.I)


def graduation_years(text: str) -> set[int]:
    years: set[int] = set()
    for a, b in _YEAR_RANGE.findall(text):
        years.update(range(int(a), int(b) + 1))
    years.update(int(y) for y in _YEAR.findall(_YEAR_RANGE.sub(" ", text)))
    return years


def min_cgpa(text: str) -> float | None:
    for rx in (_CGPA_A, _CGPA_B):
        m = rx.search(text)
        if m:
            v = float(m.group(1))
            if 0 < v <= 10:
                return v
    return None


def eligibility_checks(profile: ProfileContext, posting: PostingContext) -> list[EligibilityCheck]:
    text = " ".join(x for x in (posting.education_req, posting.eligibility_text) if x)
    out: list[EligibilityCheck] = []

    years = graduation_years(text)
    if years:
        listed = ", ".join(str(y) for y in sorted(years))
        if profile.graduation_year is None:
            out.append(EligibilityCheck(key="graduation_year", label="Graduation year", status="unknown",
                                        detail=f"The posting mentions {listed}. Add your graduation year to your profile."))
        elif profile.graduation_year in years:
            out.append(EligibilityCheck(key="graduation_year", label="Graduation year", status="met",
                                        detail=f"You graduate in {profile.graduation_year}; the posting mentions {listed}."))
        else:
            out.append(EligibilityCheck(key="graduation_year", label="Graduation year", status="not_met",
                                        detail=f"You graduate in {profile.graduation_year}; the posting mentions {listed}."))

    need = min_cgpa(text)
    if need is not None:
        if profile.cgpa is None:
            out.append(EligibilityCheck(key="cgpa", label="Minimum CGPA", status="unknown",
                                        detail=f"The posting mentions a CGPA of {need:g}. Add your CGPA to your profile."))
        else:
            ok = profile.cgpa >= need
            out.append(EligibilityCheck(key="cgpa", label="Minimum CGPA", status="met" if ok else "not_met",
                                        detail=f"Your CGPA is {profile.cgpa:g}; the posting mentions {need:g}."))
    return out


# ---------- semantic ----------

def semantic_value(raw: float | None) -> float | None:
    if raw is None:
        return None
    return max(0.0, min(1.0, (raw - SEM_LOW) / (SEM_HIGH - SEM_LOW)))


# ---------- scoring ----------

def _coverage(wanted: dict[str, str], have: dict[str, str]) -> tuple[list[str], list[str]]:
    matched = sorted((n for k, n in wanted.items() if k in have), key=str.lower)
    missing = sorted((n for k, n in wanted.items() if k not in have), key=str.lower)
    return matched, missing


def score_match(profile: ProfileContext, posting: PostingContext) -> tuple[list[Factor], float, dict]:
    """Returns (factors, overall 0..100, skill lists)."""
    m_req, x_req = _coverage(posting.required, profile.verified)
    m_pref, x_pref = _coverage(posting.preferred, profile.verified)

    raw: dict[str, tuple[float | None, str]] = {}
    if posting.required:
        raw["required"] = (len(m_req) / len(posting.required), f"{len(m_req)} of {len(posting.required)} required skills are in your verified skills.")
    else:
        raw["required"] = (None, "The posting lists no required skills.")
    if posting.preferred:
        raw["preferred"] = (len(m_pref) / len(posting.preferred), f"{len(m_pref)} of {len(posting.preferred)} preferred skills are in your verified skills.")
    else:
        raw["preferred"] = (None, "The posting lists no preferred skills.")
    sem = semantic_value(posting.similarity)
    raw["semantic"] = (
        (sem, f"Text similarity {posting.similarity:.2f} ({SEM_LOW:.2f} = unrelated, {SEM_HIGH:.2f} = strong fit), rescaled to {sem:.2f}.")
        if sem is not None
        else (None, "Not available: your profile has too little text or the similarity model was unavailable.")
    )
    raw["education"] = education_fit(profile, posting.education_req)
    raw["experience"] = experience_fit(profile, posting.experience_req)

    applicable_total = sum(WEIGHTS[k] for k, (v, _) in raw.items() if v is not None)
    # Skills are the core of a match. Without any verified skill the other factors would only add noise
    # (e.g. "no experience required" being met), so nothing is scored until the student verifies a skill.
    scoring_enabled = bool(profile.verified)
    factors: list[Factor] = []
    overall = 0.0
    for key in WEIGHTS:
        value, detail = raw[key]
        eff = WEIGHTS[key] / applicable_total if value is not None and applicable_total else 0.0
        contrib = (value or 0.0) * eff * 100 if scoring_enabled else 0.0
        overall += contrib
        factors.append(Factor(key=key, label=LABELS[key], weight=WEIGHTS[key], applicable=value is not None,
                              effective_weight=round(eff, 4), value=None if value is None else round(value, 4),
                              contribution=round(contrib, 2), detail=detail))
    return factors, round(overall, 1), {"m_req": m_req, "x_req": x_req, "m_pref": m_pref, "x_pref": x_pref}


def build_match(profile: ProfileContext, posting: PostingContext, *, internship_id, company: str, source: str) -> MatchOut:
    factors, overall, sk = score_match(profile, posting)
    missing_keys = {k for k in {**posting.required, **posting.preferred} if k not in profile.verified}
    unverified = sorted((profile.unverified[k] for k in missing_keys if k in profile.unverified), key=str.lower)
    notes: list[str] = []
    if not profile.verified:
        notes.append("You have no verified skills yet, so the score is 0. Verify your skills on the Resume Parsing page and it will be calculated.")
    elif unverified:
        notes.append(f"{len(unverified)} missing skill(s) appear in your resume but are not verified, so they are not counted: "
                     + ", ".join(unverified) + ".")
    off = [f.label for f in factors if not f.applicable]
    if off:
        notes.append("Not enough information for: " + ", ".join(off) + ". Their weight was shared across the other factors.")
    return MatchOut(
        internship_id=internship_id, title=posting.title, company=company, source=source, overall=overall,
        factors=factors, matched_required=sk["m_req"], missing_required=sk["x_req"],
        matched_preferred=sk["m_pref"], missing_preferred=sk["x_pref"], unverified_in_resume=unverified,
        eligibility=eligibility_checks(profile, posting), verified_skill_count=len(profile.verified), notes=notes,
    )


# ---------- skill gap ----------

def compute_gap(profile: ProfileContext, postings: list[PostingContext], target: GapTarget) -> GapReport:
    """Rank the skills the student lacks. Demand = how many of the considered postings ask for the skill.

    critical  = required by at least one posting; ordered by how many postings require it, then alphabetically
    secondary = only ever preferred; ordered by how many postings prefer it
    """
    n = len(postings)
    req_count: dict[str, int] = {}
    pref_count: dict[str, int] = {}
    names: dict[str, str] = {}
    for p in postings:
        for k, name in p.required.items():
            req_count[k] = req_count.get(k, 0) + 1
            names[k] = name
        for k, name in p.preferred.items():
            if k not in p.required:
                pref_count[k] = pref_count.get(k, 0) + 1
            names.setdefault(k, name)

    def skill(k: str, importance: str, count: int) -> GapSkill:
        return GapSkill(name=names[k], importance=importance, demand=count, of=n, unverified_in_resume=k in profile.unverified)

    critical = [skill(k, "required", c) for k, c in req_count.items() if k not in profile.verified]
    secondary = [skill(k, "preferred", c) for k, c in pref_count.items() if k not in profile.verified and k not in req_count]
    critical.sort(key=lambda g: (-g.demand, g.name.lower()))
    secondary.sort(key=lambda g: (-g.demand, g.name.lower()))

    demanded = set(req_count) | set(pref_count)
    acquired = sorted((names[k] for k in demanded if k in profile.verified), key=str.lower)
    # Coverage weights each demanded skill by its demand (required counts fully, preferred-only half).
    total = sum(req_count.values()) + 0.5 * sum(pref_count.values())
    have = sum(c for k, c in req_count.items() if k in profile.verified) + 0.5 * sum(
        c for k, c in pref_count.items() if k in profile.verified
    )
    coverage = round(100 * have / total, 1) if total else None

    notes: list[str] = []
    if not postings:
        notes.append("No postings were found for this target, so there is nothing to compare against.")
    elif not demanded:
        notes.append("The considered posting(s) list no skills, so no gap can be computed.")
    if not profile.verified:
        notes.append("You have no verified skills yet. Verify your skills on the Resume Parsing page for an accurate gap.")
    return GapReport(target=target, acquired=acquired, critical=critical, secondary=secondary, coverage=coverage,
                     verified_skill_count=len(profile.verified), notes=notes)
