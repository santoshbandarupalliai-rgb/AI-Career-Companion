from app.llm import LLMError
from app.services import resume_parser, skills_catalog
from app.services.resume_parser import Project, ResumeData, ground
from tests.factories import SAMPLE_RESUME_TEXT


def test_canonicalize_aliases_and_no_substring_confusion():
    assert skills_catalog.canonicalize("ReactJS")[0] == "react"
    assert skills_catalog.canonicalize("JS")[0] == "javascript"
    assert skills_catalog.canonicalize("Java")[0] == "java"
    assert skills_catalog.canonicalize("JavaScript")[0] == "javascript"
    assert skills_catalog.canonicalize("Python 3.11")[0] == "python"
    assert skills_catalog.canonicalize("Some Niche Tool")[1] == "Some Niche Tool"
    assert skills_catalog.canonicalize("   ") is None


def test_find_known_skills_does_not_match_inside_words():
    found = skills_catalog.find_known_skills("I used JavaScript and React; also good at teamwork.")
    assert "javascript" in found and "react" in found and "teamwork" in found
    assert "java" not in found  # "Java" must not match inside "JavaScript"


def test_grounding_removes_hallucinated_skills_and_contacts():
    data = ResumeData()
    data.skills.technical = ["Python", "Kubernetes", "JS"]  # Kubernetes is not in the text
    data.personal.email = "someone.else@example.com"
    data.personal.phone = "+91 98765 43210"
    data.projects = [Project(name="Study Planner", technologies=["React", "Angular"])]
    warnings = ground(data, SAMPLE_RESUME_TEXT)
    assert data.skills.technical == ["Python", "JS"]  # JS grounded via its alias "JavaScript"
    assert data.personal.email == ""
    assert data.personal.phone == "+91 98765 43210"
    assert data.projects[0].technologies == ["React"]
    assert any("Kubernetes" in w for w in warnings)
    assert any("Angular" in w for w in warnings)


def test_parse_uses_llm_and_grounds(monkeypatch):
    def fake_llm(prompt, schema, **kw):
        d = ResumeData()
        d.personal.name = "Asha Verma"
        d.skills.technical = ["Python", "FastAPI", "Rust"]  # Rust invented
        return d

    monkeypatch.setattr(resume_parser, "generate_structured", fake_llm)
    result = resume_parser.parse_resume(SAMPLE_RESUME_TEXT)
    assert result.method == "llm" and result.status == "complete"
    assert result.data.skills.technical == ["Python", "FastAPI"]


def test_parse_falls_back_to_heuristics_when_llm_fails(monkeypatch):
    def failing(*a, **kw):
        raise LLMError("down")

    monkeypatch.setattr(resume_parser, "generate_structured", failing)
    result = resume_parser.parse_resume(SAMPLE_RESUME_TEXT)
    assert result.method == "heuristic" and result.status == "partial"
    assert result.data.personal.email == "asha.verma@example.com"
    assert result.data.personal.name == "Asha Verma"
    names = resume_parser.all_skills(result.data)
    assert {"Python", "FastAPI", "Docker", "Git"} <= set(names)
    assert "Java" not in names
    assert "unavailable" in result.warnings[0]
