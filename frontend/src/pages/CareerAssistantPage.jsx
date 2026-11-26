import RichText from "../components/RichText.jsx";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, errorMessage } from "../api/client.js";

const BASE = "/chat/career";
const EXAMPLES = [
  "Find internships that fit me and add the top one to my tracker",
  "What skills am I missing for backend developer roles?",
  "How am I doing with my applications?",
  "Give me interview questions for a data analyst internship",
];
const TOOL_LABEL = {
  get_profile: "Read your profile",
  search_internships: "Searched internships",
  rank_matches: "Ranked your matches",
  score_match: "Scored a match",
  skill_gap: "Analysed skill gap",
  interview_questions: "Created interview questions",
  list_applications: "Read your tracker",
  propose_track: "Prepared a tracker change",
  propose_status: "Prepared a status change",
};

function Steps({ steps }) {
  if (!steps?.length) return null;
  return (
    <details className="sources">
      <summary>
        Used {steps.length} tool{steps.length > 1 ? "s" : ""}
      </summary>
      <ul>
        {steps.map((s, i) => (
          <li key={i}>
            <strong className={s.ok ? "" : "warn"}>{TOOL_LABEL[s.tool] || s.tool}</strong>
            {Object.keys(s.args).length > 0 && (
              <span className="muted small"> ({Object.entries(s.args).map(([k, v]) => `${k}: ${v}`).join(", ")})</span>
            )}
            {s.summary && <div className="muted small">{s.summary}</div>}
          </li>
        ))}
      </ul>
    </details>
  );
}

