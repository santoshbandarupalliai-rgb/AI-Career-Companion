import copy

import pytest
from sqlalchemy import select

from app.llm import LLMError
from app.models import Resume, ResumeExtraction, User
from app.schemas.tailoring import CoverLetterLLM, ResumeDraftLLM, _BulletsFor
from app.services import internship_service, tailoring_service
from tests.conftest import bearer

RESUME_DATA = {
    "personal": {"name": "Test Student"},
    "summary": "",
    "skills": {"technical": ["Python", "SQL", "Docker"], "tools": ["Git"], "soft": []},
    "education": [],
    "experience": [{
        "title": "Software Intern", "organization": "Acme Labs", "start": "Jun 2025", "end": "Aug 2025", "location": "",
        "bullets": ["Built a Python script that cleaned 5000 records", "Wrote SQL reports for the sales team"],
    }],
    "projects": [{"name": "Budget Tracker", "technologies": ["Python", "SQLite"], "description": "A command line tool to track monthly spending.", "link": ""}],
    "certifications": [{"name": "Python Basics", "issuer": "", "year": ""}],
    "achievements": [],
}


@pytest.fixture()
def seeded(db_session_factory, monkeypatch):
    from app.rag import embeddings
    monkeypatch.setattr(embeddings, "embed_documents", lambda texts: [[0.1] * embeddings.DIM for _ in texts])
    with db_session_factory() as db:
        internship_service.seed_samples(db)


@pytest.fixture()
def auth(register):
    def _auth(email="a@example.com"):
        return bearer(register(email=email).json()["access_token"])

    return _auth


def give_resume(db_session_factory, email="a@example.com", data=RESUME_DATA):
    with db_session_factory() as db:
        user = db.scalar(select(User).where(User.email == email))
        r = Resume(user_id=user.id, original_filename="cv.pdf", stored_filename="x.pdf", content_type="application/pdf",
                   size_bytes=1, raw_text="x", is_active=True, extraction_status="complete")
        db.add(r)
        db.flush()
        db.add(ResumeExtraction(resume_id=r.id, data=copy.deepcopy(data), method="llm", warnings=[]))
        db.commit()


def setup_student(client, h, db_session_factory, email="a@example.com"):
    for n in ("Python", "SQL"):
        client.post("/api/skills", headers=h, json={"name": n})
    give_resume(db_session_factory, email)


def posting(client, h):
    items = client.get("/api/internships?limit=100", headers=h).json()["items"]
    return next(i for i in items if i["title"].startswith("Backend Developer Intern (Python)"))


class FakeLLM:
    def __init__(self):
        self.prompts = []
        self.fail = False
        self.resume = ResumeDraftLLM(
            summary="Computer science student with Python and SQL skills.",
            skills=["Python", "SQL", "Haskell", "Docker"],  # Haskell invented, Docker unverified
            experience=[
                _BulletsFor(source_index=0, bullets=[
                    "Built a Python script that cleaned 5000 records.",
                    "Increased throughput by 300% using Kubernetes at Globex.",
                ]),
                _BulletsFor(source_index=7, bullets=["Ghost entry."]),  # does not exist
            ],
            projects=[_BulletsFor(source_index=0, bullets=["Created a command line Python tool to track monthly spending."])],
        )
        self.letter = CoverLetterLLM(paragraphs=[
            "I am excited to apply for the Backend Developer Intern role at Brightlane Analytics.",
            "At Acme Labs I built a Python script that cleaned 5000 records. I also grew sales by 90%.",
            "I would welcome the chance to discuss how I can contribute.",
        ])

    def structured(self, prompt, schema, **kw):
        if self.fail:
            raise LLMError("The AI service is rate-limited right now. Please try again in a minute.")
        self.prompts.append(prompt)
        return self.resume if schema is ResumeDraftLLM else self.letter


@pytest.fixture()
def llm(monkeypatch):
    f = FakeLLM()
    monkeypatch.setattr(tailoring_service, "generate_structured", f.structured)
    return f


def generate(client, h, internship_id, kind):
    return client.post("/api/tailoring/generate", headers=h, json={"internship_id": internship_id, "kind": kind})


# ---------- resume draft ----------

def test_requires_auth(client):
    assert client.get("/api/tailoring/documents").status_code == 401
    assert client.post("/api/tailoring/generate", json={}).status_code == 401


