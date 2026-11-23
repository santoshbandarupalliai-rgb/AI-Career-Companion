"""Pure-function tests for the scoring and gap engine. Expected numbers are worked out by hand."""

import uuid

import pytest

from app.schemas.matching import GapTarget
from app.services import match_engine as me
from app.services.match_engine import PostingContext, ProfileContext


def skills(*names):
    return {n.lower(): n for n in names}


def profile(**kw):
    base = dict(verified=skills("Python", "SQL"), unverified={}, degree="B.Tech", branch="Computer Science",
                cgpa=8.0, graduation_year=2026, has_resume=True, project_count=2, experience_count=0)
    base.update(kw)
    return ProfileContext(**base)


def posting(**kw):
    base = dict(title="Intern", required=skills("Python", "SQL", "Docker", "Git"), preferred=skills("Redis", "SQL2"),
                education_req="B.Tech in CS", experience_req="None required", similarity=0.65)
    base.update(kw)
    return PostingContext(**base)


def build(p, q):
    return me.build_match(p, q, internship_id=uuid.uuid4(), company="Acme", source="sample")


def test_weights_sum_to_one():
    assert sum(me.WEIGHTS.values()) == pytest.approx(1.0)


def test_hand_computed_overall():
    # required 2/4 = 0.5 -> 25 ; preferred 0/2 -> 0 ; semantic (0.65-0.50)/0.30 = 0.5 -> 10 ; education 1 -> 10 ; experience 1 -> 5
    m = build(profile(), posting())
    assert m.overall == 50.0
    by = {f.key: f for f in m.factors}
    assert by["required"].contribution == 25.0 and by["required"].value == 0.5
    assert by["preferred"].contribution == 0.0
    assert by["semantic"].value == pytest.approx(0.5)
    assert by["education"].contribution == 10.0 and by["experience"].contribution == 5.0
    assert sum(f.contribution for f in m.factors) == pytest.approx(m.overall, abs=0.05)
    assert m.matched_required == ["Python", "SQL"] and m.missing_required == ["Docker", "Git"]


def test_perfect_match_is_100():
    p = profile(verified=skills("Python", "SQL", "Docker", "Git", "Redis", "SQL2"))
    assert build(p, posting(similarity=0.80)).overall == 100.0


def test_nothing_matches_gives_low_but_valid_score():
    p = profile(verified={}, degree="B.Com", branch="Commerce", project_count=0)
    m = build(p, posting(similarity=0.30, experience_req="Portfolio needed"))
    assert 0.0 <= m.overall <= 100.0 and m.overall == 0.0
    assert any("no verified skills" in n.lower() for n in m.notes)


def test_nothing_is_scored_until_a_skill_is_verified():
    # even with education and experience "met", a student with no verified skill scores 0, not noise
    m = build(profile(verified={}), posting(experience_req="None required"))
    assert m.overall == 0.0 and all(f.contribution == 0 for f in m.factors)
    assert any(f.key == "experience" and f.applicable and f.value == 1.0 for f in m.factors)  # still explained
    assert any("score is 0" in n for n in m.notes)


def test_unverified_skills_are_not_counted_but_are_flagged():
    base = build(profile(), posting())
    with_hint = build(profile(unverified={"docker": "Docker"}), posting())
    assert with_hint.overall == base.overall  # not scored
    assert with_hint.unverified_in_resume == ["Docker"]
    assert any("not verified" in n for n in with_hint.notes)


def test_missing_information_redistributes_weight_and_is_disclosed():
    q = posting(preferred={}, education_req=None, experience_req=None, similarity=None)
    m = build(profile(), q)  # only "required" is applicable -> it carries all the weight
    by = {f.key: f for f in m.factors}
    assert [f.key for f in m.factors if f.applicable] == ["required"]
    assert by["required"].effective_weight == 1.0
    assert m.overall == 50.0  # 2 of 4 required
    assert all(f.contribution == 0 for f in m.factors if not f.applicable)
    assert any("Not enough information" in n for n in m.notes)


def test_no_listed_skills_and_nothing_else_scores_zero_not_a_crash():
    m = build(profile(), PostingContext(title="x"))
    assert m.overall == 0.0 and not any(f.applicable for f in m.factors)


def test_skill_matching_is_exact_not_substring():
    # canonical keys differ, so a Java-only student does not satisfy JavaScript
    p = profile(verified={"java": "Java"})
    m = build(p, posting(required={"javascript": "JavaScript"}, preferred={}))
    assert m.matched_required == [] and m.missing_required == ["JavaScript"]


# ---------- education ----------

@pytest.mark.parametrize(
    "degree,branch,req,expected",
    [
        ("B.Tech", "Computer Science", "B.Tech/B.E. in CS, IT or related, graduating 2026 or 2027", 1.0),
        ("B.Tech", "Electronics (ECE)", "B.Tech/B.E. in CS, IT or related", 0.0),
        ("B.Tech", "Mechanical", "Any degree; strong fundamentals matter more than branch", 1.0),
        ("B.Com", "Commerce", "Any engineering or BCA/MCA student", 0.0),
        ("B.Tech", "Civil", "Any engineering or BCA/MCA student", 1.0),
        ("BCA", "", "Any engineering or BCA/MCA student", 1.0),
        ("B.Sc", "Statistics", "Final-year students in statistics, maths, CS or commerce", 1.0),
        ("B.Tech", "Computer Science", "We need students who like it and must be enrolled", None),
        ("B.Tech", "Computer Science", "Any technical degree", None),
    ],
)
def test_education_rules(degree, branch, req, expected):
    value, _ = me.education_fit(profile(degree=degree, branch=branch), req)
    assert value == expected


