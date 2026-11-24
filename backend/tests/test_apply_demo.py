"""Demo 'Apply': records an application as Applied. Nothing is sent to any company."""

import uuid
from datetime import date

from tests.test_applications import auth, fakes, first_internship, seeded  # noqa: F401  (fixtures)
from tests.test_resume_choice import DATA_A, add_resume

APPLY = "/api/applications/apply"


def test_requires_auth(client):
    assert client.post(APPLY, json={"internship_id": str(uuid.uuid4())}).status_code == 401


def test_apply_creates_an_applied_application_with_a_demo_note(client, auth, seeded):
    h = auth()
    item = first_internship(client, h)
    r = client.post(APPLY, headers=h, json={"internship_id": item["id"], "notes": "  Keen on this one  "})
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "applied" and body["applied_on"] == date.today().isoformat()
    assert (body["company"], body["role"]) == (item["company"], item["title"])
    assert body["notes"] == "Keen on this one"
    assert len(body["events"]) == 1 and body["events"][0]["to_status"] == "applied"
    assert "nothing was sent" in body["events"][0]["note"].lower()
    listing = client.get("/api/applications", headers=h).json()
    assert listing["counts"]["applied"] == 1 and listing["items"][0]["internship_id"] == item["id"]


def test_apply_moves_a_saved_application_forward(client, auth, seeded):
    h = auth()
    item = first_internship(client, h)
    saved = client.post("/api/applications", headers=h, json={"internship_id": item["id"]}).json()
    assert saved["status"] == "saved"
    r = client.post(APPLY, headers=h, json={"internship_id": item["id"]})
    assert r.status_code == 201
    body = r.json()
    assert body["id"] == saved["id"] and body["status"] == "applied" and body["applied_on"] == date.today().isoformat()
    assert [e["to_status"] for e in body["events"]] == ["saved", "applied"]
    assert client.get("/api/applications", headers=h).json()["counts"]["applied"] == 1  # still one application


def test_applying_twice_is_a_conflict(client, auth, seeded):
    h = auth()
    item = first_internship(client, h)
    assert client.post(APPLY, headers=h, json={"internship_id": item["id"]}).status_code == 201
    again = client.post(APPLY, headers=h, json={"internship_id": item["id"]})
    assert again.status_code == 409 and "already applied" in again.json()["detail"]


def test_a_later_stage_is_not_reset_by_applying(client, auth, seeded):
    h = auth()
    item = first_internship(client, h)
    app = client.post("/api/applications", headers=h, json={"internship_id": item["id"], "status": "interview"}).json()
    assert client.post(APPLY, headers=h, json={"internship_id": item["id"]}).status_code == 409
    assert client.get(f"/api/applications/{app['id']}", headers=h).json()["status"] == "interview"


def test_active_resume_is_used_by_default_and_a_chosen_one_wins(client, auth, seeded, db_session_factory):
    h = auth()
    add_resume(db_session_factory, "a@example.com", DATA_A, "active.pdf", active=True)
    other = add_resume(db_session_factory, "a@example.com", DATA_A, "other.pdf")
    items = client.get("/api/internships?limit=2", headers=h).json()["items"]
    first = client.post(APPLY, headers=h, json={"internship_id": items[0]["id"]}).json()
    assert first["resume_name"] == "active.pdf"
    second = client.post(APPLY, headers=h, json={"internship_id": items[1]["id"], "resume_id": other}).json()
    assert second["resume_name"] == "other.pdf"


def test_a_resume_that_is_not_yours_is_rejected(client, auth, seeded, db_session_factory):
    h = auth()
    auth("b@example.com")
    theirs = add_resume(db_session_factory, "b@example.com", DATA_A, "theirs.pdf", active=True)
    item = first_internship(client, h)
    r = client.post(APPLY, headers=h, json={"internship_id": item["id"], "resume_id": theirs})
    assert r.status_code == 400
    assert client.get("/api/applications", headers=h).json()["items"] == []


def test_unknown_posting_and_private_postings_of_others(client, auth, seeded):
    h = auth()
    other = auth("b@example.com")
    assert client.post(APPLY, headers=h, json={"internship_id": str(uuid.uuid4())}).status_code == 400
    mine = client.post("/api/internships", headers=other, json={
        "title": "Secret Role", "company": "Hidden Co", "description": "A private posting for testing the visibility rules here.",
        "skills": [{"name": "Python", "importance": "required"}],
    })
    assert mine.status_code == 201
    assert client.post(APPLY, headers=h, json={"internship_id": mine.json()["id"]}).status_code == 400  # not visible to others


def test_notes_are_length_limited(client, auth, seeded):
    h = auth()
    item = first_internship(client, h)
    assert client.post(APPLY, headers=h, json={"internship_id": item["id"], "notes": "x" * 1001}).status_code == 422
