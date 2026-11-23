from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB

# JSONB on Postgres (indexable, compact), plain JSON on SQLite for tests.
JSONType = JSON().with_variant(JSONB(), "postgresql")
