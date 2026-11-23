import hashlib
import math
import re

import pytest
from sqlalchemy import select

from app.llm import LLMError
from app.models import ChatMessage, User
from app.rag import embeddings, product_kb
from app.rag.product_kb import DOC_PATH, parse_sections
from app.services import chat_repo, product_assistant
from app.services.product_assistant import NOT_FOUND_REPLY, Answer
from tests.conftest import bearer

BASE = "/api/chat/product"


def _fake_vec(text: str) -> list[float]:
    v = [0.0] * embeddings.DIM
    for w in re.findall(r"[a-z0-9+#]+", text.lower()):
        v[int(hashlib.md5(w.encode()).hexdigest(), 16) % embeddings.DIM] += 1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


class FakeLLM:
    """Records prompts and returns scripted output."""

    def __init__(self):
        self.structured_prompts: list[str] = []
        self.text_prompts: list[tuple[str, str]] = []
        self.answer = Answer(covered=True, answer="It uses pgvector inside Postgres [1].")
        self.fail = False

    def structured(self, prompt, schema, **kw):
        if self.fail:
            raise LLMError("down")
        self.structured_prompts.append(prompt)
        return self.answer

    def text(self, prompt, **kw):
        system = kw.get("system") or ""
        self.text_prompts.append((system, prompt))
        if "standalone question" in system:
            return "Why was pgvector chosen as the vector database?"
        return "SUMMARY-OF-EARLIER-CHAT"


@pytest.fixture()
def llm(monkeypatch):
    f = FakeLLM()
    monkeypatch.setattr(product_assistant, "generate_structured", f.structured)
    monkeypatch.setattr(product_assistant, "generate_text", f.text)
    monkeypatch.setattr(embeddings, "embed_documents", lambda texts: [_fake_vec(t) for t in texts])
    monkeypatch.setattr(product_assistant, "embed_query", _fake_vec)
    # Fake embeddings are not calibrated, so disable the threshold here; it is tested separately.
    monkeypatch.setattr(product_assistant, "MIN_SCORE", -1.0)
    return f


@pytest.fixture()
def auth(register):
    def _auth(email="a@example.com"):
        return bearer(register(email=email).json()["access_token"])

    return _auth


def new_session(client, h):
    return client.post(f"{BASE}/sessions", headers=h).json()["id"]


def ask(client, h, sid, text):
    return client.post(f"{BASE}/sessions/{sid}/messages", headers=h, json={"content": text})


# ---------- the document and its ingestion ----------

def test_document_has_the_required_sections():
    titles = " | ".join(s.title for s in parse_sections(DOC_PATH.read_text(encoding="utf-8")))
    for needed in ("Overview", "Features", "How to Use", "Architecture", "Tech Stack"):
        assert needed in titles
    assert "Why each technology was chosen" in titles


def test_parse_sections_paths_and_code_blocks():
    md = "# T\n\n## A\nintro\n\n### A1\nbody1\n\n## B\n```\n## not a heading\n```\n"
    secs = parse_sections(md)
    assert [s.title for s in secs] == ["A", "A > A1", "B"]
    assert "## not a heading" in secs[2].body


def test_ingest_is_idempotent(db_session_factory, monkeypatch):
    monkeypatch.setattr(embeddings, "embed_documents", lambda texts: [_fake_vec(t) for t in texts])
    with db_session_factory() as db:
        first = product_kb.ingest(db)
        assert first["updated"] == first["sections"] > 20
        second = product_kb.ingest(db)
        assert second["updated"] == 0 and second["removed"] == 0


# ---------- sessions and isolation ----------

def test_requires_auth(client):
    assert client.get(f"{BASE}/sessions").status_code == 401
    assert client.post(f"{BASE}/sessions").status_code == 401


def test_session_lifecycle_and_title(client, auth, llm):
    h = auth()
    sid = new_session(client, h)
    assert client.get(f"{BASE}/sessions", headers=h).json()[0]["title"] == "New chat"
    r = ask(client, h, sid, "Why did you choose pgvector?")
    assert r.status_code == 200
    body = r.json()
    assert body["session"]["title"] == "Why did you choose pgvector?"
    assert body["user_message"]["role"] == "user" and body["assistant_message"]["role"] == "assistant"
    detail = client.get(f"{BASE}/sessions/{sid}", headers=h).json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert client.delete(f"{BASE}/sessions/{sid}", headers=h).status_code == 204
    assert client.get(f"{BASE}/sessions/{sid}", headers=h).status_code == 404


def test_users_cannot_touch_each_others_sessions(client, auth, llm):
    a, b = auth("a@example.com"), auth("b@example.com")
    sid = new_session(client, a)
    ask(client, a, sid, "How does resume parsing work?")
    assert client.get(f"{BASE}/sessions/{sid}", headers=b).status_code == 404
    assert ask(client, b, sid, "hello there").status_code == 404
    assert client.delete(f"{BASE}/sessions/{sid}", headers=b).status_code == 404
    assert client.get(f"{BASE}/sessions", headers=b).json() == []
    # and nothing of A's chat was changed by B's attempts
    assert len(client.get(f"{BASE}/sessions/{sid}", headers=a).json()["messages"]) == 2


def test_sessions_of_one_user_do_not_share_history(client, auth, llm):
    h = auth()
    s1, s2 = new_session(client, h), new_session(client, h)
    ask(client, h, s1, "SECRET-TOPIC-ALPHA question about features")
    ask(client, h, s2, "A different question about architecture")
    assert "SECRET-TOPIC-ALPHA" not in llm.structured_prompts[-1]
    assert llm.text_prompts == []  # first turn of a session never needs question rewriting


