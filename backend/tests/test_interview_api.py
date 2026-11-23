import pytest
from sqlalchemy import select

from app.llm import LLMError
from app.models import InterviewItem, InterviewSession
from app.schemas.interview import EvaluationLLM, QuestionLLM, QuestionsLLM
from app.services import interview_service, internship_service
from tests.conftest import bearer
from tests.test_tailoring_api import give_resume

BASE = "/api/interview"


def q(text, category="technical", difficulty="medium"):
    return QuestionLLM(question=text, category=category, difficulty=difficulty)


class FakeLLM:
    def __init__(self):
        self.prompts = []
        self.fail = False
        self.questions = QuestionsLLM(questions=[
            q("Explain how a Python dictionary works internally."),
            q("Tell me about a time you resolved a conflict in a team.", "behavioral", "easy"),
            q("Explain how a Python dictionary works internally."),  # duplicate
            q("Walk me through your Budget Tracker project.", "resume", "medium"),
            q("How would you design a REST API for a to-do app? See https://spam.test", "technical", "hard"),
            q("What would you do if a deadline was at risk?", "situational", "medium"),
        ])
        self.evaluation = EvaluationLLM(relevance=3, structure=2, depth=1, strengths=["Clear start. https://x.test"],
                                        improvements=["Add an example."], answer_outline="Cover hashing and collisions.")

    def structured(self, prompt, schema, **kw):
        if self.fail:
            raise LLMError("The AI service request failed.")
        self.prompts.append(prompt)
        return self.questions if schema is QuestionsLLM else self.evaluation


@pytest.fixture()
def llm(monkeypatch):
    f = FakeLLM()
    monkeypatch.setattr(interview_service, "generate_structured", f.structured)
    return f


@pytest.fixture()
def seeded(db_session_factory, monkeypatch):
    from app.rag import embeddings
    monkeypatch.setattr(embeddings, "embed_documents", lambda texts: [[0.1] * embeddings.DIM for _ in texts])
    with db_session_factory() as db:
        internship_service.seed_samples(db)


@pytest.fixture()
def auth(register):
    def _auth(email="a@example.com"):
        return bearer(register(email=email).json()["access_token"])

    return _auth


def start(client, h, **body):
    return client.post(f"{BASE}/sessions", headers=h, json=body or {"role": "Backend developer"})


ANSWER = "A dictionary hashes the key to find a bucket and handles collisions by probing, giving average constant time lookups."


def test_requires_auth(client):
    assert client.get(f"{BASE}/sessions").status_code == 401


def test_session_creation_cleans_questions(client, auth, llm, db_session_factory):
    h = auth()
    give_resume(db_session_factory)
    r = start(client, h, role="Backend developer", count=8)
    assert r.status_code == 201
    body = r.json()
    items = body["items"]
    assert [i["position"] for i in items] == [1, 2, 3, 4, 5]  # duplicate dropped
    assert all("http" not in i["question"] for i in items)
    assert {i["category"] for i in items} >= {"technical", "behavioral", "resume", "situational"}
    assert body["session"]["role"] == "Backend developer" and body["session"]["answered"] == 0 and body["session"]["average_score"] is None
    assert "Budget Tracker" in llm.prompts[0]  # grounded in the real resume


def test_count_limits_questions(client, auth, llm):
    assert len(start(client, auth(), role="Data analyst", count=3).json()["items"]) == 3
    assert start(client, auth("b@example.com"), role="x", count=3).status_code == 422
    assert start(client, auth("c@example.com"), role="Data analyst", count=50).status_code == 422


def test_resume_questions_are_not_pretended_without_a_resume(client, auth, llm):
    items = start(client, auth(), role="Backend developer").json()["items"]
    assert "resume" not in {i["category"] for i in items}  # no resume: reclassified, never presented as resume-based


def test_needs_a_target(client, auth, llm):
    assert start(client, auth(), count=5).status_code == 400
    assert llm.prompts == []


def test_for_an_internship_uses_the_posting(client, auth, llm, seeded):
    h = auth()
    p = next(i for i in client.get("/api/internships?limit=100", headers=h).json()["items"] if i["title"].startswith("Generative AI"))
    r = start(client, h, internship_id=p["id"])
    assert r.status_code == 201 and r.json()["session"]["role"] == "Generative AI Intern (RAG Systems)"
    assert "Retrieval Augmented Generation" in llm.prompts[0] or "RAG" in llm.prompts[0]


def test_llm_failure_creates_nothing(client, auth, llm, db_session_factory):
    h = auth()
    llm.fail = True
    assert start(client, h).status_code == 503
    llm.fail = False
    assert client.get(f"{BASE}/sessions", headers=h).json() == []


