from datetime import date, timedelta

import pytest

from app.models import Resume, Skill, StudentSkill, User
from tests.conftest import bearer

URL = "/api/dashboard"


@pytest.fixture()
def auth(register):
    def _auth(email="a@example.com"):
        return bearer(register(email=email).json()["access_token"])

    return _auth


def _user_id(db_session_factory, email):
    with db_session_factory() as db:
        return db.query(User).filter_by(email=email).one().id


def _add_skill(db_session_factory, user_id, name, status):
    with db_session_factory() as db:
        skill = Skill(canonical=name.lower(), name=name)
        db.add(skill)
        db.flush()
        db.add(StudentSkill(user_id=user_id, skill_id=skill.id, status=status, source="manual" if status == "verified" else "resume"))
        db.commit()


def _add_resume(db_session_factory, user_id, active=True):
    with db_session_factory() as db:
        db.add(
            Resume(
                user_id=user_id, original_filename="cv.pdf", stored_filename="x.pdf", content_type="application/pdf",
                size_bytes=10, raw_text="t", is_active=active, extraction_status="complete",
            )
        )
        db.commit()


def test_requires_auth(client):
    assert client.get(URL).status_code == 401


def test_empty_account_gets_upload_hint_and_zeros(client, auth):
    d = client.get(URL, headers=auth()).json()
    assert d["profile"]["filled"] == 0 and d["profile"]["total"] == 6
    assert "College" in d["profile"]["missing"]
    assert d["resume"] == {"count": 0, "has_active": False, "active_filename": None, "extraction_status": None}
    assert d["skills"] == {"verified": 0, "extracted": 0, "rejected": 0}
    assert d["applications"]["total"] == 0
    assert d["applications"]["upcoming_deadlines"] == []
    assert d["next_step"]["path"] == "/profile"


def test_extracted_only_asks_to_verify(client, auth, db_session_factory):
    h = auth()
    uid = _user_id(db_session_factory, "a@example.com")
    _add_resume(db_session_factory, uid)
    _add_skill(db_session_factory, uid, "Python", "extracted")
    d = client.get(URL, headers=h).json()
    assert d["resume"]["has_active"] and d["resume"]["active_filename"] == "cv.pdf"
    assert d["skills"]["verified"] == 0 and d["skills"]["extracted"] == 1
    assert "Verify your skills" in d["next_step"]["message"]
    assert d["next_step"]["path"] == "/resume"


def test_verified_skills_and_profile_progress(client, auth, db_session_factory):
    h = auth()
    uid = _user_id(db_session_factory, "a@example.com")
    _add_resume(db_session_factory, uid)
    _add_skill(db_session_factory, uid, "Python", "verified")
    assert client.get(URL, headers=h).json()["next_step"]["path"] == "/profile"  # profile still empty
    client.put(
        "/api/profile", headers=h,
        json={"college": "Example Institute", "degree": "B.Tech", "branch": "CSE", "graduation_year": 2026, "cgpa": 8.1, "target_role": "Backend"},
    )
    d = client.get(URL, headers=h).json()
    assert d["profile"]["filled"] == 6 and d["profile"]["missing"] == []
    assert d["skills"]["verified"] == 1
    assert d["next_step"]["path"] == "/matching"


def test_applications_counts_and_deadlines(client, auth, db_session_factory):
    h = auth()
    uid = _user_id(db_session_factory, "a@example.com")
    _add_resume(db_session_factory, uid)
    _add_skill(db_session_factory, uid, "Python", "verified")
    today = date.today()
    mk = lambda company, status, dl: client.post(  # noqa: E731
        "/api/applications", headers=h,
        json={"company": company, "role": "Dev", "status": status, "deadline": dl.isoformat() if dl else None},
    ).status_code
    assert mk("Later Co", "saved", today + timedelta(days=10)) == 201
    assert mk("Soon Co", "applied", today + timedelta(days=2)) == 201
    assert mk("Past Co", "saved", today - timedelta(days=1)) == 201  # already passed: not listed
    assert mk("Done Co", "rejected", today + timedelta(days=1)) == 201  # closed: not listed
    assert mk("None Co", "saved", None) == 201
    d = client.get(URL, headers=h).json()["applications"]
    assert d["total"] == 5
    assert d["by_status"]["saved"] == 3 and d["by_status"]["applied"] == 1 and d["by_status"]["rejected"] == 1
    assert [x["company"] for x in d["upcoming_deadlines"]] == ["Soon Co", "Later Co"]
    assert d["upcoming_deadlines"][0]["days_left"] == 2


def test_other_users_data_is_not_counted(client, auth, db_session_factory):
    a, b = auth("a@example.com"), auth("b@example.com")
    client.post("/api/applications", headers=a, json={"company": "A Co", "role": "Dev"})
    uid_a = _user_id(db_session_factory, "a@example.com")
    _add_skill(db_session_factory, uid_a, "Python", "verified")
    _add_resume(db_session_factory, uid_a)
    d = client.get(URL, headers=b).json()
    assert d["applications"]["total"] == 0 and d["skills"]["verified"] == 0 and d["resume"]["count"] == 0
