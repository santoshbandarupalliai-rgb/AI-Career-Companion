from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import EmailToken, User
from app.services import email_service
from tests.conftest import bearer


@pytest.fixture()
def sent(monkeypatch):
    """Capture verification emails instead of sending them."""
    box: list[dict] = []
    monkeypatch.setattr(email_service, "send_verification_email", lambda to, name, token: box.append({"to": to, "token": token}) or True)
    return box


def signup(register, email="v@example.com"):
    r = register(email=email)
    assert r.status_code == 201
    return r.json()


def test_register_starts_unverified_and_sends_a_link(register, sent):
    data = signup(register)
    assert data["user"]["email_verified"] is False
    assert len(sent) == 1 and sent[0]["to"] == "v@example.com" and len(sent[0]["token"]) > 20


def test_verify_marks_the_account_and_the_token_works_once(client, register, sent):
    data = signup(register)
    h = bearer(data["access_token"])
    r = client.post("/api/auth/verify-email", json={"token": sent[0]["token"]})
    assert r.status_code == 200 and r.json()["email_verified"] is True
    assert client.get("/api/auth/me", headers=h).json()["email_verified"] is True
    again = client.post("/api/auth/verify-email", json={"token": sent[0]["token"]})
    assert again.status_code == 400


def test_invalid_and_expired_tokens_are_rejected(client, register, sent, db_session_factory):
    signup(register)
    assert client.post("/api/auth/verify-email", json={"token": "not-a-real-token-value"}).status_code == 400
    with db_session_factory() as db:
        row = db.scalar(select(EmailToken))
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    r = client.post("/api/auth/verify-email", json={"token": sent[0]["token"]})
    assert r.status_code == 400 and "expired" in r.json()["detail"]


def test_tokens_are_stored_hashed(register, sent, db_session_factory):
    signup(register)
    with db_session_factory() as db:
        row = db.scalar(select(EmailToken))
        assert row.token_hash != sent[0]["token"] and len(row.token_hash) == 64


def test_resend_has_a_cooldown_and_replaces_the_old_link(client, register, sent, db_session_factory):
    h = bearer(signup(register)["access_token"])
    too_soon = client.post("/api/auth/resend-verification", headers=h)
    assert too_soon.status_code == 429
    with db_session_factory() as db:  # pretend the first email was sent a while ago
        for row in db.scalars(select(EmailToken)):
            row.created_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        db.commit()
    ok = client.post("/api/auth/resend-verification", headers=h)
    assert ok.status_code == 200 and len(sent) == 2
    assert client.post("/api/auth/verify-email", json={"token": sent[0]["token"]}).status_code == 400  # old link is dead
    assert client.post("/api/auth/verify-email", json={"token": sent[1]["token"]}).status_code == 200


def test_resend_when_already_verified(client, register, sent):
    h = bearer(signup(register)["access_token"])
    client.post("/api/auth/verify-email", json={"token": sent[0]["token"]})
    r = client.post("/api/auth/resend-verification", headers=h)
    assert r.status_code == 200 and r.json()["already_verified"] is True and len(sent) == 1


def test_resend_requires_sign_in(client):
    assert client.post("/api/auth/resend-verification").status_code == 401


def test_enforcement_blocks_unverified_users_only_when_enabled(client, register, sent, monkeypatch):
    h = bearer(signup(register)["access_token"])
    assert client.get("/api/profile", headers=h).status_code == 200  # off by default
    monkeypatch.setattr(get_settings(), "require_email_verification", True)
    blocked = client.get("/api/profile", headers=h)
    assert blocked.status_code == 403 and "verify" in blocked.json()["detail"].lower()
    assert client.get("/api/auth/me", headers=h).status_code == 200  # the account page and resend stay reachable
    client.post("/api/auth/verify-email", json={"token": sent[0]["token"]})
    assert client.get("/api/profile", headers=h).status_code == 200


def test_existing_users_helper_columns_default_to_unverified(db_session_factory):
    with db_session_factory() as db:
        db.add(User(full_name="X", email="x@example.com", hashed_password="h"))
        db.commit()
        assert db.scalar(select(User)).email_verified is False


# ---------- sending ----------

def test_no_smtp_host_means_nothing_is_sent(monkeypatch):
    monkeypatch.setattr(get_settings(), "smtp_host", "")
    assert email_service.send_email("a@example.com", "s", "body") is False
    assert email_service.smtp_configured() is False


def test_smtp_send_uses_starttls_and_login(monkeypatch):
    s = get_settings()
    for k, v in dict(smtp_host="smtp.test", smtp_port=587, smtp_user="u@test", smtp_password="pw", smtp_from="", smtp_ssl=False, smtp_starttls=True).items():
        monkeypatch.setattr(s, k, v)
    calls: list = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None, **kw):
            calls.append(("connect", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self, context=None):
            calls.append(("starttls",))

        def login(self, user, pw):
            calls.append(("login", user, pw))

        def send_message(self, msg):
            calls.append(("send", msg["To"], msg["Subject"], msg["From"]))

    monkeypatch.setattr(email_service.smtplib, "SMTP", FakeSMTP)
    assert email_service.send_verification_email("to@example.com", "Asha", "tok123") is True
    assert calls[0] == ("connect", "smtp.test", 587) and ("starttls",) in calls and ("login", "u@test", "pw") in calls
    send = [c for c in calls if c[0] == "send"][0]
    assert send[1] == "to@example.com" and send[3] == "u@test" and "Verify" in send[2]


def test_smtp_failure_is_swallowed_and_hides_the_password(monkeypatch, caplog):
    s = get_settings()
    for k, v in dict(smtp_host="smtp.test", smtp_user="u@test", smtp_password="topsecretpw", smtp_ssl=False, smtp_starttls=False).items():
        monkeypatch.setattr(s, k, v)

    def boom(*a, **k):
        raise OSError("connection refused topsecretpw")

    monkeypatch.setattr(email_service.smtplib, "SMTP", boom)
    with caplog.at_level("ERROR"):
        assert email_service.send_email("a@example.com", "s", "b") is False
    assert "topsecretpw" not in caplog.text


def test_verification_link_uses_the_configured_base(monkeypatch):
    monkeypatch.setattr(get_settings(), "app_base_url", "https://careers.example.org/")
    assert email_service.verification_link("abc") == "https://careers.example.org/verify-email?token=abc"