def test_education_unknown_when_profile_or_posting_is_silent():
    assert me.education_fit(profile(degree=None, branch=None), "B.Tech in CS")[0] is None
    assert me.education_fit(profile(), None)[0] is None


# ---------- experience ----------

def test_experience_rules():
    assert me.experience_fit(profile(), "No prior internship needed; a personal API project helps")[0] == 1.0
    assert me.experience_fit(profile(project_count=1), "Portfolio of at least one React project")[0] == 1.0
    assert me.experience_fit(profile(project_count=0, experience_count=0), "Portfolio of at least one React project")[0] == 0.0
    assert me.experience_fit(profile(has_resume=False), "Portfolio of at least one React project")[0] is None
    assert me.experience_fit(profile(), "")[0] is None


# ---------- eligibility ----------

def elig(p, **kw):
    return {c.key: c.status for c in me.eligibility_checks(p, PostingContext(title="x", **kw))}


def test_graduation_year_checks():
    assert elig(profile(graduation_year=2026), education_req="B.Tech, graduating 2026 or 2027") == {"graduation_year": "met"}
    assert elig(profile(graduation_year=2026), education_req="2025-2027 batches") == {"graduation_year": "met"}
    assert elig(profile(graduation_year=2028), education_req="2026-2027 batches") == {"graduation_year": "not_met"}
    assert elig(profile(graduation_year=None), education_req="2026 graduates") == {"graduation_year": "unknown"}
    assert elig(profile(), education_req="B.Tech in CS") == {}  # nothing stated -> nothing shown


def test_cgpa_checks():
    assert elig(profile(cgpa=8.2), eligibility_text="Minimum CGPA 7.5 required") == {"cgpa": "met"}
    assert elig(profile(cgpa=6.9), eligibility_text="7.0+ CGPA") == {"cgpa": "not_met"}
    assert elig(profile(cgpa=None), eligibility_text="CGPA of 7") == {"cgpa": "unknown"}
    assert elig(profile(), eligibility_text="strong CGPA preferred") == {}


def test_eligibility_does_not_change_the_score():
    a = build(profile(graduation_year=2026), posting(education_req="B.Tech in CS, 2026"))
    b = build(profile(graduation_year=2030), posting(education_req="B.Tech in CS, 2026"))
    assert a.overall == b.overall
    assert {c.status for c in a.eligibility} == {"met"} and {c.status for c in b.eligibility} == {"not_met"}


# ---------- semantic rescale ----------

def test_semantic_rescale_bounds():
    assert me.semantic_value(None) is None
    assert me.semantic_value(0.2) == 0.0 and me.semantic_value(0.99) == 1.0
    assert me.semantic_value(0.65) == pytest.approx(0.5)


# ---------- gap ----------

TARGET = GapTarget(type="role", label="backend", postings_considered=[])


def test_gap_ranks_by_demand_and_separates_critical_from_secondary():
    p = profile(verified=skills("Python"), unverified={"docker": "Docker"})
    postings = [
        PostingContext(title="a", required=skills("Python", "SQL", "Docker"), preferred=skills("Redis")),
        PostingContext(title="b", required=skills("SQL", "Git"), preferred=skills("Redis", "Kafka")),
        PostingContext(title="c", required=skills("SQL"), preferred=skills("Kafka")),
    ]
    g = me.compute_gap(p, postings, TARGET)
    assert [(s.name, s.demand) for s in g.critical] == [("SQL", 3), ("Docker", 1), ("Git", 1)]
    assert [(s.name, s.demand) for s in g.secondary] == [("Kafka", 2), ("Redis", 2)]
    assert g.acquired == ["Python"]
    assert next(s for s in g.critical if s.name == "Docker").unverified_in_resume is True
    assert next(s for s in g.critical if s.name == "SQL").unverified_in_resume is False
    assert all(s.of == 3 for s in g.critical + g.secondary)


def test_gap_coverage_arithmetic():
    # required: Python(1) SQL(1) -> verified Python ; preferred-only: Redis(1) -> half weight, not verified
    # total = 2 + 0.5 = 2.5 ; have = 1 -> 40.0
    g = me.compute_gap(profile(verified=skills("Python")),
                       [PostingContext(title="a", required=skills("Python", "SQL"), preferred=skills("Redis"))], TARGET)
    assert g.coverage == 40.0


def test_gap_skill_required_somewhere_is_never_secondary():
    g = me.compute_gap(profile(verified={}),
                       [PostingContext(title="a", required=skills("SQL")), PostingContext(title="b", preferred=skills("SQL"))], TARGET)
    assert [s.name for s in g.critical] == ["SQL"] and g.secondary == []


def test_gap_with_nothing_to_compare():
    g = me.compute_gap(profile(), [], TARGET)
    assert g.coverage is None and g.critical == [] and any("nothing to compare" in n for n in g.notes)
    g2 = me.compute_gap(profile(), [PostingContext(title="x")], TARGET)
    assert g2.coverage is None and any("no skills" in n for n in g2.notes)


def test_gap_is_complete_when_all_verified():
    g = me.compute_gap(profile(verified=skills("Python", "SQL")), [PostingContext(title="a", required=skills("Python", "SQL"))], TARGET)
    assert g.critical == [] and g.secondary == [] and g.coverage == 100.0 and g.acquired == ["Python", "SQL"]
