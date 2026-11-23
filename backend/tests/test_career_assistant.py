import hashlib
import math
import re

import pytest
from sqlalchemy import func, select

from app.llm import LLMError
from app.models import Application, ChatMessage, InterviewSession
from app.rag import embeddings
from app.schemas.interview import QuestionLLM, QuestionsLLM
from app.services import career_assistant, internship_service, interview_service, matching_service
from app.services.career_assistant import AgentStep, FinalReply
from tests.conftest import bearer

BASE = "/api/chat/career"
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _fake_vec(text: str) -> list[float]:
    v = [0.0] * embeddings.DIM
    for w in re.findall(r"[a-z0-9+#]+", text.lower()):
        v[int(hashlib.md5(w.encode()).hexdigest(), 16) % embeddings.DIM] += 1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


class ScriptedLLM:
    """Returns AgentSteps from a script, recording every prompt the agent sent."""

    def __init__(self):
        self.script: list[AgentStep] = []
        self.prompts: list[str] = []
        self.final_calls = 0
        self.fail = False

    def structured(self, prompt, schema, **kw):
        if self.fail:
            raise LLMError("The AI service is rate-limited right now. Please try again in a minute.")
        self.prompts.append(prompt)
        if schema is FinalReply:
            self.final_calls += 1
            return FinalReply(reply="Here is what I found so far.")
        assert schema is AgentStep
        return self.script.pop(0) if self.script else AgentStep(action="respond", reply="Done.")

    def text(self, prompt, **kw):
        return "SUMMARY"


def tool(name, **kw):
    return AgentStep(action="tool", tool=name, **kw)


def respond(text):
    return AgentStep(action="respond", reply=text)


@pytest.fixture()
def llm(monkeypatch):
    f = ScriptedLLM()
    monkeypatch.setattr(career_assistant, "generate_structured", f.structured)
    monkeypatch.setattr(career_assistant, "generate_text", f.text)
    monkeypatch.setattr(embeddings, "embed_documents", lambda texts: [_fake_vec(t) for t in texts])
    monkeypatch.setattr(internship_service, "embed_query", _fake_vec)
    monkeypatch.setattr(matching_service, "ROLE_MIN_SIMILARITY", -1.0)
    return f


@pytest.fixture()
def seeded(db_session_factory):
    with db_session_factory() as db:
        internship_service.seed_samples(db)


@pytest.fixture()
def auth(register):
    def _auth(email="a@example.com"):
        return bearer(register(email=email).json()["access_token"])

    return _auth


def new_chat(client, h):
    r = client.post(f"{BASE}/sessions", headers=h)
    assert r.status_code == 201
    return r.json()["id"]


def say(client, h, sid, text):
    return client.post(f"{BASE}/sessions/{sid}/messages", headers=h, json={"content": text})


def verify(client, h, *names):
    for n in names:
        assert client.post("/api/skills", headers=h, json={"name": n}).status_code == 201


def count(db_session_factory, model):
    with db_session_factory() as db:
        return db.scalar(select(func.count()).select_from(model))


# ---------- separation and isolation ----------

def test_requires_auth(client):
    assert client.get(f"{BASE}/sessions").status_code == 401


def test_career_and_product_chats_are_separate(client, auth, llm):
    h = auth()
    product_sid = client.post("/api/chat/product/sessions", headers=h).json()["id"]
    career_sid = new_chat(client, h)
    assert client.get(f"{BASE}/sessions/{product_sid}", headers=h).status_code == 404
    assert say(client, h, product_sid, "hi").status_code == 404
    assert client.get(f"/api/chat/product/sessions/{career_sid}", headers=h).status_code == 404
    assert [s["id"] for s in client.get(f"{BASE}/sessions", headers=h).json()] == [career_sid]


def test_other_user_cannot_read_or_post(client, auth, llm):
    h, other = auth(), auth("b@example.com")
    sid = new_chat(client, h)
    assert client.get(f"{BASE}/sessions/{sid}", headers=other).status_code == 404
    assert say(client, other, sid, "hi").status_code == 404
    assert client.delete(f"{BASE}/sessions/{sid}", headers=other).status_code == 404


# ---------- the agent loop ----------