def test_too_few_usable_questions_is_an_error_not_a_canned_fallback(client, auth, llm):
    llm.questions = QuestionsLLM(questions=[q("Explain how a Python dictionary works internally.")])
    assert start(client, auth()).status_code == 503


def test_answer_is_scored_with_the_rubric_and_saved(client, auth, llm):
    h = auth()
    s = start(client, h).json()
    item = s["items"][0]
    r = client.post(f"{BASE}/sessions/{s['session']['id']}/items/{item['id']}/answer", headers=h, json={"answer": ANSWER})
    assert r.status_code == 200
    body = r.json()
    assert body["score"] == 6 and body["user_answer"] == ANSWER
    assert body["feedback"]["relevance"] == 3 and body["feedback"]["strengths"] == ["Clear start."]
    assert "http" not in str(body["feedback"])
    detail = client.get(f"{BASE}/sessions/{s['session']['id']}", headers=h).json()
    assert detail["session"]["answered"] == 1 and detail["session"]["average_score"] == 6.0
    assert detail["items"][0]["score"] == 6 and detail["items"][1]["score"] is None
    assert client.get(f"{BASE}/sessions", headers=h).json()[0]["average_score"] == 6.0
    # the answer reaches the model delimited as data
    assert "<<<\n" + ANSWER in llm.prompts[-1]


def test_reanswering_replaces_the_previous_score(client, auth, llm):
    h = auth()
    s = start(client, h).json()
    url = f"{BASE}/sessions/{s['session']['id']}/items/{s['items'][0]['id']}/answer"
    client.post(url, headers=h, json={"answer": ANSWER})
    llm.evaluation = EvaluationLLM(relevance=4, structure=3, depth=3)
    assert client.post(url, headers=h, json={"answer": ANSWER + " Resizing keeps load factor low."}).json()["score"] == 10


def test_answer_validation_and_scoring_failure(client, auth, llm):
    h = auth()
    s = start(client, h).json()
    url = f"{BASE}/sessions/{s['session']['id']}/items/{s['items'][0]['id']}/answer"
    assert client.post(url, headers=h, json={"answer": "idk"}).status_code == 422
    assert client.post(url, headers=h, json={"answer": "x" * 3001}).status_code == 422
    llm.fail = True
    assert client.post(url, headers=h, json={"answer": ANSWER}).status_code == 503
    detail = client.get(f"{BASE}/sessions/{s['session']['id']}", headers=h).json()
    assert detail["items"][0]["user_answer"] is None and detail["items"][0]["score"] is None  # nothing half-saved


def test_rubric_bounds_are_enforced_by_the_schema():
    with pytest.raises(Exception):
        EvaluationLLM(relevance=5, structure=3, depth=3)
    with pytest.raises(Exception):
        EvaluationLLM(relevance=4, structure=-1, depth=0)


def test_sessions_are_private(client, auth, llm):
    a, b = auth("a@example.com"), auth("b@example.com")
    s = start(client, a).json()
    sid, iid = s["session"]["id"], s["items"][0]["id"]
    assert client.get(f"{BASE}/sessions/{sid}", headers=b).status_code == 404
    assert client.post(f"{BASE}/sessions/{sid}/items/{iid}/answer", headers=b, json={"answer": ANSWER}).status_code == 404
    assert client.delete(f"{BASE}/sessions/{sid}", headers=b).status_code == 404
    assert client.get(f"{BASE}/sessions", headers=b).json() == []
    # an item cannot be answered through a different session of the same user
    s2 = start(client, a).json()
    assert client.post(f"{BASE}/sessions/{s2['session']['id']}/items/{iid}/answer", headers=a, json={"answer": ANSWER}).status_code == 404


def test_cannot_practise_for_someone_elses_private_posting(client, auth, llm):
    a, b = auth("a@example.com"), auth("b@example.com")
    mine = client.post("/api/internships", headers=a, json={"title": "Private", "company": "Hidden Co", "description": "A private posting for its creator only."}).json()
    assert start(client, b, internship_id=mine["id"]).status_code == 404


def test_delete_cascades(client, auth, llm, db_session_factory):
    h = auth()
    s = start(client, h).json()
    assert client.delete(f"{BASE}/sessions/{s['session']['id']}", headers=h).status_code == 204
    with db_session_factory() as db:
        assert db.scalar(select(InterviewItem.id).limit(1)) is None and db.scalar(select(InterviewSession.id).limit(1)) is None
