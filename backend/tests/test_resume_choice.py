"""Several resumes per student: friendly names, and choosing which one a feature uses."""

import copy
import uuid

import pytest
from sqlalchemy import select

from app.models import Resume, ResumeExtraction, User
from tests import test_interview_api as iv
from tests import test_tailoring_api as tl
from tests.conftest import bearer
from tests.test_interview_api import llm as interview_llm  # noqa: F401  (fixtures)
from tests.test_tailoring_api import auth, llm as tailoring_llm, seeded  # noqa: F401

DATA_A = copy.deepcopy(tl.RESUME_DATA)
DATA_B = copy.deepcopy(tl.RESUME_DATA)
DATA_B["experience"] = [{"title": "Data Intern", "organization": "Zephyr Analytics", "start": "Jan 2025", "end": "Mar 2025",
                         "location": "", "bullets": ["Built dashboards in Tableau for the sales team"]}]
DATA_B["projects"] = [{"name": "Churn Predictor", "technologies": ["Python"], "description": "Predicts customer churn.", "link": ""}]


def add_resume(db_session_factory, email, data, name, active=False):
    with db_session_factory() as db:
        user = db.scalar(select(User).where(User.email == email))
        r = Resume(user_id=user.id, original_filename=name, stored_filename=f"{uuid.uuid4().hex}.pdf", content_type="application/pdf",
                   size_bytes=1, raw_text="x", is_active=active, extraction_status="complete")
        db.add(r)
        db.flush()
        db.add(ResumeExtraction(resume_id=r.id, data=copy.deepcopy(data), method="llm", warnings=[]))
        db.commit()
        return str(r.id)


# ---------- friendly names ----------

def test_rename_set_and_clear(client, auth, db_session_factory):
    h = auth()
    rid = add_resume(db_session_factory, "a@example.com", DATA_A, "cv1.pdf", active=True)
    r = client.patch(f"/api/resumes/{rid}", headers=h, json={"label": "  Backend resume "})
    assert r.status_code == 200 and r.json()["label"] == "Backend resume"
    assert client.get("/api/resumes", headers=h).json()[0]["label"] == "Backend resume"
    assert client.patch(f"/api/resumes/{rid}", headers=h, json={"label": ""}).json()["label"] is None


def test_label_validation_and_ownership(client, auth, db_session_factory):
    h = auth()
    other = auth("b@example.com")
    rid = add_resume(db_session_factory, "a@example.com", DATA_A, "cv1.pdf", active=True)
    assert client.patch(f"/api/resumes/{rid}", headers=h, json={"label": "x" * 101}).status_code == 422
    assert client.patch(f"/api/resumes/{rid}", headers=other, json={"label": "mine now"}).status_code == 404
    assert client.patch(f"/api/resumes/{uuid.uuid4()}", headers=h, json={"label": "x"}).status_code == 404


def test_application_shows_the_label(client, auth, db_session_factory):
    h = auth()
    rid = add_resume(db_session_factory, "a@example.com", DATA_A, "cv1.pdf", active=True)
    client.patch(f"/api/resumes/{rid}", headers=h, json={"label": "Backend resume"})
    created = client.post("/api/applications", headers=h, json={"company": "Acme", "role": "Dev", "resume_id": rid})
    assert created.status_code == 201
    listing = client.get("/api/applications", headers=h).json()["items"][0]
    assert "Backend resume" in str(listing.get("resume_name") or listing)


# ---------- choosing a resume for a feature ----------

def test_tailoring_uses_the_chosen_resume_not_just_the_active_one(client, auth, seeded, db_session_factory, tailoring_llm):
    h = auth()
    for n in ("Python", "SQL"):
        client.post("/api/skills", headers=h, json={"name": n})
    add_resume(db_session_factory, "a@example.com", DATA_A, "backend.pdf", active=True)
    other = add_resume(db_session_factory, "a@example.com", DATA_B, "data.pdf")
    item = tl.posting(client, h)

    default = client.post("/api/tailoring/generate", headers=h, json={"internship_id": item["id"], "kind": "cover_letter"})
    assert default.status_code == 200 and "Acme Labs" in tailoring_llm.prompts[-1]

    chosen = client.post("/api/tailoring/generate", headers=h, json={"internship_id": item["id"], "kind": "cover_letter", "resume_id": other})
    assert chosen.status_code == 200
    assert "Zephyr Analytics" in tailoring_llm.prompts[-1] and "Acme Labs" not in tailoring_llm.prompts[-1]


def test_tailoring_rejects_a_resume_that_is_not_yours(client, auth, seeded, db_session_factory, tailoring_llm):
    h = auth()
    auth("b@example.com")
    for n in ("Python", "SQL"):
        client.post("/api/skills", headers=h, json={"name": n})
    add_resume(db_session_factory, "a@example.com", DATA_A, "mine.pdf", active=True)
    theirs = add_resume(db_session_factory, "b@example.com", DATA_B, "theirs.pdf", active=True)
    item = tl.posting(client, h)
    r = client.post("/api/tailoring/generate", headers=h, json={"internship_id": item["id"], "kind": "cover_letter", "resume_id": theirs})
    assert r.status_code == 400
    assert not any("Zephyr" in p for p in tailoring_llm.prompts)


def test_interview_questions_use_the_chosen_resume(client, auth, interview_llm, db_session_factory):
    h = auth()
    add_resume(db_session_factory, "a@example.com", DATA_A, "backend.pdf", active=True)
    other = add_resume(db_session_factory, "a@example.com", DATA_B, "data.pdf")
    iv.start(client, h, role="Data analyst", count=5)
    assert "Budget Tracker" in interview_llm.prompts[-1]
    r = iv.start(client, h, role="Data analyst", count=5, resume_id=other)
    assert r.status_code == 201 and "Churn Predictor" in interview_llm.prompts[-1] and "Budget Tracker" not in interview_llm.prompts[-1]


def test_interview_rejects_an_unknown_resume(client, auth, interview_llm):
    r = iv.start(client, auth(), role="Data analyst", count=5, resume_id=str(uuid.uuid4()))
    assert r.status_code == 400
