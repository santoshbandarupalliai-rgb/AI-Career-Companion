import hashlib
import math
import re

import pytest
from sqlalchemy import select

from app.llm import LLMError
from app.models import StudentSkill, User
from app.rag import embeddings
from app.schemas.matching import LearningPlan, PlanStep
from app.services import internship_service, matching_service, plan_service, skill_service
from tests.conftest import bearer


def _fake_vec(text: str) -> list[float]:
    v = [0.0] * embeddings.DIM
    for w in re.findall(r"[a-z0-9+#]+", text.lower()):
        v[int(hashlib.md5(w.encode()).hexdigest(), 16) % embeddings.DIM] += 1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


@pytest.fixture(autouse=True)
def fakes(monkeypatch):
    monkeypatch.setattr(embeddings, "embed_documents", lambda texts: [_fake_vec(t) for t in texts])
    monkeypatch.setattr(internship_service, "embed_query", _fake_vec)
    monkeypatch.setattr(matching_service, "ROLE_MIN_SIMILARITY", -1.0)  # fake vectors are not calibrated


@pytest.fixture()
def seeded(db_session_factory):
    with db_session_factory() as db:
        internship_service.seed_samples(db)


@pytest.fixture()
def auth(register):
    def _auth(email="a@example.com"):
        return bearer(register(email=email).json()["access_token"])

    return _auth


def verify(client, h, *names):
    for n in names:
        assert client.post("/api/skills", headers=h, json={"name": n}).status_code == 201


def find(client, h, title_start):
    items = client.get("/api/internships?limit=100", headers=h).json()["items"]
    return next(i for i in items if i["title"].startswith(title_start))


def add_extracted(db_session_factory, email, *names):
    """Simulate skills found in a resume but not yet verified."""
    with db_session_factory() as db:
        user = db.scalar(select(User).where(User.email == email))
        for n in names:
            skill = skill_service.get_or_create_skill(db, n)
            db.add(StudentSkill(user_id=user.id, skill_id=skill.id, status="extracted", source="resume"))
        db.commit()


# ---------- scoring through the API ----------

def test_requires_auth(client):
    for url in ("/api/matching", "/api/skill-gap?role=backend"):
        assert client.get(url).status_code == 401
    assert client.post("/api/skill-gap/plan", json={"role": "backend"}).status_code == 401


def test_list_is_ranked_and_reflects_verified_skills(client, auth, seeded):
    h = auth()
    verify(client, h, "Python", "FastAPI", "SQL", "Git")
    body = client.get("/api/matching?limit=200", headers=h).json()
    scores = [i["overall"] for i in body["items"]]
    assert scores == sorted(scores, reverse=True) and len(scores) == 20
    top = body["items"][0]
    assert top["title"].startswith("Backend Developer Intern (Python)")
    assert top["required_matched"] == top["required_total"] == 4 and top["missing_required"] == []
    assert body["verified_skill_count"] == 4 and body["notes"] == []


def test_no_verified_skills_is_disclosed(client, auth, seeded):
    body = client.get("/api/matching", headers=auth()).json()
    assert body["verified_skill_count"] == 0 and body["notes"]
    assert all(i["required_matched"] == 0 for i in body["items"])


def test_detail_breakdown_is_complete_and_consistent(client, auth, seeded):
    h = auth()
    verify(client, h, "Python", "SQL")
    client.put("/api/profile", headers=h, json={"degree": "B.Tech", "branch": "Computer Science", "graduation_year": 2026, "cgpa": 8})
    posting = find(client, h, "Backend Developer Intern (Python)")
    m = client.get(f"/api/matching/{posting['id']}", headers=h).json()
    assert [f["key"] for f in m["factors"]] == ["required", "preferred", "semantic", "education", "experience"]
    assert m["matched_required"] == ["Python", "SQL"] and m["missing_required"] == ["FastAPI", "Git"]
    assert sum(f["contribution"] for f in m["factors"]) == pytest.approx(m["overall"], abs=0.1)
    assert sum(f["effective_weight"] for f in m["factors"] if f["applicable"]) == pytest.approx(1.0, abs=0.01)
    edu = next(f for f in m["factors"] if f["key"] == "education")
    assert edu["applicable"] and edu["value"] == 1.0
    grad = next(e for e in m["eligibility"] if e["key"] == "graduation_year")
    assert grad["status"] == "met"