def test_career_sessions_are_invisible_to_the_product_assistant(client, auth, llm, db_session_factory):
    h = auth()
    with db_session_factory() as db:
        user = db.scalar(select(User).where(User.email == "a@example.com"))
        career = chat_repo.create_session(db, user.id, "career", "career chat")
    assert client.get(f"{BASE}/sessions", headers=h).json() == []
    assert client.get(f"{BASE}/sessions/{career.id}", headers=h).status_code == 404
    assert ask(client, h, str(career.id), "hi there").status_code == 404


# ---------- the RAG + memory flow ----------

def test_answer_has_citations_only_for_sections_used(client, auth, llm):
    h = auth()
    sid = new_session(client, h)
    llm.answer = Answer(covered=True, answer="Resume parsing uses Gemini [2].")
    body = ask(client, h, sid, "How does resume parsing work with Gemini?").json()
    cites = body["assistant_message"]["citations"]
    assert [c["n"] for c in cites] == [2]
    assert cites[0]["title"] and cites[0]["snippet"]
    # the stored message keeps its citations when reloaded
    again = client.get(f"{BASE}/sessions/{sid}", headers=h).json()["messages"][1]
    assert again["citations"][0]["n"] == 2


def test_followup_is_rewritten_using_history(client, auth, llm, monkeypatch):
    h = auth()
    sid = new_session(client, h)
    searched: list[str] = []
    monkeypatch.setattr(product_assistant, "embed_query", lambda q: searched.append(q) or _fake_vec(q))
    ask(client, h, sid, "What vector database does the product use?")
    ask(client, h, sid, "Why did we use it?")
    assert searched[0] == "What vector database does the product use?"
    assert searched[1] == "Why was pgvector chosen as the vector database?"  # reference resolved
    _, prompt = llm.text_prompts[0]
    assert "What vector database does the product use?" in prompt and "Why did we use it?" in prompt
    # the answer prompt also carries recent history
    assert "What vector database does the product use?" in llm.structured_prompts[-1]


def test_nothing_relevant_gives_not_found_without_calling_the_llm(client, auth, llm, monkeypatch):
    monkeypatch.setattr(product_assistant, "MIN_SCORE", 2.0)  # nothing can pass
    h = auth()
    body = ask(client, h, new_session(client, h), "What is the capital of France?").json()
    assert body["assistant_message"]["content"] == NOT_FOUND_REPLY
    assert body["assistant_message"]["citations"] == []
    assert llm.structured_prompts == []


def test_model_saying_not_covered_gives_not_found(client, auth, llm):
    llm.answer = Answer(covered=False, answer="")
    h = auth()
    body = ask(client, h, new_session(client, h), "how do I reset my password").json()
    assert body["assistant_message"]["content"] == NOT_FOUND_REPLY and body["assistant_message"]["citations"] == []


def test_llm_failure_is_503_and_stores_nothing(client, auth, llm, db_session_factory):
    llm.fail = True
    h = auth()
    sid = new_session(client, h)
    assert ask(client, h, sid, "How does resume parsing work?").status_code == 503
    with db_session_factory() as db:
        assert db.scalar(select(ChatMessage.id).limit(1)) is None


def test_embedding_failure_is_503(client, auth, llm, monkeypatch):
    def boom(q):
        raise embeddings.EmbeddingError("down")

    monkeypatch.setattr(product_assistant, "embed_query", boom)
    h = auth()
    assert ask(client, h, new_session(client, h), "How does resume parsing work?").status_code == 503


def test_condense_failure_falls_back_to_raw_question(client, auth, llm, monkeypatch):
    h = auth()
    sid = new_session(client, h)
    ask(client, h, sid, "What vector database does the product use?")

    def fail(*a, **k):
        raise LLMError("down")

    monkeypatch.setattr(product_assistant, "generate_text", fail)
    assert ask(client, h, sid, "Why did we use it?").status_code == 200


def test_long_history_is_summarised_and_used(client, auth, llm, monkeypatch):
    monkeypatch.setattr(product_assistant, "SUMMARIZE_AFTER", 4)
    monkeypatch.setattr(product_assistant, "KEEP_RECENT", 2)
    h = auth()
    sid = new_session(client, h)
    for i in range(4):
        assert ask(client, h, sid, f"Question number {i} about features").status_code == 200
    ask(client, h, sid, "One more question about security")
    assert "SUMMARY-OF-EARLIER-CHAT" in llm.structured_prompts[-1]


# ---------- validation and feedback ----------

def test_message_validation(client, auth, llm):
    h = auth()
    sid = new_session(client, h)
    assert ask(client, h, sid, "   ").status_code == 422
    assert ask(client, h, sid, "x" * 2001).status_code == 422


def test_feedback_roundtrip_and_isolation(client, auth, llm):
    a, b = auth("a@example.com"), auth("b@example.com")
    sid = new_session(client, a)
    mid = ask(client, a, sid, "How does resume parsing work?").json()["assistant_message"]["id"]
    assert client.put(f"{BASE}/messages/{mid}/feedback", headers=a, json={"rating": 1}).json()["rating"] == 1
    assert client.put(f"{BASE}/messages/{mid}/feedback", headers=a, json={"rating": -1}).status_code == 200
    msgs = client.get(f"{BASE}/sessions/{sid}", headers=a).json()["messages"]
    assert msgs[1]["rating"] == -1 and msgs[0]["rating"] is None
    assert client.put(f"{BASE}/messages/{mid}/feedback", headers=b, json={"rating": 1}).status_code == 404
    assert client.put(f"{BASE}/messages/{mid}/feedback", headers=a, json={"rating": 5}).status_code == 422
    # user messages cannot be rated
    uid = msgs[0]["id"]
    assert client.put(f"{BASE}/messages/{uid}/feedback", headers=a, json={"rating": 1}).status_code == 404
