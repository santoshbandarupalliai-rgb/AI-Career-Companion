import hashlib
import math
import re

import pytest

from app.llm import LLMError
from app.rag import embeddings
from app.rag.chunker import chunk_text
from app.seed.sample_internships import SAMPLES
from app.services import internship_service, jd_parser
from app.services.jd_parser import JDExtraction
from tests.conftest import bearer


def _fake_vec(text: str) -> list[float]:
    """Deterministic bag-of-words embedding: texts sharing words are close."""
    v = [0.0] * embeddings.DIM
    for w in re.findall(r"[a-z0-9+#]+", text.lower()):
        v[int(hashlib.md5(w.encode()).hexdigest(), 16) % embeddings.DIM] += 1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


@pytest.fixture(autouse=True)
def fake_embeddings(monkeypatch):
    monkeypatch.setattr(embeddings, "embed_documents", lambda texts: [_fake_vec(t) for t in texts])
    monkeypatch.setattr(internship_service, "embed_query", lambda q: _fake_vec(q))


@pytest.fixture()
def auth(register):
    def _auth(email="student@example.com"):
        return bearer(register(email=email).json()["access_token"])

    return _auth


@pytest.fixture()
def seeded(db_session_factory):
    with db_session_factory() as db:
        internship_service.seed_samples(db)


JD = (
    "Acme Robotics is hiring a Python Intern in Pune (hybrid). Stipend: 15000/month for 3 months. "
    "Required: Python, SQL. Nice to have: Docker. Apply at https://example.com/jobs/42"
)


# ---------- chunker ----------

def test_chunk_empty_and_short():
    assert chunk_text("   ") == []
    assert chunk_text("One short paragraph.") == ["One short paragraph."]


def test_chunk_long_text_respects_max_and_overlaps():
    text = "\n\n".join(f"Paragraph {i}. " + ("word " * 60) for i in range(12))
    chunks = chunk_text(text, max_chars=600, overlap=100)
    assert len(chunks) > 1
    assert all(len(c) <= 600 + 120 for c in chunks)
    assert "Paragraph 0." in chunks[0] and "Paragraph 11." in chunks[-1]


def test_chunk_splits_single_huge_paragraph():
    chunks = chunk_text("x" * 5000, max_chars=1000, overlap=100)
    assert len(chunks) >= 5


def test_chunk_rejects_bad_overlap():
    with pytest.raises(ValueError):
        chunk_text("text", max_chars=100, overlap=100)


# ---------- seed ----------

def test_seed_adds_samples_once(db_session_factory):
    with db_session_factory() as db:
        assert internship_service.seed_samples(db) == len(SAMPLES)
        assert internship_service.seed_samples(db) == 0


def test_sample_data_is_wellformed():
    assert len(SAMPLES) >= 20
    assert len({s["seed_key"] for s in SAMPLES}) == len(SAMPLES)
    for s in SAMPLES:
        assert s["required"], s["seed_key"]
        assert s["work_mode"] in ("remote", "onsite", "hybrid")


# ---------- API: list / filter / detail ----------

def test_requires_auth(client):
    assert client.get("/api/internships").status_code == 401
    assert client.get("/api/internships/search?q=python").status_code == 401


def test_list_marks_samples_and_filters(client, auth, seeded):
    h = auth()
    body = client.get("/api/internships?limit=100", headers=h).json()
    assert body["total"] == len(SAMPLES)
    assert all(i["source"] == "sample" for i in body["items"])

    remote = client.get("/api/internships?work_mode=remote", headers=h).json()
    assert remote["total"] > 0 and all(i["work_mode"] == "remote" for i in remote["items"])

    by_skill = client.get("/api/internships?skill=fast api", headers=h).json()  # alias normalised
    assert by_skill["total"] > 0
    assert all("FastAPI" in [s["name"] for s in i["skills"]] for i in by_skill["items"])

    assert client.get("/api/internships?q=brightlane", headers=h).json()["total"] == 1
    assert client.get("/api/internships?work_mode=bogus", headers=h).status_code == 422


