"""Extract plain text from uploaded PDF / DOCX files (PyMuPDF and python-docx)."""

import io
import logging
import re
from dataclasses import dataclass

log = logging.getLogger(__name__)

MAX_PAGES = 20
MIN_TEXT_CHARS = 80  # below this we assume an image-only / scanned document

PDF_MAGIC = b"%PDF-"
ZIP_MAGIC = b"PK\x03\x04"  # .docx is a zip container


class DocumentError(ValueError):
    """User-facing problem with an uploaded document."""


@dataclass
class ExtractedText:
    text: str
    page_count: int | None


def detect_kind(filename: str, data: bytes) -> str:
    """Return 'pdf' or 'docx'. Checks both the extension and the file signature."""
    name = filename.lower()
    if name.endswith(".pdf"):
        if not data.startswith(PDF_MAGIC):
            raise DocumentError("This file has a .pdf name but is not a valid PDF.")
        return "pdf"
    if name.endswith(".docx"):
        if not data.startswith(ZIP_MAGIC):
            raise DocumentError("This file has a .docx name but is not a valid Word document.")
        return "docx"
    if name.endswith(".doc"):
        raise DocumentError("Old .doc files are not supported. Save it as .docx or PDF and upload again.")
    raise DocumentError("Only PDF and DOCX files are supported.")


def _clean(text: str) -> str:
    text = text.replace("\x00", "").replace(" ", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _pdf_text(data: bytes) -> ExtractedText:
    import pymupdf

    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise DocumentError("The PDF could not be opened. It may be corrupted.") from exc
    with doc:
        if doc.needs_pass:
            raise DocumentError("The PDF is password-protected. Remove the password and upload again.")
        pages = []
        for i, page in enumerate(doc):
            if i >= MAX_PAGES:
                break
            # sort=True reads multi-column layouts top-to-bottom, left-to-right.
            pages.append(page.get_text("text", sort=True))
        return ExtractedText(_clean("\n".join(pages)), doc.page_count)


def _docx_text(data: bytes) -> ExtractedText:
    import docx
    from docx.oxml.ns import qn

    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:
        raise DocumentError("The Word document could not be opened. It may be corrupted.") from exc

    lines: list[str] = []
    # Walk the body in order so paragraphs and tables stay in reading order.
    for block in document.element.body.iterchildren():
        if block.tag == qn("w:p"):
            text = "".join(node.text or "" for node in block.iter(qn("w:t")))
            if text.strip():
                lines.append(text)
        elif block.tag == qn("w:tbl"):
            for row in block.iter(qn("w:tr")):
                cells = []
                for cell in row.iter(qn("w:tc")):
                    cell_text = " ".join(
                        "".join(n.text or "" for n in p.iter(qn("w:t"))) for p in cell.iter(qn("w:p"))
                    ).strip()
                    if cell_text and cell_text not in cells:
                        cells.append(cell_text)
                if cells:
                    lines.append(" | ".join(cells))
    # Headers often hold the name and contact details.
    for section in document.sections:
        for p in section.header.paragraphs:
            if p.text.strip():
                lines.insert(0, p.text)
    return ExtractedText(_clean("\n".join(lines)), None)


def extract_text(filename: str, data: bytes) -> tuple[str, ExtractedText]:
    kind = detect_kind(filename, data)
    result = _pdf_text(data) if kind == "pdf" else _docx_text(data)
    if len(result.text) < MIN_TEXT_CHARS:
        raise DocumentError(
            "Almost no text could be read from this file. Scanned or image-only resumes are not "
            "supported; export your resume as a text-based PDF or DOCX."
        )
    log.info("extracted %d chars from %s (%s)", len(result.text), kind, result.page_count)
    return kind, result