def test_resume_draft_is_guarded(client, auth, seeded, db_session_factory, llm):
    h = auth()
    setup_student(client, h, db_session_factory)
    p = posting(client, h)
    r = generate(client, h, p["id"], "resume")
    assert r.status_code == 200, r.text
    d = r.json()
    c = d["content"]
    # skills list: verified only
    assert c["skills"] == ["Python", "SQL"]
    removed = {f["text"] for f in d["flags"] if f["severity"] == "removed"}
    assert removed == {"Haskell", "Docker"}
    # entry details come from the resume, and the nonexistent entry was dropped
    assert [(e["title"], e["organization"], e["start"], e["end"]) for e in c["experience"]] == [("Software Intern", "Acme Labs", "Jun 2025", "Aug 2025")]
    assert any("does not exist" in n for n in d["notes"])
    assert [e["title"] for e in c["projects"]] == ["Budget Tracker"] and c["projects"][0]["technologies"] == ["Python", "SQLite"]
    # the invented bullet is flagged (figure, skill, name) while the faithful bullet is not
    bad = {(f["where"], f["kind"], f["text"]) for f in d["flags"] if f["severity"] == "warning"}
    assert ("experience.0.bullet.1", "number", "300%") in bad
    assert ("experience.0.bullet.1", "skill", "Kubernetes") in bad
    assert ("experience.0.bullet.1", "name", "Globex") in bad
    assert not any(w.startswith("experience.0.bullet.0") for w, _, _ in bad)
    assert not any(w.startswith("projects.0") for w, _, _ in bad)
    assert "Experience: Software Intern at Acme Labs" in d["facts_used"]
    assert c["header"]["name"] == "Test Student" and c["education"] == []
    # prompt only carries real material
    assert "VERIFIED SKILLS: Python, SQL" in llm.prompts[0] and "Docker" not in llm.prompts[0].split("VERIFIED SKILLS")[1].split("\n")[0]


def test_generate_saves_nothing(client, auth, seeded, db_session_factory, llm):
    h = auth()
    setup_student(client, h, db_session_factory)
    generate(client, h, posting(client, h)["id"], "resume")
    assert client.get("/api/tailoring/documents", headers=h).json() == []


def test_needs_real_material(client, auth, seeded, llm):
    h = auth()
    r = generate(client, h, posting(client, h)["id"], "resume")
    assert r.status_code == 400 and "Nothing is invented" in r.json()["detail"]
    assert llm.prompts == []  # no model call without material


def test_llm_failure_gives_503_with_message(client, auth, seeded, db_session_factory, llm):
    h = auth()
    setup_student(client, h, db_session_factory)
    llm.fail = True
    r = generate(client, h, posting(client, h)["id"], "resume")
    assert r.status_code == 503 and "rate-limited" in r.json()["detail"]


def test_cannot_tailor_to_someone_elses_private_posting(client, auth, seeded, db_session_factory, llm):
    a, b = auth("a@example.com"), auth("b@example.com")
    setup_student(client, b, db_session_factory, "b@example.com")
    mine = client.post("/api/internships", headers=a, json={"title": "Private", "company": "Hidden Co", "description": "A private posting for its creator only."}).json()
    assert generate(client, b, mine["id"], "resume").status_code == 404


# ---------- cover letter ----------

def test_cover_letter_flags_the_exact_sentence_and_allows_posting_names(client, auth, seeded, db_session_factory, llm):
    h = auth()
    setup_student(client, h, db_session_factory)
    d = generate(client, h, posting(client, h)["id"], "cover_letter").json()
    assert d["content"]["paragraphs"] and d["content"]["name"] == "Test Student"
    assert d["content"]["greeting"] == "Dear Hiring Manager,"
    where = {f["where"] for f in d["flags"]}
    assert where == {"cover_letter.p2.s2"}  # "grew sales by 90%"; Brightlane/Acme mentions are fine
    assert {f["kind"] for f in d["flags"]} == {"number"}


# ---------- approval and saving ----------

def draft(client, h, internship_id, kind="resume"):
    return generate(client, h, internship_id, kind).json()


def test_saving_flagged_draft_needs_acknowledgement(client, auth, seeded, db_session_factory, llm):
    h = auth()
    setup_student(client, h, db_session_factory)
    p = posting(client, h)
    d = draft(client, h, p["id"])
    body = {"kind": "resume", "internship_id": p["id"], "content": d["content"]}
    r = client.post("/api/tailoring/documents", headers=h, json=body)
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["flags"] and "confirm" in detail["message"].lower()
    ok = client.post("/api/tailoring/documents", headers=h, json={**body, "acknowledge_flags": True})
    assert ok.status_code == 201
    saved = ok.json()
    assert saved["flagged"] and saved["title"] == "Resume for Backend Developer Intern (Python) at Brightlane Analytics"
    assert client.get("/api/tailoring/documents", headers=h).json()[0]["flagged_count"] == len(saved["flagged"])


def test_editing_out_the_problems_lets_it_save_without_acknowledgement(client, auth, seeded, db_session_factory, llm):
    h = auth()
    setup_student(client, h, db_session_factory)
    p = posting(client, h)
    c = draft(client, h, p["id"])["content"]
    c["experience"][0]["bullets"] = ["Built a Python script that cleaned 5000 records."]
    r = client.post("/api/tailoring/documents", headers=h, json={"kind": "resume", "internship_id": p["id"], "content": c})
    assert r.status_code == 201 and r.json()["flagged"] == []