def test_skill_filter_is_exact_not_substring(client, auth, seeded):
    h = auth()
    java = client.get("/api/internships?skill=java&limit=100", headers=h).json()
    for i in java["items"]:
        assert "Java" in [s["name"] for s in i["skills"]]  # never matches JavaScript-only postings


def test_detail_and_404(client, auth, seeded):
    h = auth()
    first = client.get("/api/internships", headers=h).json()["items"][0]
    assert client.get(f"/api/internships/{first['id']}", headers=h).json()["title"] == first["title"]
    assert client.get("/api/internships/00000000-0000-0000-0000-000000000000", headers=h).status_code == 404


# ---------- API: semantic search ----------

def test_search_ranks_relevant_first(client, auth, seeded):
    h = auth()
    r = client.get("/api/internships/search?q=retrieval augmented generation prompt engineering LLM", headers=h)
    assert r.status_code == 200
    results = r.json()
    assert results[0]["title"].startswith("Generative AI Intern")
    assert results[0]["score"] >= results[-1]["score"]
    assert results[0]["snippet"]


def test_search_respects_filters(client, auth, seeded):
    h = auth()
    r = client.get("/api/internships/search?q=python developer&work_mode=onsite", headers=h).json()
    assert r and all(i["work_mode"] == "onsite" for i in r)


def test_search_with_no_candidates(client, auth):
    assert client.get("/api/internships/search?q=python", headers=auth()).json() == []


def test_search_embedding_failure_is_503(client, auth, seeded, monkeypatch):
    def boom(q):
        raise embeddings.EmbeddingError("down")

    monkeypatch.setattr(internship_service, "embed_query", boom)
    assert client.get("/api/internships/search?q=python", headers=auth()).status_code == 503


# ---------- API: user-added internships ----------

PAYLOAD = {
    "title": "Python Intern",
    "company": "Acme Robotics",
    "description": "Work on Python automation scripts for factory robots and write SQL reports.",
    "work_mode": "hybrid",
    "skills": [{"name": "python", "importance": "required"}, {"name": "Docker", "importance": "preferred"}],
}


def test_create_user_internship_private_to_creator(client, auth, seeded):
    a, b = auth("a@example.com"), auth("b@example.com")
    r = client.post("/api/internships", headers=a, json=PAYLOAD)
    assert r.status_code == 201
    item = r.json()
    assert item["source"] == "user"
    assert [(s["name"], s["importance"]) for s in item["skills"]] == [("Python", "required"), ("Docker", "preferred")]

    assert client.get(f"/api/internships/{item['id']}", headers=a).status_code == 200
    assert client.get(f"/api/internships/{item['id']}", headers=b).status_code == 404
    assert client.get("/api/internships?source=user", headers=b).json()["total"] == 0
    # it is searchable by its owner only
    mine = client.get("/api/internships/search?q=factory robots automation", headers=a).json()
    theirs = client.get("/api/internships/search?q=factory robots automation", headers=b).json()
    assert item["id"] in [i["id"] for i in mine]
    assert item["id"] not in [i["id"] for i in theirs]


def test_create_validates(client, auth):
    h = auth()
    assert client.post("/api/internships", headers=h, json={**PAYLOAD, "description": "short"}).status_code == 422
    assert client.post("/api/internships", headers=h, json={**PAYLOAD, "apply_url": "javascript:alert(1)"}).status_code == 422
    assert client.post("/api/internships", headers=h, json={**PAYLOAD, "work_mode": "moon"}).status_code == 422


def test_delete_own_but_not_sample(client, auth, seeded):
    a, b = auth("a@example.com"), auth("b@example.com")
    item = client.post("/api/internships", headers=a, json=PAYLOAD).json()
    assert client.delete(f"/api/internships/{item['id']}", headers=b).status_code == 404
    assert client.delete(f"/api/internships/{item['id']}", headers=a).status_code == 204
    assert client.get(f"/api/internships/{item['id']}", headers=a).status_code == 404
    sample = client.get("/api/internships", headers=a).json()["items"][0]
    assert client.delete(f"/api/internships/{sample['id']}", headers=a).status_code == 400


