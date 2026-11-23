"""Behaviour when the database connection drops (flaky networks)."""

import pytest
from fastapi import APIRouter
from sqlalchemy.exc import OperationalError

from app.config import get_settings
from app.main import app
from app.services import resume_parser, resume_service, skill_service
from app.services.resume_parser import ResumeData
from tests.conftest import bearer
from tests.factories import make_pdf


@pytest.fixture(autouse=True)
def tmp_uploads(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "upload_dir", tmp_path)


@pytest.fixture()
def fake_llm(monkeypatch):
    calls = {"n": 0}

    def _fake(prompt, schema, **kw):
        calls["n"] += 1
        d = ResumeData()
        d.skills.technical = ["Python", "FastAPI"]
        return d

    monkeypatch.setattr(resume_parser, "generate_structured", _fake)
    monkeypatch.setattr(resume_service.time, "sleep", lambda s: None)
    return calls


def _drop():
    return OperationalError("SELECT 1", {}, Exception("server closed the connection unexpectedly"))


def test_extraction_save_retries_without_calling_llm_again(client, register, fake_llm, monkeypatch):
    real_sync = skill_service.sync_from_resume
    state = {"fails_left": 2}

    def flaky_sync(*args, **kwargs):
        if state["fails_left"]:
            state["fails_left"] -= 1
            raise _drop()
        return real_sync(*args, **kwargs)

    monkeypatch.setattr(skill_service, "sync_from_resume", flaky_sync)
    h = bearer(register().json()["access_token"])
    r = client.post("/api/resumes", headers=h, files={"file": ("cv.pdf", make_pdf(), "application/pdf")})
    assert r.status_code == 201, r.text
    assert r.json()["extraction_status"] == "complete"
    assert fake_llm["n"] == 1  # the LLM was not re-called on retry
    names = {s["name"] for s in client.get("/api/skills", headers=h).json()["extracted"]}
    assert names == {"Python", "FastAPI"}


def test_persistent_db_failure_returns_503_not_500(client, register, fake_llm, monkeypatch):
    def always_fail(*a, **k):
        raise _drop()

    monkeypatch.setattr(skill_service, "sync_from_resume", always_fail)
    h = bearer(register().json()["access_token"])
    r = client.post("/api/resumes", headers=h, files={"file": ("cv.pdf", make_pdf(), "application/pdf")})
    assert r.status_code == 503
    assert "temporarily unreachable" in r.json()["detail"]


_boom = APIRouter()


@_boom.get("/api/_test/dbdown")
def db_down():
    raise _drop()


app.include_router(_boom)


def test_operational_error_anywhere_maps_to_503(client):
    r = client.get("/api/_test/dbdown")
    assert r.status_code == 503
    assert "server closed" not in r.text  # internals are not leaked
