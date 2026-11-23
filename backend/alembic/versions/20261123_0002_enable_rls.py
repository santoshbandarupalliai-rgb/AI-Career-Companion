"""Enable row-level security on app tables.

Supabase exposes the public schema through its auto-generated REST API
(PostgREST) to the `anon` and `authenticated` roles. This app does not use
that API: the FastAPI backend connects as the table owner, which bypasses RLS.
Enabling RLS with no policies makes the tables unreadable through the REST API
while leaving the backend unaffected.

Every future migration that creates a table must also enable RLS on it
(see tests/test_rls.py, which checks all public tables).

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-23
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

TABLES = ("users", "refresh_tokens", "alembic_version")


def upgrade() -> None:
    for table in TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    for table in TABLES:
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
