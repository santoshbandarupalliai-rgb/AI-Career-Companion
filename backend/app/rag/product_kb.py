"""Ingest the Product Knowledge Document into the 'product' corpus.

The Markdown source (docs/02_PRODUCT_KNOWLEDGE_DOCUMENT.md) is split into sections at
`##` / `###` headings. Each section becomes one rag_document, so a citation points at a
named section (e.g. "Features > 2.3 Resume upload and parsing (Available)").
Re-running is cheap: unchanged sections are not re-embedded and removed sections are deleted.
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import BACKEND_DIR
from app.models import RagDocument
from app.rag import embeddings, retriever
from app.rag.chunker import chunk_text

log = logging.getLogger(__name__)

CORPUS = "product"
DOC_PATH = BACKEND_DIR.parent / "docs" / "02_PRODUCT_KNOWLEDGE_DOCUMENT.md"


@dataclass
class Section:
    key: str
    title: str  # heading path, e.g. "Features > 2.3 Resume upload and parsing (Available)"
    body: str


def parse_sections(markdown: str) -> list[Section]:
    sections: list[Section] = []
    h2 = h3 = ""
    buf: list[str] = []
    in_code = False

    def flush():
        body = "\n".join(buf).strip()
        if body and h2:
            title = f"{h2} > {h3}" if h3 else h2
            sections.append(Section(key=_slug(title), title=title, body=body))
        buf.clear()

    for line in markdown.splitlines():
        if line.startswith("```"):
            in_code = not in_code
        m = None if in_code else re.match(r"^(#{2,3})\s+(.*\S)\s*$", line)
        if m:
            flush()
            if len(m.group(1)) == 2:
                h2, h3 = m.group(2), ""
            else:
                h3 = m.group(2)
        elif not (line.startswith("# ") and not in_code):
            buf.append(line)
    flush()
    return sections


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:190]


def _section_text(s: Section) -> str:
    return f"{s.title}\n\n{s.body}"


def ingest(db: Session, path: Path = DOC_PATH) -> dict:
    """Index the document. Returns {'sections', 'updated', 'removed'}. Commits."""
    sections = parse_sections(path.read_text(encoding="utf-8"))
    if not sections:
        raise ValueError(f"No sections found in {path}")
    existing = {d.source_key: d for d in db.scalars(select(RagDocument).where(RagDocument.corpus == CORPUS))}

    # Embed first (slow), before the write transaction.
    todo: list[tuple[Section, str, tuple[list[str], list[list[float]]]]] = []
    for s in sections:
        text = _section_text(s)
        doc = existing.get(s.key)
        if doc is not None and doc.content_hash == retriever._hash(text):
            continue
        # Prefix every chunk with the section title so chunk 2+ keeps its context.
        chunks = [f"{s.title}\n\n{c}" for c in chunk_text(s.body)]
        todo.append((s, text, (chunks, embeddings.embed_documents(chunks))))
    db.rollback()  # release the read transaction

    for s, text, prepared in todo:
        retriever.upsert_document(
            db, corpus=CORPUS, source_key=s.key, title=s.title, text=text, meta={"path": s.title}, prepared=prepared
        )
    keys = {s.key for s in sections}
    removed = [k for k in existing if k not in keys]
    for k in removed:
        retriever.delete_document(db, CORPUS, k)
    db.commit()
    log.info("product kb ingested: %d sections, %d updated, %d removed", len(sections), len(todo), len(removed))
    return {"sections": len(sections), "updated": len(todo), "removed": len(removed)}


def ensure_ingested(db: Session) -> None:
    """Index the document on first use if nothing is indexed yet."""
    count = db.scalar(select(func.count()).select_from(RagDocument).where(RagDocument.corpus == CORPUS)) or 0
    if count == 0:
        ingest(db)
