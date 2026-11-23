import pytest

from app.services.document_text import DocumentError, extract_text
from tests.factories import make_blank_pdf, make_docx, make_pdf


def test_pdf_text_extracted():
    kind, result = extract_text("cv.pdf", make_pdf())
    assert kind == "pdf"
    assert "asha.verma@example.com" in result.text
    assert result.page_count == 1


def test_docx_text_and_tables_extracted():
    kind, result = extract_text("CV.DOCX", make_docx())
    assert kind == "docx"
    assert "FastAPI" in result.text
    assert "MongoDB" in result.text  # from the table


@pytest.mark.parametrize(
    "name,data,msg",
    [
        ("cv.pdf", b"not a pdf at all" * 20, "not a valid PDF"),
        ("cv.docx", b"%PDF-1.7 pretending", "not a valid Word"),
        ("cv.doc", b"whatever", ".doc files are not supported"),
        ("cv.png", b"\x89PNG....", "Only PDF and DOCX"),
    ],
)
def test_bad_files_rejected(name, data, msg):
    with pytest.raises(DocumentError, match=msg):
        extract_text(name, data)


def test_image_only_pdf_rejected():
    with pytest.raises(DocumentError, match="Scanned or image-only"):
        extract_text("scan.pdf", make_blank_pdf())


def test_corrupt_pdf_rejected():
    with pytest.raises(DocumentError):
        extract_text("cv.pdf", b"%PDF-1.4\n garbage garbage")
