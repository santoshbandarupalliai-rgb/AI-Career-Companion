"""Unit tests for the deterministic fact guard (pure functions)."""

from app.services import fact_guard as fg
from app.services.fact_guard import Source


def src(corpus="Built a Python script that cleaned 5000 records. Wrote SQL reports. Used Git at Acme Labs in 2025.",
        verified=("Python", "SQL"), rejected=(), extra=""):
    return Source(corpus=corpus, verified={v.lower(): v for v in verified}, rejected=set(rejected), extra_text=extra)


def kinds(flags):
    return sorted((f.kind, f.text) for f in flags)


# ---------- numbers ----------

def test_supported_numbers_pass_and_invented_numbers_are_flagged():
    s = src()
    assert fg.check_text("Cleaned 5000 records with Python.", s, "w") == []
    assert ("number", "40%") in kinds(fg.check_text("Improved speed by 40% with Python.", s, "w"))
    assert ("number", "2024") in kinds(fg.check_text("Worked there in 2024.", s, "w"))
    assert fg.check_text("Worked there in 2025.", s, "w") == []


def test_number_formatting_is_normalised():
    s = src(corpus="Processed 5,000 records and 12.5% growth. Python")
    assert fg.check_text("Processed 5000 records with 12.5% growth in Python.", s, "w") == []


def test_posting_numbers_are_allowed_for_letters_via_extra_text():
    s = src(extra="A 3 months internship")
    assert fg.check_text("I can commit to the 3 months duration.", s, "w") == []
    assert fg.check_text("I can commit to the 3 months duration.", src(), "w") != []


# ---------- skills ----------

def test_skill_claims():
    s = src()
    assert ("skill", "Kubernetes") in kinds(fg.check_text("Deployed services on Kubernetes.", s, "w"))
    assert fg.check_text("Wrote SQL reports in Python.", s, "w") == []
    # Git is in the source text although not verified: a mention in prose is the student's own claim
    assert fg.check_text("Used Git daily.", s, "w") == []


def test_rejected_skill_is_flagged_even_if_in_the_resume_text():
    s = src(corpus="Used Docker. Python.", verified=("Python",), rejected=("docker",))
    assert ("skill", "Docker") in kinds(fg.check_text("Containerised the app with Docker.", s, "w"))


def test_skill_matching_is_exact_not_substring():
    s = src(corpus="JavaScript projects", verified=("JavaScript",))
    assert fg.check_text("Wrote JavaScript.", s, "w") == []
    assert ("skill", "Java") in kinds(fg.check_text("Wrote Java services.", s, "w"))


def test_skills_list_only_keeps_verified_skills():
    s = src(corpus="Docker Python SQL Git")  # Docker/Git appear in the resume but are NOT verified
    kept, flags = fg.filter_skills(["python", "Docker", "SQL", "Haskell", "sql", "Git"], s)
    assert kept == ["Python", "SQL"]  # display names of verified skills, de-duplicated
    assert sorted(f.text for f in flags) == ["Docker", "Git", "Haskell"] and all(f.severity == "removed" for f in flags)


# ---------- names ----------

def test_unknown_proper_names_are_flagged():
    s = src()
    flagged = {f.text for f in fg.check_text("Interned at Globex Corporation using Python.", s, "w") if f.kind == "name"}
    assert flagged == {"Globex", "Corporation"}


def test_known_names_sentence_starts_and_acronyms_are_not_flagged():
    s = src(extra="Brightlane Analytics hires a Python intern")
    assert not [f for f in fg.check_text("Excited about Brightlane Analytics and its Python work.", s, "w") if f.kind == "name"]
    assert not [f for f in fg.check_text("Built tools. Delivered reports. Python and SQL.", s, "w") if f.kind == "name"]
    assert not [f for f in fg.check_text("Worked with REST APIs and SQL in Python.", s, "w") if f.kind == "name"]
    assert not [f for f in fg.check_text("Dear Hiring Manager, I used Python.", s, "w") if f.kind == "name"]


# ---------- overlap ----------

def test_bullet_overlap_catches_lines_that_do_not_come_from_the_entry():
    ref = "Built a Python script that cleaned 5000 records for the sales team"
    s = src()
    assert fg.check_text("Developed a Python script cleaning 5000 records for sales.", s, "w", ref_text=ref) == []
    flags = fg.check_text("Led a cross functional initiative improving customer satisfaction.", s, "w", ref_text=ref)
    assert [f.kind for f in flags] == ["overlap"]


def test_overlap_not_checked_without_a_reference():
    assert fg.check_text("Led a cross functional initiative improving customer satisfaction.", src(), "w") == []


# ---------- letter ----------

def test_letter_flags_point_at_the_exact_sentence():
    paragraphs = [
        "I am applying for the Python role. I cleaned 5000 records.",
        "I increased revenue by 90% at Initech.",
    ]
    flags = fg.check_letter(paragraphs, src())
    where = {f.where for f in flags}
    assert where == {"cover_letter.p2.s1"}
    assert {"number", "name"} <= {f.kind for f in flags}


def test_empty_text_has_no_flags():
    assert fg.check_text("   ", src(), "w") == []