def test_find_and_track_top_match_needs_confirmation(client, auth, seeded, llm, db_session_factory):
    """The Phase 7 check: 'find internships that fit me and add the top one to my tracker'."""
    h = auth()
    verify(client, h, "Python", "FastAPI", "SQL", "Git")
    sid = new_chat(client, h)
    llm.script = [tool("rank_matches"), tool("propose_track", internship="I1"),
                  respond("Your best fit is I1 (score above). I proposed adding (I1) to your tracker.")]
    r = say(client, h, sid, "Find internships that fit me and add the top one to my tracker")
    assert r.status_code == 200, r.text
    msg = r.json()["assistant_message"]

    top = client.get("/api/matching?limit=1", headers=h).json()["items"][0]
    label = f"{top['title']} at {top['company']}"
    assert [s["tool"] for s in msg["steps"]] == ["rank_matches", "propose_track"] and all(s["ok"] for s in msg["steps"])
    assert "I1" not in msg["content"] and label in msg["content"]  # codes replaced by names
    assert msg["actions"] == [{"id": "act1", "kind": "track", "state": "pending", "result": None,
                               "label": f"Add '{top['title']}' at {top['company']} to your tracker as Saved"}]
    assert count(db_session_factory, Application) == 0  # nothing written before the click
    # The model only ever saw codes, never database ids.
    assert not any(UUID_RE.search(p) for p in llm.prompts)
    assert "I1: " in llm.prompts[1] and "score" in llm.prompts[1]

    url = f"{BASE}/messages/{msg['id']}/actions/act1"
    done = client.post(url, headers=h, json={"decision": "confirm"})
    assert done.status_code == 200
    assert done.json()["actions"][0]["state"] == "done"
    assert done.json()["steps"][1]["summary"] == "Proposed: " + msg["actions"][0]["label"] + "."  # no model-only text
    apps = client.get("/api/applications", headers=h).json()["items"]
    assert [(a["company"], a["role"], a["status"]) for a in apps] == [(top["company"], top["title"], "saved")]

    assert client.post(url, headers=h, json={"decision": "confirm"}).status_code == 409  # only once
    assert client.post(url, headers=h, json={"decision": "cancel"}).status_code == 409
    # Reloading the chat shows the resolved state.
    stored = client.get(f"{BASE}/sessions/{sid}", headers=h).json()["messages"][1]
    assert stored["actions"][0]["state"] == "done"


def test_cancel_changes_nothing_and_other_users_cannot_confirm(client, auth, seeded, llm, db_session_factory):
    h, other = auth(), auth("b@example.com")
    sid = new_chat(client, h)
    llm.script = [tool("search_internships", query="data analyst"), tool("propose_track", internship="I1"), respond("Proposed.")]
    msg = say(client, h, sid, "track a data analyst internship").json()["assistant_message"]
    url = f"{BASE}/messages/{msg['id']}/actions/act1"
    assert client.post(url, headers=other, json={"decision": "confirm"}).status_code == 404
    assert client.post(f"{BASE}/messages/{msg['id']}/actions/act9", headers=h, json={"decision": "confirm"}).status_code == 404
    r = client.post(url, headers=h, json={"decision": "cancel"})
    assert r.json()["actions"][0]["state"] == "cancelled"
    assert count(db_session_factory, Application) == 0


def test_unknown_code_and_bad_arguments_become_observations(client, auth, seeded, llm):
    h = auth()
    sid = new_chat(client, h)
    llm.script = [tool("propose_track", internship="I7"), tool("search_internships"), respond("I couldn't find that.")]
    msg = say(client, h, sid, "add that one").json()["assistant_message"]
    assert [s["ok"] for s in msg["steps"]] == [False, False]
    assert msg["actions"] == []
    assert "Unknown internship code 'I7'" in llm.prompts[1]
    assert "needs a query" in llm.prompts[2]


def test_tool_steps_are_capped(client, auth, seeded, llm):
    h = auth()
    sid = new_chat(client, h)
    llm.script = [tool("get_profile"), tool("list_applications"), tool("rank_matches"), tool("get_profile"),
                  tool("get_profile"), tool("get_profile")]
    msg = say(client, h, sid, "loop forever").json()["assistant_message"]
    assert len(msg["steps"]) == career_assistant.MAX_TOOL_STEPS
    assert llm.final_calls == 1 and "No tool calls left" in llm.prompts[-1]
    assert msg["content"] == "Here is what I found so far."


def test_llm_failure_stores_nothing(client, auth, llm, db_session_factory):
    h = auth()
    sid = new_chat(client, h)
    llm.fail = True
    r = say(client, h, sid, "hello")
    assert r.status_code == 503 and "rate-limited" in r.json()["detail"]
    assert count(db_session_factory, ChatMessage) == 0


def test_codes_persist_across_turns_and_status_change(client, auth, seeded, llm, db_session_factory):
    h = auth()
    item = client.get("/api/internships?limit=1", headers=h).json()["items"][0]
    client.post("/api/applications", headers=h, json={"internship_id": item["id"], "status": "applied"})
    sid = new_chat(client, h)
    llm.script = [tool("list_applications"), respond("You have one application.")]
    say(client, h, sid, "what have I applied to?")

    # Next turn: the model refers to A1 from the previous turn's tool result.
    llm.script = [tool("propose_status", application="A1", status="interview", note="HR call"), respond("Proposed the move.")]
    msg = say(client, h, sid, "I got an interview for it").json()["assistant_message"]
    assert "A1 = " in llm.prompts[-2]  # known items carried over
    assert "Recent conversation" in llm.prompts[-2] and "You have one application." in llm.prompts[-2]
    action = msg["actions"][0]
    assert action["kind"] == "status" and "from Applied to Interview" in action["label"]

    client.post(f"{BASE}/messages/{msg['id']}/actions/act1", headers=h, json={"decision": "confirm"})
    app = client.get("/api/applications", headers=h).json()["items"][0]
    detail = client.get(f"/api/applications/{app['id']}", headers=h).json()
    assert detail["status"] == "interview" and detail["events"][-1]["note"] == "HR call"

    # A third turn's history shows the action outcome to the model.
    llm.script = [respond("Good luck!")]
    say(client, h, sid, "thanks")
    assert "Proposed action:" in llm.prompts[-1] and "- done" in llm.prompts[-1]