def test_unverified_resume_skills_are_not_counted_but_are_suggested(client, auth, seeded, db_session_factory):
    h = auth()
    verify(client, h, "Python")
    posting = find(client, h, "Backend Developer Intern (Python)")
    before = client.get(f"/api/matching/{posting['id']}", headers=h).json()
    add_extracted(db_session_factory, "a@example.com", "FastAPI", "SQL")
    after = client.get(f"/api/matching/{posting['id']}", headers=h).json()
    assert after["overall"] == before["overall"]
    assert after["matched_required"] == ["Python"]
    assert after["unverified_in_resume"] == ["FastAPI", "SQL"]


def test_each_user_is_scored_on_their_own_skills(client, auth, seeded):
    a, b = auth("a@example.com"), auth("b@example.com")
    verify(client, a, "Python", "FastAPI", "SQL", "Git")
    posting = find(client, a, "Backend Developer Intern (Python)")
    assert client.get(f"/api/matching/{posting['id']}", headers=a).json()["overall"] > client.get(
        f"/api/matching/{posting['id']}", headers=b
    ).json()["overall"]
    assert client.get(f"/api/matching/{posting['id']}", headers=b).json()["verified_skill_count"] == 0


def test_cannot_match_against_someone_elses_private_internship(client, auth, seeded):
    a, b = auth("a@example.com"), auth("b@example.com")
    mine = client.post("/api/internships", headers=a, json={
        "title": "Secret Role", "company": "Hidden Co", "description": "A private posting only for its creator to see.",
        "skills": [{"name": "Python", "importance": "required"}]}).json()
    assert client.get(f"/api/matching/{mine['id']}", headers=a).status_code == 200
    assert client.get(f"/api/matching/{mine['id']}", headers=b).status_code == 404
    assert client.post(f"/api/matching/{mine['id']}/explain", headers=b).status_code == 404
    assert all(i["title"] != "Secret Role" for i in client.get("/api/matching?limit=200", headers=b).json()["items"])
    assert client.get(f"/api/skill-gap?internship_id={mine['id']}", headers=b).status_code == 404


def test_embedding_outage_degrades_to_skills_only_scoring(client, auth, seeded, monkeypatch):
    h = auth()
    verify(client, h, "Python")

    def boom(texts):
        raise embeddings.EmbeddingError("down")

    monkeypatch.setattr(embeddings, "embed_documents", boom)
    posting = find(client, h, "Backend Developer Intern (Python)")
    m = client.get(f"/api/matching/{posting['id']}", headers=h).json()
    sem = next(f for f in m["factors"] if f["key"] == "semantic")
    assert sem["applicable"] is False and m["overall"] > 0


# ---------- explanation ----------

def test_explain_uses_the_computed_facts_and_degrades_gracefully(client, auth, seeded, monkeypatch):
    h = auth()
    verify(client, h, "Python")
    posting = find(client, h, "Backend Developer Intern (Python)")
    seen = {}

    def fake_text(prompt, **kw):
        seen["prompt"] = prompt
        return "You match on Python. See https://evil.example for more."

    monkeypatch.setattr(plan_service, "generate_text", fake_text)
    r = client.post(f"/api/matching/{posting['id']}/explain", headers=h).json()
    assert r["available"] is True and "evil.example" not in r["narrative"]
    assert "Overall score:" in seen["prompt"] and "Missing required: FastAPI, Git, SQL" in seen["prompt"]

    def fail(*a, **k):
        raise LLMError("The AI service is rate-limited right now. Please try again in a minute.")

    monkeypatch.setattr(plan_service, "generate_text", fail)
    r = client.post(f"/api/matching/{posting['id']}/explain", headers=h)
    assert r.status_code == 200 and r.json() == {"narrative": None, "available": False, "message": "The AI service is rate-limited right now. Please try again in a minute."}
    # the score itself is unaffected
    assert client.get(f"/api/matching/{posting['id']}", headers=h).json()["overall"] > 0


# ---------- skill gap ----------

def test_gap_for_an_internship(client, auth, seeded, db_session_factory):
    h = auth()
    verify(client, h, "Python", "Git")
    add_extracted(db_session_factory, "a@example.com", "SQL")
    posting = find(client, h, "Backend Developer Intern (Python)")
    g = client.get(f"/api/skill-gap?internship_id={posting['id']}", headers=h).json()
    assert g["target"]["type"] == "internship"
    assert g["acquired"] == ["Git", "Python"]
    assert {s["name"] for s in g["critical"]} == {"FastAPI", "SQL"}
    assert next(s for s in g["critical"] if s["name"] == "SQL")["unverified_in_resume"] is True
    assert {s["name"] for s in g["secondary"]} == {"Docker", "PostgreSQL", "pytest"}
    assert 0 < g["coverage"] < 100


