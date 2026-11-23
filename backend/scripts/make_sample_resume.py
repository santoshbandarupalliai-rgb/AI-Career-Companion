"""Write a fictional sample resume PDF for demos (docs/03_DEMO_SCRIPT.md).

Run from the repo root:   backend\\.venv\\Scripts\\python backend\\scripts\\make_sample_resume.py
Output:                   docs/exports/sample_resume_demo.pdf
Everything in it is made up (fictional person, institute and employer).
"""

from pathlib import Path

TEXT = """Asha Verma
asha.verma@example.com | +91 98765 43210 | github.com/ashaverma-demo
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


def main() -> None:
    import pymupdf

    out = Path(__file__).resolve().parents[2] / "docs" / "exports" / "sample_resume_demo.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()
    page = doc.new_page()
    y = 50
    for line in TEXT.splitlines():
        page.insert_text((50, y), line, fontsize=9)
        y += 13
    doc.save(str(out))
    doc.close()
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
