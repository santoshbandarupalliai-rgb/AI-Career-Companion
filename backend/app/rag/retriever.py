"""Index text into rag_documents/rag_chunks and search it by cosine similarity.

On Postgres the search uses pgvector's `<=>` operator (HNSW index). On SQLite
(unit tests only) the same ranking is computed in Python, so tests exercise the
real indexing code path.
"""

import hashlib
import math
import uuid
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import RagChunk, RagDocument
from app.rag import embeddings
from app.rag.chunker import chunk_text


@dataclass
class Hit:
    document_id: uuid.UUID
    source_key: str
    title: str
    chunk_index: int
    content: str
    score: float  # cosine similarity, higher is better
    meta: dict


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def prepare_chunks(text: str) -> tuple[list[str], list[list[float]]]:
    """Chunk and embed OUTSIDE any DB transaction (embedding is slow)."""
    chunks = chunk_text(text)
    return chunks, embeddings.embed_documents(chunks)


def upsert_document(
    db: Session,
    *,
    corpus: str,
    source_key: str,
    title: str,
    text: str,
    meta: dict | None = None,
    prepared: tuple[list[str], list[list[float]]] | None = None,
) -> RagDocument | None:
    """Create or refresh a document's chunks. Does not commit.

    Returns None when the text is unchanged (nothing re-embedded). Pass `prepared`
    (from `prepare_chunks`) to keep embedding out of the transaction.
    """
    digest = _hash(text)
    doc = db.scalar(select(RagDocument).where(RagDocument.corpus == corpus, RagDocument.source_key == source_key))
    if doc is not None and doc.content_hash == digest:
        return None
    chunks, vectors = prepared if prepared is not None else prepare_chunks(text)
    if doc is None:
        doc = RagDocument(corpus=corpus, source_key=source_key, title=title, content_hash=digest, meta=meta or {})
        db.add(doc)
        db.flush()
    else:
        doc.title, doc.content_hash, doc.meta = title, digest, meta or {}
        db.execute(delete(RagChunk).where(RagChunk.document_id == doc.id))
    db.add_all(
        RagChunk(document_id=doc.id, corpus=corpus, chunk_index=i, content=c, embedding=v)
        for i, (c, v) in enumerate(zip(chunks, vectors))
    )
    return doc


def delete_document(db: Session, corpus: str, source_key: str) -> None:
    doc = db.scalar(select(RagDocument).where(RagDocument.corpus == corpus, RagDocument.source_key == source_key))
    if doc is not None:
        db.delete(doc)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def search(
    db: Session,
    query_vector: list[float],
    *,
    corpus: str,
    limit: int = 10,
    allowed_source_keys: set[str] | None = None,
) -> list[Hit]:
    """Best chunk per document, ranked by cosine similarity.

    `allowed_source_keys` restricts results (e.g. to internships passing the user's filters).
    """
    if allowed_source_keys is not None and not allowed_source_keys:
        return []

    if db.get_bind().dialect.name == "postgresql":
        from pgvector.sqlalchemy import Vector
        from sqlalchemy import type_coerce

        # The column is an EmbeddingType (SQLite-friendly wrapper); coerce to Vector for pgvector operators.
        distance = type_coerce(RagChunk.embedding, Vector(embeddings.DIM)).cosine_distance(query_vector)
        stmt = (
            select(RagChunk, RagDocument, distance.label("distance"))
            .join(RagDocument, RagDocument.id == RagChunk.document_id)
            .where(RagChunk.corpus == corpus)
        )
        if allowed_source_keys is not None:
            stmt = stmt.where(RagDocument.source_key.in_(allowed_source_keys))
        # Over-fetch: several chunks of one document may rank high; we keep the best per document.
        rows = [(c, d, 1.0 - float(dist)) for c, d, dist in db.execute(stmt.order_by(distance).limit(limit * 4))]
    else:
        stmt = select(RagChunk, RagDocument).join(RagDocument, RagDocument.id == RagChunk.document_id).where(
            RagChunk.corpus == corpus
        )
        if allowed_source_keys is not None:
            stmt = stmt.where(RagDocument.source_key.in_(allowed_source_keys))
        rows = sorted(
            ((c, d, _cosine(query_vector, c.embedding)) for c, d in db.execute(stmt)), key=lambda r: r[2], reverse=True
        )

    best: dict[uuid.UUID, Hit] = {}
    for chunk, doc, score in rows:
        if doc.id not in best:
            best[doc.id] = Hit(doc.id, doc.source_key, doc.title, chunk.chunk_index, chunk.content, score, doc.meta)
    return sorted(best.values(), key=lambda h: h.score, reverse=True)[:limit]
