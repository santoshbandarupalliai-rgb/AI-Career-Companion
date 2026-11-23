"""Split text into overlapping, paragraph-aware chunks for embedding.

Reused by the Product Assistant (Phase 4) for the Product Knowledge Document.
Sizes are in characters: bge-small has a 512-token window, and ~1200 chars is safely under it.
"""

import re

DEFAULT_MAX_CHARS = 1200
DEFAULT_OVERLAP = 150


def _split_long(paragraph: str, max_chars: int) -> list[str]:
    """Split an over-long paragraph on sentence boundaries, hard-cutting only as a last resort."""
    sentences = re.split(r"(?<=[.!?])\s+", paragraph)
    out, cur = [], ""
    for s in sentences:
        while len(s) > max_chars:
            if cur:
                out.append(cur)
                cur = ""
            out.append(s[:max_chars])
            s = s[max_chars:]
        if cur and len(cur) + 1 + len(s) > max_chars:
            out.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        out.append(cur)
    return out


def chunk_text(text: str, max_chars: int = DEFAULT_MAX_CHARS, overlap: int = DEFAULT_OVERLAP) -> list[str]:
    if max_chars <= overlap:
        raise ValueError("max_chars must be larger than overlap")
    text = re.sub(r"[ \t]+", " ", text.replace("\r\n", "\n")).strip()
    if not text:
        return []
    pieces: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        pieces.extend(_split_long(para, max_chars) if len(para) > max_chars else [para])

    chunks: list[str] = []
    cur = ""
    for piece in pieces:
        if cur and len(cur) + 2 + len(piece) > max_chars:
            chunks.append(cur)
            tail = cur[-overlap:] if overlap else ""
            # Start the next chunk with a little context, at a word boundary.
            tail = tail[tail.find(" ") + 1 :] if " " in tail else ""
            cur = f"{tail}\n\n{piece}".strip() if tail else piece
        else:
            cur = f"{cur}\n\n{piece}" if cur else piece
    if cur:
        chunks.append(cur)
    return chunks
