import RichText from "../components/RichText.jsx";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, errorMessage } from "../api/client.js";

const BASE = "/chat/product";
const EXAMPLES = [
  "How does resume parsing work?",
  "What is the difference between extracted and verified skills?",
  "Why was pgvector chosen?",
  "Which features are not available yet?",
];

function Citations({ citations }) {
  if (!citations?.length) return null;
  return (
    <details className="sources">
      <summary>
        {citations.length} source{citations.length > 1 ? "s" : ""}
      </summary>
      <ul>
        {citations.map((c) => (
          <li key={c.n}>
            <strong>
              [{c.n}] {c.title}
            </strong>
            <div className="muted small">…{c.snippet}…</div>
          </li>
        ))}
      </ul>
    </details>
  );
}

function Message({ m, onRate }) {
  const mine = m.role === "user";
  return (
    <div className={`msg ${mine ? "msg-user" : "msg-bot"}`}>
      <div className="msg-body">{m.role === "user" ? m.content : <RichText text={m.content} />}</div>
      {!mine && (
        <>
          <Citations citations={m.citations} />
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

export default function ProductAssistantPage() {
  const [sessions, setSessions] = useState(null);
  const [activeId, setActiveId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [loadingChat, setLoadingChat] = useState(false);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
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
    const pending = { id: `pending-${Date.now()}`, role: "user", content, citations: [] };
    setMessages((m) => [...m, pending]);
    setInput("");
    setSending(true);
    try {
      const { data } = await api.post(`${BASE}/sessions/${sid}/messages`, { content }, { timeout: 120000 });
      setMessages((m) => [...m.filter((x) => x.id !== pending.id), data.user_message, data.assistant_message]);
      setSessions((s) => [data.session, ...(s || []).filter((x) => x.id !== sid)]);
    } catch (err) {
      setMessages((m) => m.filter((x) => x.id !== pending.id));
      setInput(content); // give the question back so nothing is lost
      setError(errorMessage(err, "The assistant could not answer. Please try again."));
    } finally {
      setSending(false);
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
        <h1>Product Assistant</h1>
        <p className="muted">Ask how Career Companion works. Answers come only from the product documentation and cite the sections used.</p>
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
              <Message key={m.id} m={m} onRate={rate} />
            ))}
            {sending && <div className="msg msg-bot muted">Thinking…</div>}
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
              placeholder="Ask about features, how to use the app, architecture or the tech stack…"
              aria-label="Your question"
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
