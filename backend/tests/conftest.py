"""Test fixtures.

API tests run against an in-memory SQLite database so they are fast and never
touch Supabase data. Tests marked `integration` use the real DATABASE_URL.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db import Base, get_db
from app.main import app


@pytest.fixture()
def db_session_factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    yield factory
    engine.dispose()


@pytest.fixture()
def client(db_session_factory):
    def _get_db():
        db = db_session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def register(client):
    def _register(email="student@example.com", password="Secret123", full_name="Test Student"):
        return client.post(
            "/api/auth/register", json={"full_name": full_name, "email": email, "password": password}
        )

    return _register


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