def test_saving_rechecks_what_the_student_submits(client, auth, seeded, db_session_factory, llm):
    h = auth()
    setup_student(client, h, db_session_factory)
    p = posting(client, h)
    c = draft(client, h, p["id"])["content"]
    c["experience"][0]["bullets"] = ["Built a Python script that cleaned 5000 records."]
    c["skills"] = ["Python", "Docker", "Kubernetes"]  # edited in unverified skills
    c["experience"][0]["title"] = "CEO"  # tampered entry details
    c["experience"][0]["organization"] = "Google"
    c["header"]["name"] = "Someone Else"
    r = client.post("/api/tailoring/documents", headers=h, json={"kind": "resume", "internship_id": p["id"], "content": c, "acknowledge_flags": True})
    assert r.status_code == 201
    saved = r.json()["content"]
    assert saved["skills"] == ["Python"]
    assert (saved["experience"][0]["title"], saved["experience"][0]["organization"]) == ("Software Intern", "Acme Labs")
    assert saved["header"]["name"] == "Test Student"
    assert {f["text"] for f in r.json()["flagged"] if f["severity"] == "removed"} == {"Docker", "Kubernetes"}


def test_saving_rejects_entries_not_in_the_resume(client, auth, seeded, db_session_factory, llm):
    h = auth()
    setup_student(client, h, db_session_factory)
    p = posting(client, h)
    c = draft(client, h, p["id"])["content"]
    c["experience"][0]["source_index"] = 5
    assert client.post("/api/tailoring/documents", headers=h, json={"kind": "resume", "internship_id": p["id"], "content": c, "acknowledge_flags": True}).status_code == 400
    assert client.post("/api/tailoring/documents", headers=h, json={"kind": "resume", "content": {"nonsense": 1}}).status_code == 400


def test_cover_letter_save_and_docx_download(client, auth, seeded, db_session_factory, llm):
    h = auth()
    setup_student(client, h, db_session_factory)
    p = posting(client, h)
    d = draft(client, h, p["id"], "cover_letter")
    assert client.post("/api/tailoring/documents", headers=h, json={"kind": "cover_letter", "internship_id": p["id"], "content": d["content"]}).status_code == 409
    saved = client.post("/api/tailoring/documents", headers=h, json={"kind": "cover_letter", "internship_id": p["id"], "content": d["content"], "acknowledge_flags": True}).json()
    dl = client.get(f"/api/tailoring/documents/{saved['id']}/download", headers=h)
    assert dl.status_code == 200 and dl.content[:2] == b"PK" and "wordprocessingml" in dl.headers["content-type"]
    assert ".docx" in dl.headers["content-disposition"]
    from docx import Document
    import io
    text = "\n".join(par.text for par in Document(io.BytesIO(dl.content)).paragraphs)
    assert "Dear Hiring Manager," in text and "Test Student" in text and "Acme Labs" in text


def test_resume_docx_download(client, auth, seeded, db_session_factory, llm):
    h = auth()
    setup_student(client, h, db_session_factory)
    p = posting(client, h)
    c = draft(client, h, p["id"])["content"]
    saved = client.post("/api/tailoring/documents", headers=h, json={"kind": "resume", "internship_id": p["id"], "content": c, "acknowledge_flags": True}).json()
    dl = client.get(f"/api/tailoring/documents/{saved['id']}/download", headers=h)
    from docx import Document
    import io
    text = "\n".join(par.text for par in Document(io.BytesIO(dl.content)).paragraphs)
    assert "Software Intern, Acme Labs" in text and "Budget Tracker" in text and "Python, SQL" in text


def test_documents_are_private_to_their_owner(client, auth, seeded, db_session_factory, llm):
    a, b = auth("a@example.com"), auth("b@example.com")
    setup_student(client, a, db_session_factory, "a@example.com")
    p = posting(client, a)
    c = draft(client, a, p["id"], "cover_letter")["content"]
    doc = client.post("/api/tailoring/documents", headers=a, json={"kind": "cover_letter", "internship_id": p["id"], "content": c, "acknowledge_flags": True}).json()
    for method, url in (("get", f"/api/tailoring/documents/{doc['id']}"), ("get", f"/api/tailoring/documents/{doc['id']}/download"), ("delete", f"/api/tailoring/documents/{doc['id']}")):
        assert getattr(client, method)(url, headers=b).status_code == 404
    assert client.get("/api/tailoring/documents", headers=b).json() == []
    assert client.delete(f"/api/tailoring/documents/{doc['id']}", headers=a).status_code == 204
    assert client.get("/api/tailoring/documents", headers=a).json() == []
