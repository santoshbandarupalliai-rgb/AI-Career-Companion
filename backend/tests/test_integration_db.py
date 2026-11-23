"""Checks against the real Supabase database (read-only)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import engine
from app.main import app

pytestmark = pytest.mark.integration


def test_health_reaches_database():
    with TestClient(app) as c:
        r = c.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "database": "ok"}


def test_migrations_are_at_head():
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from pathlib import Path

    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    head = ScriptDirectory.from_config(cfg).get_current_head()
    with engine.connect() as conn:
        current = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert current == head, "Run: alembic upgrade head"


def test_every_public_table_has_row_level_security():
    """Guards against exposing a table through Supabase's public REST API."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relkind = 'r' AND NOT c.relrowsecurity"
            )
        ).all()
    assert rows == [], f"Tables without RLS: {[r[0] for r in rows]}"


def test_pgvector_enabled():
    with engine.connect() as conn:
        assert conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")).scalar() == 1
