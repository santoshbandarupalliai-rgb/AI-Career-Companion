"""Build small but real PDF and DOCX resumes in memory for tests."""

import io

SAMPLE_RESUME_TEXT = """Asha Verma
asha.verma@example.com | +91 98765 43210 | linkedin.com/in/asha-verma-demo | github.com/ashaverma-demo
Bengaluru, India

SUMMARY
Final-year computer science student interested in backend development.

EDUCATION
B.Tech in Computer Science, Example Institute of Technology, 2022 - 2026, CGPA 8.4

SKILLS
Languages: Python, JavaScript, SQL
Frameworks: FastAPI, React
Tools: Git, Docker, Postman
Soft skills: Teamwork, Communication

EXPERIENCE
Backend Intern, Sample Labs, May 2025 - July 2025
- Built REST APIs with FastAPI and PostgreSQL for an internal dashboard.

PROJECTS
Study Planner: A web app built with React and Node.js that schedules revision sessions.

CERTIFICATIONS
Python for Everybody - Coursera - 2024
"""


def make_pdf(text: str = SAMPLE_RESUME_TEXT) -> bytes:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    y = 50
    for line in text.splitlines():
        page.insert_text((50, y), line, fontsize=9)
        y += 13
    data = doc.tobytes()
    doc.close()
    return data


def make_blank_pdf() -> bytes:
    import pymupdf

    doc = pymupdf.open()
    doc.new_page()
    data = doc.tobytes()
    doc.close()
    return data


def make_docx(text: str = SAMPLE_RESUME_TEXT, with_table: bool = True) -> bytes:
    import docx

    d = docx.Document()
    for line in text.splitlines():
        d.add_paragraph(line)
    if with_table:
        t = d.add_table(rows=1, cols=2)
        t.cell(0, 0).text = "Databases"
        t.cell(0, 1).text = "MongoDB"
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()
