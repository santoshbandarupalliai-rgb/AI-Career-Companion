import hashlib
import math
import re
from datetime import date

import pytest

from app.rag import embeddings
from app.services import internship_service
from tests.conftest import bearer

BASE = "/api/applications"


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


@pytest.fixture()
def seeded(db_session_factory):
    with db_session_factory() as db:
        internship_service.seed_samples(db)


@pytest.fixture()
def auth(register):
    def _auth(email="a@example.com"):
        return bearer(register(email=email).json()["access_token"])

    return _auth


def first_internship(client, h):
    return client.get("/api/internships?limit=1", headers=h).json()["items"][0]


def test_requires_auth(client):
    assert client.get(BASE).status_code == 401
    assert client.post(BASE, json={"company": "X", "role": "Y"}).status_code == 401


def test_track_posting_copies_company_and_role(client, auth, seeded):
    h = auth()
    item = first_internship(client, h)
    r = client.post(BASE, headers=h, json={"internship_id": item["id"], "company": "Fake Co", "role": "CEO"})
    assert r.status_code == 201
    body = r.json()
    assert (body["company"], body["role"]) == (item["company"], item["title"])  # never the typed values
    assert body["status"] == "saved" and body["applied_on"] is None
    assert body["internship_source"] == "sample"
    assert [(e["from_status"], e["to_status"]) for e in body["events"]] == [(None, "saved")]

    dup = client.post(BASE, headers=h, json={"internship_id": item["id"]})
    assert dup.status_code == 409


def test_external_application_needs_company_and_role(client, auth):
    h = auth()
    assert client.post(BASE, headers=h, json={"company": "Acme Demo"}).status_code == 422
    assert client.post(BASE, headers=h, json={"company": "  ", "role": "Intern"}).status_code == 422
    r = client.post(BASE, headers=h, json={"company": " Acme   Demo ", "role": "Data Intern", "status": "applied"})
    assert r.status_code == 201
    assert r.json()["company"] == "Acme Demo"
    assert r.json()["applied_on"] == date.today().isoformat()  # status past 'saved' implies it was sent


def test_unknown_or_foreign_internship_is_rejected(client, auth):
    h = auth()
    other = auth("b@example.com")
    posting = client.post("/api/internships", headers=other, json={
        "title": "Private Intern", "company": "Other Demo Co", "description": "A private posting " * 5,
        "skills": [],
    })
    assert posting.status_code == 201, posting.text
    r = client.post(BASE, headers=h, json={"internship_id": posting.json()["id"]})
    assert r.status_code == 400


def test_status_changes_are_logged(client, auth):
    h = auth()
    app_id = client.post(BASE, headers=h, json={"company": "Acme Demo", "role": "Intern"}).json()["id"]
    r = client.post(f"{BASE}/{app_id}/status", headers=h, json={"status": "applied", "note": "via portal"})
    assert r.status_code == 200
    assert r.json()["applied_on"] == date.today().isoformat()
    r = client.post(f"{BASE}/{app_id}/status", headers=h, json={"status": "interview"})
    events = r.json()["events"]
    assert [(e["from_status"], e["to_status"]) for e in events] == [(None, "saved"), ("saved", "applied"), ("applied", "interview")]
    assert events[1]["note"] == "via portal"

    same = client.post(f"{BASE}/{app_id}/status", headers=h, json={"status": "interview"})
    assert same.status_code == 400
    bad = client.post(f"{BASE}/{app_id}/status", headers=h, json={"status": "hired"})
    assert bad.status_code == 422


def test_update_fields_and_linked_posting_is_protected(client, auth, seeded):
    h = auth()
    ext = client.post(BASE, headers=h, json={"company": "Acme Demo", "role": "Intern"}).json()["id"]
    r = client.patch(f"{BASE}/{ext}", headers=h, json={"role": "ML Intern", "deadline": "2027-01-15", "notes": " follow up "})
    assert r.status_code == 200
    assert (r.json()["role"], r.json()["deadline"], r.json()["notes"]) == ("ML Intern", "2027-01-15", "follow up")
    assert client.patch(f"{BASE}/{ext}", headers=h, json={"deadline": None}).json()["deadline"] is None

    item = first_internship(client, h)
    linked = client.post(BASE, headers=h, json={"internship_id": item["id"]}).json()["id"]
    assert client.patch(f"{BASE}/{linked}", headers=h, json={"company": "Something Else"}).status_code == 400
    assert client.patch(f"{BASE}/{linked}", headers=h, json={"notes": "ok"}).status_code == 200


def test_resume_must_be_owned(client, auth):
    h = auth()
    r = client.post(BASE, headers=h, json={"company": "Acme Demo", "role": "Intern",
                                           "resume_id": "00000000-0000-0000-0000-000000000001"})
    assert r.status_code == 400


def test_isolation_between_users(client, auth):
    h, other = auth(), auth("b@example.com")
    app_id = client.post(BASE, headers=h, json={"company": "Acme Demo", "role": "Intern"}).json()["id"]
    assert client.get(f"{BASE}/{app_id}", headers=other).status_code == 404
    assert client.patch(f"{BASE}/{app_id}", headers=other, json={"notes": "x"}).status_code == 404
    assert client.post(f"{BASE}/{app_id}/status", headers=other, json={"status": "offer"}).status_code == 404
    assert client.delete(f"{BASE}/{app_id}", headers=other).status_code == 404
    assert client.get(BASE, headers=other).json()["items"] == []


def test_list_filter_counts_and_delete(client, auth):
    h = auth()
    a = client.post(BASE, headers=h, json={"company": "A Demo", "role": "Intern"}).json()["id"]
    client.post(BASE, headers=h, json={"company": "B Demo", "role": "Intern", "status": "applied"})
    body = client.get(BASE, headers=h).json()
    assert len(body["items"]) == 2 and body["counts"]["saved"] == 1 and body["counts"]["applied"] == 1
    assert body["counts"]["offer"] == 0
    only = client.get(f"{BASE}?status=applied", headers=h).json()
    assert [i["company"] for i in only["items"]] == ["B Demo"] and only["counts"]["saved"] == 1
    assert client.delete(f"{BASE}/{a}", headers=h).status_code == 204
    assert client.get(f"{BASE}/{a}", headers=h).status_code == 404