function Action({ a, onResolve, busy }) {
  return (
    <div className={`proposal state-${a.state}`}>
      <div>{a.label}</div>
      {a.state === "pending" ? (
        <div className="actions">
          <button className="btn btn-primary small" disabled={busy} onClick={() => onResolve(a, "confirm")}>
            Confirm
          </button>
          <button className="btn btn-ghost small" disabled={busy} onClick={() => onResolve(a, "cancel")}>
            Cancel
          </button>
        </div>
      ) : (
        <div className="small">
          {a.state === "done" ? "✓ " : a.state === "failed" ? "⚠ " : ""}
          {a.result}
          {a.state === "done" && (
            <>
              {" "}
              <Link to="/applications">Open tracker</Link>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function Message({ m, onRate, onResolve, busyAction }) {
  const mine = m.role === "user";
  return (
    <div className={`msg ${mine ? "msg-user" : "msg-bot"}`}>
      <div className="msg-body">{m.role === "user" ? m.content : <RichText text={m.content} />}</div>
      {!mine && (
        <>
          {m.actions?.map((a) => (
            <Action key={a.id} a={a} busy={busyAction === `${m.id}/${a.id}`} onResolve={(act, d) => onResolve(m, act, d)} />
          ))}
          <Steps steps={m.steps} />
          <div className="rate">
            <button className={`icon ${m.rating === 1 ? "ok" : ""}`} onClick={() => onRate(m, 1)} aria-label="Helpful" aria-pressed={m.rating === 1} title="Helpful">
              👍
            </button>
            <button className={`icon ${m.rating === -1 ? "no" : ""}`} onClick={() => onRate(m, -1)} aria-label="Not helpful" aria-pressed={m.rating === -1} title="Not helpful">
              👎
            </button>
          </div>
        </>
      )}
    </div>
  );
}

export default function CareerAssistantPage() {
  const [sessions, setSessions] = useState(null);
  const [activeId, setActiveId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [loadingChat, setLoadingChat] = useState(false);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [busyAction, setBusyAction] = useState(null);
  const [error, setError] = useState("");
  const endRef = useRef(null);
  const openReq = useRef(0);

  const loadSessions = useCallback(async () => {
    try {
      const { data } = await api.get(`${BASE}/sessions`);
      setSessions(data);
      return data;
    } catch (err) {
      setError(errorMessage(err, "Could not load your chats."));
      setSessions([]);
      return [];
    }
  }, []);

  const open = useCallback(async (id) => {
    const req = ++openReq.current;
    setActiveId(id);
    setError("");
    setMessages([]);
    if (!id) return;
    setLoadingChat(true);
    try {
      const { data } = await api.get(`${BASE}/sessions/${id}`);
      if (req === openReq.current) setMessages(data.messages);
    } catch (err) {
      if (req === openReq.current) setError(errorMessage(err, "Could not open that chat."));
    } finally {
      if (req === openReq.current) setLoadingChat(false);
    }
  }, []);

  useEffect(() => {
    loadSessions().then((list) => list[0] && open(list[0].id));
  }, [loadSessions, open]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, sending]);

  async function newChat() {
    setError("");
    try {
      const { data } = await api.post(`${BASE}/sessions`, {});
      setSessions((s) => [data, ...(s || [])]);
      openReq.current++;
      setActiveId(data.id);
      setMessages([]);
    } catch (err) {
      setError(errorMessage(err, "Could not start a chat."));
    }
  }

  async function removeChat(s) {
    if (!window.confirm(`Delete "${s.title}"? This cannot be undone.`)) return;
    try {
      await api.delete(`${BASE}/sessions/${s.id}`);
      const list = (sessions || []).filter((x) => x.id !== s.id);
      setSessions(list);
      if (s.id === activeId) open(list[0]?.id || null);
    } catch (err) {
      setError(errorMessage(err, "Could not delete the chat."));
    }
  }

  async function send(text) {
    const content = (text ?? input).trim();
    if (!content || sending) return;
    setError("");
    let sid = activeId;
    if (!sid) {
      try {
        const { data } = await api.post(`${BASE}/sessions`, {});
        sid = data.id;
        setSessions((s) => [data, ...(s || [])]);
        setActiveId(sid);
      } catch (err) {
        return setError(errorMessage(err, "Could not start a chat."));
      }
    }
    const pending = { id: `pending-${Date.now()}`, role: "user", content };
    setMessages((m) => [...m, pending]);
    setInput("");
    setSending(true);
    try {
      // Up to 5 model calls plus tools: allow more time than a normal request.
      const { data } = await api.post(`${BASE}/sessions/${sid}/messages`, { content }, { timeout: 180000 });
      setMessages((m) => [...m.filter((x) => x.id !== pending.id), data.user_message, data.assistant_message]);
      setSessions((s) => [data.session, ...(s || []).filter((x) => x.id !== sid)]);
    } catch (err) {
      setMessages((m) => m.filter((x) => x.id !== pending.id));
      setInput(content);
      setError(errorMessage(err, "The assistant could not answer. Please try again."));
    } finally {
      setSending(false);
    }
  }

  async function resolve(m, a, decision) {
    setBusyAction(`${m.id}/${a.id}`);
    setError("");
    try {
      const { data } = await api.post(`${BASE}/messages/${m.id}/actions/${a.id}`, { decision });
      setMessages((list) => list.map((x) => (x.id === m.id ? data : x)));
    } catch (err) {
      setError(errorMessage(err, "Could not apply that action."));
      if (err.response?.status === 409) open(activeId); // already resolved elsewhere: show the real state
    } finally {
      setBusyAction(null);
    }
  }

  async function rate(m, rating) {
    try {
      await api.put(`${BASE}/messages/${m.id}/feedback`, { rating });
      setMessages((list) => list.map((x) => (x.id === m.id ? { ...x, rating } : x)));
    } catch (err) {
      setError(errorMessage(err, "Could not save your feedback."));
    }
  }

  return (
    <div className="stack-lg">
      <div>
        <h1>Career Assistant</h1>
        <p className="muted">
          Ask about your matches, skill gaps, interview practice and applications. It works only from your own data and the tools of this app, and
          it asks before changing your tracker. For questions about how the app works, use the <Link to="/product-assistant">Product Assistant</Link>.
        </p>
      </div>
      <div className="chat-layout">
        <aside className="card chat-sessions">
          <button className="btn btn-primary" onClick={newChat}>
            New chat
          </button>
          {sessions === null ? (
            <p className="muted small">Loading…</p>
          ) : sessions.length === 0 ? (
            <p className="muted small">No chats yet.</p>
          ) : (
            <ul className="session-list">
              {sessions.map((s) => (
                <li key={s.id} className={s.id === activeId ? "active" : ""}>
                  <button className="session-btn" onClick={() => open(s.id)} title={s.title}>
                    {s.title}
                  </button>
                  <button className="icon no" onClick={() => removeChat(s)} aria-label={`Delete ${s.title}`}>
                    ✕
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>

        <section className="card chat-main">
          <div className="chat-scroll" aria-live="polite">
            {loadingChat && <p className="muted">Loading chat…</p>}
            {!loadingChat && messages.length === 0 && (
              <div className="stack">
                <p className="muted">Try one of these:</p>
                <div className="actions">
                  {EXAMPLES.map((q) => (
                    <button key={q} className="btn btn-ghost small" onClick={() => send(q)} disabled={sending}>
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((m) => (
              <Message key={m.id} m={m} onRate={rate} onResolve={resolve} busyAction={busyAction} />
            ))}
            {sending && <div className="msg msg-bot muted">Working on it… (this can take a few steps)</div>}
            <div ref={endRef} />
          </div>
          {error && <div className="alert">{error}</div>}
          <form
            className="chat-input"
            onSubmit={(e) => {
              e.preventDefault();
              send();
            }}
          >
            <textarea
              rows={2}
              value={input}
              maxLength={2000}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
              placeholder="e.g. Which internships fit me best, and what am I missing for them?"
              aria-label="Your message"
            />
            <button className="btn btn-primary" disabled={sending || !input.trim()}>
              {sending ? "Sending…" : "Send"}
            </button>
          </form>
        </section>
      </div>
    </div>
  );
}