def test_gap_for_a_role_aggregates_best_matching_postings(client, auth, seeded):
    h = auth()
    verify(client, h, "Python")
    g = client.get("/api/skill-gap?role=python backend developer api", headers=h).json()
    assert g["target"]["type"] == "role" and 1 <= len(g["target"]["postings_considered"]) <= matching_service.ROLE_TOP_K
    assert g["critical"] and all(s["of"] == len(g["target"]["postings_considered"]) for s in g["critical"])
    demands = [s["demand"] for s in g["critical"]]
    assert demands == sorted(demands, reverse=True)


def test_gap_target_validation(client, auth, seeded):
    h = auth()
    posting = find(client, h, "Backend Developer Intern (Python)")
    assert client.get("/api/skill-gap", headers=h).status_code == 400
    assert client.get(f"/api/skill-gap?role=backend&internship_id={posting['id']}", headers=h).status_code == 400
    assert client.get("/api/skill-gap?role=x", headers=h).status_code == 422


# ---------- learning plan ----------

def test_plan_keeps_only_asked_skills_and_strips_links(client, auth, seeded, monkeypatch):
    h = auth()
    verify(client, h, "Python", "Git")
    posting = find(client, h, "Backend Developer Intern (Python)")

    def fake(prompt, schema, **kw):
        assert "FastAPI" in prompt and "Python (" not in prompt  # only missing skills are sent
        return LearningPlan(summary="Focus on the API basics. See https://x.test", steps=[
            PlanStep(skill="Haskell", why="invented", how_to_learn="x", practice_project="y"),
            PlanStep(skill="sql", why="Needed for data. www.spam.test", how_to_learn="Study joins https://c.test/a", practice_project="Build a report"),
            PlanStep(skill="FastAPI", why="Core framework", how_to_learn="Routing and validation", practice_project="A todo API"),
            PlanStep(skill="FastAPI", why="duplicate", how_to_learn="d", practice_project="d"),
        ])

    monkeypatch.setattr(plan_service, "generate_structured", fake)
    r = client.post("/api/skill-gap/plan", headers=h, json={"internship_id": posting["id"]}).json()
    assert r["plan_available"] is True
    names = [s["skill"] for s in r["plan"]["steps"]]
    assert names == ["FastAPI", "SQL"]  # gap order (by demand then name), invented and duplicate steps dropped
    blob = str(r["plan"])
    assert "http" not in blob and "www." not in blob
    assert r["gap"]["critical"]


def test_plan_failure_still_returns_the_gap(client, auth, seeded, monkeypatch):
    h = auth()
    posting = find(client, h, "Backend Developer Intern (Python)")

    def fail(*a, **k):
        raise LLMError("The AI service request failed.")

    monkeypatch.setattr(plan_service, "generate_structured", fail)
    r = client.post("/api/skill-gap/plan", headers=h, json={"internship_id": posting["id"]})
    body = r.json()
    assert r.status_code == 200 and body["plan_available"] is False and body["plan"] is None
    assert body["message"] == "The AI service request failed." and body["gap"]["critical"]


def test_no_plan_needed_when_nothing_is_missing(client, auth, seeded, monkeypatch):
    h = auth()
    verify(client, h, "Python", "FastAPI", "SQL", "Git", "PostgreSQL", "Docker", "pytest")
    posting = find(client, h, "Backend Developer Intern (Python)")
    monkeypatch.setattr(plan_service, "generate_structured", lambda *a, **k: pytest.fail("LLM must not be called"))
    body = client.post("/api/skill-gap/plan", headers=h, json={"internship_id": posting["id"]}).json()
    assert body["plan"] is None and "no missing skills" in body["message"] and body["gap"]["coverage"] == 100.0


def test_plan_ignores_client_supplied_gaps(client, auth, seeded, monkeypatch):
    h = auth()
    posting = find(client, h, "Backend Developer Intern (Python)")
    prompts = []
    monkeypatch.setattr(plan_service, "generate_structured", lambda p, s, **k: prompts.append(p) or LearningPlan())
    client.post("/api/skill-gap/plan", headers=h, json={"internship_id": posting["id"], "gaps": ["Kubernetes"]})
    assert prompts and "Kubernetes" not in prompts[0]


def test_match_list_includes_stipend_and_duration(client, auth, seeded):
    h = auth()
    client.post("/api/skills", headers=h, json={"name": "Python"})
    items = client.get("/api/matching", headers=h).json()["items"]
    assert items and all(i["stipend"] and i["duration"] for i in items)  # every sample posting states both
