from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import TypeDecorator

# JSONB on Postgres (indexable, compact), plain JSON on SQLite for tests.
JSONType = JSON().with_variant(JSONB(), "postgresql")

EMBEDDING_DIM = 384  # BAAI/bge-small-en-v1.5


class EmbeddingType(TypeDecorator):
    """pgvector `vector(384)` on Postgres; a JSON list of floats on SQLite (tests).

    The SQLite fallback exists only so non-integration tests can run. Similarity
    search on SQLite is done in Python (see app/rag/retriever.py).
    """

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from pgvector.sqlalchemy import Vector

            return dialect.type_descriptor(Vector(EMBEDDING_DIM))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return [float(x) for x in value]

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return [float(x) for x in value]
