import pytest

from app.config import get_settings
from app.services import resume_parser
from app.services.resume_parser import ResumeData
from tests.conftest import bearer
from tests.factories import make_docx, make_pdf

PDF_MIME = "application/pdf"


@pytest.fixture(autouse=True)
def tmp_uploads(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "upload_dir", tmp_path)
    return tmp_path


@pytest.fixture()
def fake_llm(monkeypatch):
    """Deterministic 'LLM' output: grounded skills plus one invented skill."""

    def _fake(prompt, schema, **kw):
        d = ResumeData()
        d.personal.name = "Asha Verma"
        d.personal.email = "asha.verma@example.com"
        d.skills.technical = ["Python", "JavaScript", "SQL", "FastAPI", "React", "Haskell"]
        d.skills.tools = ["Git", "Docker"]
        return d

    monkeypatch.setattr(resume_parser, "generate_structured", _fake)


@pytest.fixture()
def auth(register):
    def _auth(email="student@example.com"):
        return bearer(register(email=email).json()["access_token"])

    return _auth


def upload(client, headers, data=None, name="cv.pdf", mime=PDF_MIME):
    return client.post("/api/resumes", headers=headers, files={"file": (name, data or make_pdf(), mime)})


# ---------- profile ----------

def test_new_profile_is_empty_not_fabricated(client, auth):
    r = client.get("/api/profile", headers=auth())
    assert r.status_code == 200
    body = r.json()
    for field in ("college", "degree", "graduation_year", "target_role", "location", "bio", "cgpa"):
        assert body[field] is None
    assert body["full_name"] == "Test Student"