def test_confirm_reports_failure_when_already_tracked(client, auth, seeded, llm):
    h = auth()
    sid = new_chat(client, h)
    llm.script = [tool("search_internships", query="backend python"), tool("propose_track", internship="I1"), respond("ok")]
    msg = say(client, h, sid, "track it").json()["assistant_message"]
    # The student adds it by hand before clicking Confirm.
    item_title = msg["actions"][0]["label"].split("'")[1]
    item = next(i for i in client.get("/api/internships?limit=100", headers=h).json()["items"] if i["title"] == item_title)
    client.post("/api/applications", headers=h, json={"internship_id": item["id"]})
    r = client.post(f"{BASE}/messages/{msg['id']}/actions/act1", headers=h, json={"decision": "confirm"})
    assert r.status_code == 200
    assert r.json()["actions"][0]["state"] == "failed" and "already in your tracker" in r.json()["actions"][0]["result"]


def test_already_tracked_is_not_proposed_again(client, auth, seeded, llm):
    h = auth()
    sid = new_chat(client, h)
    llm.script = [tool("search_internships", query="backend python"), respond("Found some.")]
    say(client, h, sid, "find backend internships")
    title = llm.prompts[1].split("I1: ")[1].split(" at ")[0]
    item = next(i for i in client.get("/api/internships?limit=100", headers=h).json()["items"] if i["title"] == title)
    client.post("/api/applications", headers=h, json={"internship_id": item["id"]})

    llm.script = [tool("propose_track", internship="I1"), respond("It is already tracked.")]
    msg = say(client, h, sid, "track the first one").json()["assistant_message"]
    assert msg["actions"] == [] and "Already tracked as A1 with status Saved" in llm.prompts[-1]


def test_skill_gap_and_score_tools_use_the_deterministic_services(client, auth, seeded, llm):
    h = auth()
    verify(client, h, "Python")
    sid = new_chat(client, h)
    llm.script = [tool("search_internships", query="backend python"), tool("score_match", internship="I1"),
                  tool("skill_gap", query="Backend developer"), respond("Summary.")]
    say(client, h, sid, "how do I fit backend roles?")
    first = llm.prompts[1].split("I1: ")[1].split(" |")[0]
    item = next(i for i in client.get("/api/internships?limit=100", headers=h).json()["items"]
                if first.startswith(i["title"]))
    expected = client.get(f"/api/matching/{item['id']}", headers=h).json()["overall"]
    assert f"score {expected:.1f}/100" in llm.prompts[2]
    assert "Target: Backend developer" in llm.prompts[3] and "Critical gaps:" in llm.prompts[3]


def test_interview_tool_creates_practice_session(client, auth, seeded, llm, monkeypatch, db_session_factory):
    h = auth()
    qs = [QuestionLLM(question=f"Question number {n} about APIs?", category="technical", difficulty="easy") for n in range(5)]
    monkeypatch.setattr(interview_service, "generate_structured", lambda *a, **k: QuestionsLLM(questions=qs))
    sid = new_chat(client, h)
    llm.script = [tool("interview_questions", query="Backend intern"), respond("I created 5 questions.")]
    msg = say(client, h, sid, "give me interview questions").json()["assistant_message"]
    assert msg["steps"][0]["ok"] and "Interview Prep page" in msg["steps"][0]["summary"]
    assert count(db_session_factory, InterviewSession) == 1
    assert "Question number 0 about APIs?" in llm.prompts[1]


def test_reply_links_are_removed_and_title_set(client, auth, llm):
    h = auth()
    sid = new_chat(client, h)
    llm.script = [respond("See https://example.com/jobs for more.")]
    r = say(client, h, sid, "Where can I find more internships?").json()
    assert "http" not in r["assistant_message"]["content"]
    assert r["session"]["title"] == "Where can I find more internships?"


def test_feedback_on_career_message(client, auth, llm):
    h = auth()
    sid = new_chat(client, h)
    llm.script = [respond("Hi!")]
    mid = say(client, h, sid, "hello").json()["assistant_message"]["id"]
    assert client.put(f"{BASE}/messages/{mid}/feedback", headers=h, json={"rating": 1}).json()["rating"] == 1
    # Not reachable through the Product Assistant router.
    assert client.put(f"/api/chat/product/messages/{mid}/feedback", headers=h, json={"rating": 1}).status_code == 404
