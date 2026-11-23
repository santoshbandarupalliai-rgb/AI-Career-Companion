from datetime import timedelta

from app import security
from tests.conftest import bearer


def test_register_returns_tokens_and_user(register):
    r = register()
    assert r.status_code == 201
    body = r.json()
    assert body["access_token"] and body["refresh_token"]
    assert body["user"]["email"] == "student@example.com"
    assert "hashed_password" not in body["user"]


def test_register_duplicate_email_is_case_insensitive(register):
    assert register(email="Student@Example.com").status_code == 201
    r = register(email="student@example.COM")
    assert r.status_code == 409


def test_register_rejects_weak_password_without_echoing_it(register):
    r = register(password="onlyletters")
    assert r.status_code == 422
    assert "onlyletters" not in r.text
    assert any(e["field"] == "password" for e in r.json()["errors"])


def test_register_rejects_invalid_email_and_blank_name(register):
    assert register(email="not-an-email").status_code == 422
    assert register(full_name="   ").status_code == 422


def test_login_success_and_me(client, register):
    register()
    r = client.post("/api/auth/login", json={"email": "STUDENT@example.com", "password": "Secret123"})
    assert r.status_code == 200
    me = client.get("/api/auth/me", headers=bearer(r.json()["access_token"]))
    assert me.status_code == 200
    assert me.json()["full_name"] == "Test Student"


def test_login_failure_messages_do_not_reveal_which_part_was_wrong(client, register):
    register()
    wrong_pw = client.post("/api/auth/login", json={"email": "student@example.com", "password": "Wrong1234"})
    no_user = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "Wrong1234"})
    assert wrong_pw.status_code == no_user.status_code == 401
    assert wrong_pw.json()["detail"] == no_user.json()["detail"]


def test_me_requires_valid_access_token(client, register):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers=bearer("garbage.token.value")).status_code == 401
    # A refresh token must not work as an access token.
    refresh = register().json()["refresh_token"]
    assert client.get("/api/auth/me", headers=bearer(refresh)).status_code == 401


def test_expired_access_token_rejected(client, register, monkeypatch):
    user_id = register().json()["user"]["id"]
    token, _ = security._create_token(user_id, security.ACCESS, timedelta(seconds=-5))
    assert client.get("/api/auth/me", headers=bearer(token)).status_code == 401


def test_refresh_rotates_and_old_token_stops_working(client, register):
    first = register().json()
    r = client.post("/api/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert r.status_code == 200
    second = r.json()
    assert second["refresh_token"] != first["refresh_token"]
    assert client.get("/api/auth/me", headers=bearer(second["access_token"])).status_code == 200
    # Old refresh token is revoked.
    assert client.post("/api/auth/refresh", json={"refresh_token": first["refresh_token"]}).status_code == 401


def test_reusing_revoked_refresh_token_revokes_all_sessions(client, register):
    first = register().json()
    second = client.post("/api/auth/refresh", json={"refresh_token": first["refresh_token"]}).json()
    # Replay of the stolen/old token...
    assert client.post("/api/auth/refresh", json={"refresh_token": first["refresh_token"]}).status_code == 401
    # ...also kills the legitimate newer session.
    assert client.post("/api/auth/refresh", json={"refresh_token": second["refresh_token"]}).status_code == 401


def test_access_token_cannot_be_used_to_refresh(client, register):
    access = register().json()["access_token"]
    assert client.post("/api/auth/refresh", json={"refresh_token": access}).status_code == 401


def test_logout_revokes_refresh_token(client, register):
    tokens = register().json()
    assert client.post("/api/auth/logout", json={"refresh_token": tokens["refresh_token"]}).status_code == 204
    assert client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401
    # Logging out twice is harmless.
    assert client.post("/api/auth/logout", json={"refresh_token": tokens["refresh_token"]}).status_code == 204


def test_password_is_stored_hashed(db_session_factory, register):
    register()
    from sqlalchemy import select

    from app.models import User

    with db_session_factory() as db:
        user = db.scalar(select(User))
        assert user.hashed_password != "Secret123"
        assert security.verify_password("Secret123", user.hashed_password)


def test_responses_carry_request_id(client):
    r = client.get("/api/auth/me")
    assert r.headers.get("X-Request-ID")