def test_profile_update_validates_and_normalizes(client, auth):
    h = auth()
    r = client.put(
        "/api/profile",
        headers=h,
        json={"college": "  Example   Institute ", "cgpa": 8.4, "graduation_year": 2026, "github_url": "github.com/asha"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["college"] == "Example Institute"
    assert r.json()["github_url"] == "https://github.com/asha"
    assert client.put("/api/profile", headers=h, json={"cgpa": 11}).status_code == 422
    assert client.put("/api/profile", headers=h, json={"linkedin_url": "not a url"}).status_code == 422
    # Empty strings clear fields.
    r = client.put("/api/profile", headers=h, json={"college": "", "cgpa": ""})
    assert r.json()["college"] is None and r.json()["cgpa"] is None


# ---------- resumes ----------

def test_upload_pdf_extracts_and_records_skills_as_extracted(client, auth, fake_llm):
    h = auth()
    r = upload(client, h)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["is_active"] and body["extraction_status"] == "complete"
    assert body["extraction"]["method"] == "llm"
    assert "Haskell" not in body["extraction"]["data"]["skills"]["technical"]
    assert any("Haskell" in w for w in body["extraction"]["warnings"])

    skills = client.get("/api/skills", headers=h).json()
    names = {s["name"] for s in skills["extracted"]}
    assert {"Python", "JavaScript", "FastAPI", "Git", "Docker"} <= names
    assert skills["verified"] == []  # nothing is verified until the student says so
    assert all(s["evidence"] for s in skills["extracted"])


def test_upload_docx(client, auth, fake_llm):
    mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    r = upload(client, auth(), make_docx(), "cv.docx", mime)
    assert r.status_code == 201
    assert "MongoDB" in r.json()["raw_text"]


def test_upload_rejections(client, auth, fake_llm):
    h = auth()
    assert upload(client, h, b"hello", "cv.txt", "text/plain").status_code == 400
    assert upload(client, h, b"x" * 200, "cv.pdf").status_code == 400
    big = b"%PDF-" + b"0" * (5 * 1024 * 1024 + 10)
    assert upload(client, h, big, "big.pdf").status_code in (400, 413)
    assert client.get("/api/resumes", headers=h).json() == []


def test_newest_upload_is_active_and_activate_switches(client, auth, fake_llm):
    h = auth()
    first = upload(client, h).json()
    second = upload(client, h).json()
    listing = {r["id"]: r["is_active"] for r in client.get("/api/resumes", headers=h).json()}
    assert listing == {first["id"]: False, second["id"]: True}
    client.post(f"/api/resumes/{first['id']}/activate", headers=h)
    listing = {r["id"]: r["is_active"] for r in client.get("/api/resumes", headers=h).json()}
    assert listing == {first["id"]: True, second["id"]: False}


def test_download_and_delete(client, auth, fake_llm, tmp_uploads):
    h = auth()
    rid = upload(client, h).json()["id"]
    r = client.get(f"/api/resumes/{rid}/file", headers=h)
    assert r.status_code == 200 and r.content.startswith(b"%PDF-")
    assert client.delete(f"/api/resumes/{rid}", headers=h).status_code == 204
    assert client.get(f"/api/resumes/{rid}", headers=h).status_code == 404
    assert not any(tmp_uploads.rglob("*.pdf"))
    # Unverified skills from the deleted resume are gone too.
    assert client.get("/api/skills", headers=h).json()["extracted"] == []


def test_users_cannot_see_each_others_resumes(client, auth, fake_llm):
    alice, bob = auth("alice@example.com"), auth("bob@example.com")
    rid = upload(client, alice).json()["id"]
    assert client.get(f"/api/resumes/{rid}", headers=bob).status_code == 404
    assert client.get(f"/api/resumes/{rid}/file", headers=bob).status_code == 404
    assert client.delete(f"/api/resumes/{rid}", headers=bob).status_code == 404
    assert client.post(f"/api/resumes/{rid}/activate", headers=bob).status_code == 404
    assert client.get("/api/resumes", headers=bob).json() == []
    assert client.get("/api/skills", headers=bob).json()["extracted"] == []


def test_resume_endpoints_require_auth(client):
    assert client.get("/api/resumes").status_code == 401
    assert client.get("/api/profile").status_code == 401
    assert client.get("/api/skills").status_code == 401


# ---------- skills ----------

def _skill(skills, name):
    for group in skills.values():
        for s in group:
            if s["name"] == name:
                return s
    raise AssertionError(name)


def test_verify_reject_and_decisions_survive_reextraction(client, auth, fake_llm):
    h = auth()
    rid = upload(client, h).json()["id"]
    skills = client.get("/api/skills", headers=h).json()
    py, docker = _skill(skills, "Python"), _skill(skills, "Docker")

    assert client.patch(f"/api/skills/{py['id']}", headers=h, json={"status": "verified"}).status_code == 200
    assert client.patch(f"/api/skills/{docker['id']}", headers=h, json={"status": "rejected"}).status_code == 200

    client.post(f"/api/resumes/{rid}/reextract", headers=h)
    skills = client.get("/api/skills", headers=h).json()
    assert _skill(skills, "Python")["status"] == "verified"
    assert _skill(skills, "Docker")["status"] == "rejected"  # not resurrected


def test_bulk_verify_only_touches_own_extracted_skills(client, auth, fake_llm):
    alice, bob = auth("alice@example.com"), auth("bob@example.com")
    upload(client, alice)
    alice_ids = [s["id"] for s in client.get("/api/skills", headers=alice).json()["extracted"]]
    assert client.post("/api/skills/verify", headers=bob, json={"ids": alice_ids}).json() == {"verified": 0}
    assert client.post("/api/skills/verify", headers=alice, json={"ids": alice_ids}).json()["verified"] == len(alice_ids)


def test_manual_skill_add_is_verified_and_deduplicated(client, auth):
    h = auth()
    r = client.post("/api/skills", headers=h, json={"name": "reactjs"})
    assert r.status_code == 201 and r.json()["name"] == "React" and r.json()["status"] == "verified"
    client.post("/api/skills", headers=h, json={"name": "React.js"})
    assert len(client.get("/api/skills", headers=h).json()["verified"]) == 1
    sid = r.json()["id"]
    assert client.delete(f"/api/skills/{sid}", headers=h).status_code == 204


def test_resume_skill_cannot_be_deleted_only_rejected(client, auth, fake_llm):
    h = auth()
    upload(client, h)
    sid = client.get("/api/skills", headers=h).json()["extracted"][0]["id"]
    assert client.delete(f"/api/skills/{sid}", headers=h).status_code == 400


def test_other_users_skill_ids_are_not_found(client, auth, fake_llm):
    alice, bob = auth("alice@example.com"), auth("bob@example.com")
    upload(client, alice)
    sid = client.get("/api/skills", headers=alice).json()["extracted"][0]["id"]
    assert client.patch(f"/api/skills/{sid}", headers=bob, json={"status": "verified"}).status_code == 404
