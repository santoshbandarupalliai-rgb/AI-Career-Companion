"""LLM add-ons for matching and skill gap: a short explanation and a learning plan.

Both are OPTIONAL and sit on top of numbers computed deterministically elsewhere. The model is only
given the already-computed facts and may not change them; if it fails, the caller still has the full
score/gap and is told the narrative/plan is unavailable. No canned or invented fallback text, and no URLs.
"""

import logging
import re

from app.llm import LLMError, generate_structured, generate_text
from app.schemas.matching import Explanation, GapReport, LearningPlan, MatchOut, PlanStep

log = logging.getLogger(__name__)

EXPLAIN_SYSTEM = """You explain an internship match score to a student in 3-5 plain sentences.
Use ONLY the facts provided. Do not change or recompute any number. Do not invent skills, requirements, or advice
about companies. Mention the biggest strengths and the most important gaps, and say what the student could do next
(for example verify a skill that appears in their resume). If a factor is marked not applicable, do not guess about it."""

PLAN_SYSTEM = """You write a short, practical learning plan for a student who lacks some skills for an internship target.
Rules:
- Create exactly one step for each skill in the provided list, in the same order, using the exact skill name.
- Each step: why it matters for this target (one sentence), how to learn it (concrete topics to study, no websites or links),
  and one small practice project the student can build.
- Do not add skills that are not in the list. Do not include URLs, course names, or platform names.
- If a skill is flagged as already in the student's resume, say the first step is to verify it if they genuinely have it."""

_URL = re.compile(r"https?://\S+|www\.\S+", re.I)


def _facts(m: MatchOut) -> str:
    lines = [f"Internship: {m.title} at {m.company}", f"Overall score: {m.overall}/100"]
    for f in m.factors:
        status = f"value {f.value:.2f}, contributes {f.contribution:.1f} points" if f.applicable else "not applicable"
        lines.append(f"- {f.label}: {status}. {f.detail}")
    lines.append("Matched required: " + (", ".join(m.matched_required) or "none"))
    lines.append("Missing required: " + (", ".join(m.missing_required) or "none"))
    lines.append("Matched preferred: " + (", ".join(m.matched_preferred) or "none"))
    lines.append("Missing preferred: " + (", ".join(m.missing_preferred) or "none"))
    if m.unverified_in_resume:
        lines.append("In resume but not verified (not counted): " + ", ".join(m.unverified_in_resume))
    for e in m.eligibility:
        lines.append(f"Eligibility - {e.label}: {e.status}. {e.detail}")
    return "\n".join(lines)


def explain_match(m: MatchOut) -> Explanation:
    try:
        text = generate_text(_facts(m), system=EXPLAIN_SYSTEM, temperature=0.2).strip()
    except LLMError as exc:
        log.warning("match explanation unavailable: %s", exc)
        return Explanation(narrative=None, available=False, message=str(exc) or "The explanation is unavailable right now.")
    return Explanation(narrative=_URL.sub("", text).strip(), available=True)


def make_plan(gap: GapReport) -> tuple[LearningPlan | None, str | None]:
    """Returns (plan, message). plan is None when generation failed or there is nothing to learn."""
    skills = gap.critical + gap.secondary
    if not skills:
        return None, "You have no missing skills for this target, so no plan is needed."
    listing = "\n".join(
        f"{i}. {s.name} ({s.importance}; asked by {s.demand} of {s.of} posting(s))"
        + (" [already in the student's resume, not yet verified]" if s.unverified_in_resume else "")
        for i, s in enumerate(skills[:8], 1)
    )
    prompt = f"Target: {gap.target.label}\nSkills the student is missing, most important first:\n{listing}"
    try:
        plan = generate_structured(prompt, LearningPlan, system=PLAN_SYSTEM, temperature=0.3)
    except LLMError as exc:
        log.warning("learning plan unavailable: %s", exc)
        return None, str(exc) or "The learning plan is unavailable right now."

    # Keep only steps for skills we actually asked about, once each, in gap order; strip any links.
    allowed = {s.name.lower(): s.name for s in skills[:8]}
    by_skill: dict[str, PlanStep] = {}
    for step in plan.steps:
        key = step.skill.strip().lower()
        if key in allowed and key not in by_skill:
            by_skill[key] = PlanStep(
                skill=allowed[key], why=_URL.sub("", step.why).strip(),
                how_to_learn=_URL.sub("", step.how_to_learn).strip(), practice_project=_URL.sub("", step.practice_project).strip(),
            )
    steps = [by_skill[s.name.lower()] for s in skills[:8] if s.name.lower() in by_skill]
    if not steps:
        return None, "The AI did not return a usable plan. Please try again."
    return LearningPlan(summary=_URL.sub("", plan.summary).strip(), steps=steps), None