# ---------- JD extraction ----------

def test_extract_grounds_llm_output(client, auth, monkeypatch):
    def fake(prompt, schema, **kw):
        return JDExtraction(
            title="Python Intern", company="Acme Robotics", location="Pune", work_mode="Hybrid",
            stipend="15000/month", duration="3 months", apply_url="https://example.com/jobs/42",
            required_skills=["Python", "SQL", "Haskell"],  # Haskell is invented
            preferred_skills=["Docker", "Kubernetes"],  # Kubernetes is invented
            eligibility_text="Open to final year students from IIT Madras only",  # invented
        )

    monkeypatch.setattr(jd_parser, "generate_structured", fake)
    r = client.post("/api/internships/extract", headers=auth(), json={"text": JD})
    assert r.status_code == 200
    d = r.json()
    assert d["method"] == "llm"
    assert d["work_mode"] == "hybrid"
    assert d["company"] == "Acme Robotics" and d["stipend"] == "15000/month"
    names = {(s["name"], s["importance"]) for s in d["skills"]}
    assert names == {("Python", "required"), ("SQL", "required"), ("Docker", "preferred")}
    assert d["eligibility_text"] == ""
    assert any("Haskell" in w for w in d["warnings"]) and any("Kubernetes" in w for w in d["warnings"])
    assert d["description"] == JD


def test_extract_removes_invented_details(monkeypatch):
    monkeypatch.setattr(
        jd_parser, "generate_structured",
        lambda *a, **k: JDExtraction(company="Globex", stipend="99999/month", location="Paris", apply_url="https://evil.test/x"),
    )
    ex, method, warnings = jd_parser.extract_jd(JD)
    assert (ex.company, ex.stipend, ex.location, ex.apply_url) == ("", "", "", "")
    assert len(warnings) == 4


def test_extract_falls_back_when_llm_fails(client, auth, monkeypatch):
    def fail(*a, **k):
        raise LLMError("down")

    monkeypatch.setattr(jd_parser, "generate_structured", fail)
    d = client.post("/api/internships/extract", headers=auth(), json={"text": JD}).json()
    assert d["method"] == "heuristic"
    assert {"Python", "SQL", "Docker"} <= {s["name"] for s in d["skills"]}
    assert d["title"] == "" and any("unavailable" in w for w in d["warnings"])


def test_extract_saves_nothing(client, auth, monkeypatch):
    monkeypatch.setattr(jd_parser, "generate_structured", lambda *a, **k: JDExtraction())
    h = auth()
    client.post("/api/internships/extract", headers=h, json={"text": JD})
    assert client.get("/api/internships", headers=h).json()["total"] == 0


def test_extract_rejects_tiny_input(client, auth):
    assert client.post("/api/internships/extract", headers=auth(), json={"text": "hi"}).status_code == 422


# ---------- real embedding model (downloads ~130 MB on first run) ----------

@pytest.mark.integration
def test_real_embedding_model_shape_and_similarity(monkeypatch):
    from importlib import reload

    reload(embeddings)  # undo the autouse fake
    a, b, c = embeddings.embed_documents(
        ["Python backend developer building REST APIs", "Server-side engineer writing Python web services", "Pastry chef baking sourdough bread"]
    )
    assert len(a) == embeddings.DIM

    def cos(x, y):
        return sum(p * q for p, q in zip(x, y)) / (math.sqrt(sum(p * p for p in x)) * math.sqrt(sum(q * q for q in y)))

    assert cos(a, b) > cos(a, c)


@pytest.mark.integration
def test_pgvector_search_on_real_database():
    """Guards the Postgres-only `<=>` path, which SQLite unit tests cannot exercise."""
    from importlib import reload

    reload(embeddings)
    from app.db import SessionLocal
    from app.rag import retriever

    with SessionLocal() as db:
        internship_service.seed_samples(db)  # idempotent
        hits = retriever.search(db, embeddings.embed_query("chatbot over documents using LLMs"), corpus="internship", limit=3)
    assert hits and hits[0].title.startswith("Generative AI Intern")
    assert hits[0].score >= hits[-1].score
