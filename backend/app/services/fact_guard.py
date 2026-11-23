"""Deterministic fact guard for AI-written resume and cover-letter text. Pure: no DB, no LLM.

The model is only allowed to rephrase what the student's own profile and resume already say.
This module checks its output against that source and reports anything that looks invented:

  number   a figure or year (e.g. "40%", "2024") that is not in the source
  skill    a skill the student has not verified (or has rejected) and that the resume does not mention
  name     a proper name (employer, product, institution...) that is not in the source or the posting
  overlap  a bullet that shares too little wording with the resume entry it claims to come from

Flags never delete prose by themselves (the student decides), except for the skills LIST of a resume,
which may only contain verified skills.
"""

import re
from dataclasses import dataclass, field

from app.schemas.tailoring import Flag
from app.services import skills_catalog

MIN_BULLET_OVERLAP = 0.35

_STOP = set(
    "that with from this have were been being their they them then than also into onto over under about after before "
    "during while where which when what your yours will would should could shall must such each other some more most "
    "very using used uses use make made makes making work worked working team teams project projects role roles "
    "able across within through help helped helping build built building develop developed developing create created".split()
)
_ALLOWED_NAMES = set(
    "dear hiring manager sincerely regards thank thanks best team hello hi respectfully yours faithfully "
    "january february march april may june july august september october november december "
    "monday tuesday wednesday thursday friday saturday sunday".split()
)
_NUM = re.compile(r"\d+(?:[.,]\d+)*%?")
_WORD = re.compile(r"[a-z0-9+#]+")
_PROPER = re.compile(r"\b[A-Z][A-Za-z0-9+#&-]{2,}\b")

# Every word that appears in a catalog skill name or alias ("rest apis" -> "rest", "apis"): common tech vocabulary,
# not a proper name the student could have invented.
_CATALOG_WORDS = {w for alias in skills_catalog._ALIAS_TO_KEY for w in _WORD.findall(alias)}


def _known_word(low: str) -> bool:
    return low in _CATALOG_WORDS or low.rstrip("s") in _CATALOG_WORDS or (low + "s") in _CATALOG_WORDS
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def _norm_num(tok: str) -> str:
    return tok.replace(",", "").rstrip(".")


def numbers_in(text: str) -> set[str]:
    return {_norm_num(t) for t in _NUM.findall(text)}


def words_in(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def content_words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if len(w) >= 4 and w not in _STOP and not w.isdigit()}


@dataclass
class Source:
    """What the student has actually told us. `extra_text` (e.g. the posting) may supply names and numbers
    for a cover letter, but never counts as evidence that the student has a skill."""

    corpus: str
    verified: dict[str, str]  # canonical -> display name
    rejected: set[str] = field(default_factory=set)
    extra_text: str = ""

    def __post_init__(self):
        self.numbers = numbers_in(self.corpus) | numbers_in(self.extra_text)
        self.words = words_in(self.corpus) | words_in(self.extra_text)
        self.skill_keys = set(skills_catalog.find_known_skills(self.corpus))


def skill_supported(key: str, src: Source) -> bool:
    if key in src.rejected:
        return False
    return key in src.verified or key in src.skill_keys


def _sentence_starts(text: str) -> set[int]:
    starts = {0}
    for m in re.finditer(r"[.!?]\s+|\n+", text):
        starts.add(m.end())
    return starts


def check_text(
    text: str, src: Source, where: str, *, ref_text: str | None = None, min_overlap: float = MIN_BULLET_OVERLAP
) -> list[Flag]:
    """Flag unsupported claims in one piece of prose (a bullet, a summary, a letter sentence)."""
    flags: list[Flag] = []
    if not text.strip():
        return flags

    for n in sorted(numbers_in(text) - src.numbers):
        flags.append(Flag(where=where, kind="number", text=n, severity="warning",
                          message=f"The figure '{n}' is not in your profile or resume."))

    for key in skills_catalog.find_known_skills(text):
        if not skill_supported(key, src):
            why = "you rejected it" if key in src.rejected else "it is not in your verified skills or your resume"
            flags.append(Flag(where=where, kind="skill", text=skills_catalog.display_name(key), severity="warning",
                              message=f"'{skills_catalog.display_name(key)}' is mentioned but {why}."))

    starts = _sentence_starts(text)
    seen: set[str] = set()
    for m in _PROPER.finditer(text):
        tok = m.group(0)
        low = tok.lower()
        if m.start() in starts or low in seen:
            continue
        if low in src.words or low in _ALLOWED_NAMES or _known_word(low):
            continue
        seen.add(low)
        flags.append(Flag(where=where, kind="name", text=tok, severity="warning",
                          message=f"The name '{tok}' is not in your profile, resume or the posting."))

    if ref_text is not None:
        cw = content_words(text)
        if cw:
            ratio = len(cw & content_words(ref_text)) / len(cw)
            if ratio < min_overlap:
                flags.append(Flag(where=where, kind="overlap", text=text[:80], severity="warning",
                                  message="This line shares little wording with the resume entry it came from. Check that it is accurate."))
    return flags


def check_letter(paragraphs: list[str], src: Source, where: str = "cover_letter") -> list[Flag]:
    """Sentence-level flags for a cover letter, so the student sees exactly which sentence is the problem."""
    flags: list[Flag] = []
    for pi, para in enumerate(paragraphs, 1):
        for si, sentence in enumerate((s for s in _SENT_SPLIT.split(para) if s.strip()), 1):
            for f in check_text(sentence, src, f"{where}.p{pi}.s{si}"):
                f.text = f.text if f.kind != "overlap" else sentence[:80]
                flags.append(f)
    return flags


def filter_skills(skills: list[str], src: Source, where: str = "skills") -> tuple[list[str], list[Flag]]:
    """A resume skills list may only contain VERIFIED skills. Others are removed and reported."""
    kept: list[str] = []
    seen: set[str] = set()
    flags: list[Flag] = []
    for raw in skills:
        canon = skills_catalog.canonicalize(raw)
        if canon is None or canon[0] in seen:
            continue
        key = canon[0]
        if key in src.verified:
            kept.append(src.verified[key])
            seen.add(key)
        else:
            flags.append(Flag(where=where, kind="skill", text=raw.strip(), severity="removed",
                              message=f"Removed '{raw.strip()}': it is not one of your verified skills."))
    return kept, flags
