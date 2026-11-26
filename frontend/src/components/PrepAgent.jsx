import { useCallback, useEffect, useRef, useState } from "react";
import { api, errorMessage } from "../api/client.js";
import RichText from "./RichText.jsx";

const BASE = "/chat/interview";
const MAX_BYTES = 5 * 1024 * 1024;

const SUGGESTIONS = [
  "Which role can I apply for?",
  "Which internship is suitable for my skills?",
  "What are my strongest technical skills?",
  "Give me technical and HR interview questions for my best-fit role",
  "How should I answer 'Tell me about yourself'?",
  "Make me a 4-week interview preparation roadmap",
  "What topics should I prepare, and what learning path do you recommend?",
];

const DOC_SUGGESTIONS = [
  "Summarise the uploaded document",
  "Generate 5 interview questions with answers from the document",
];

// Interview Prep Agent: a chat that uses your resume data to recommend roles and prepare you for interviews,
// and answers questions about documents you upload to the chat.
export default function PrepAgent() {
  const [sessions, setSessions] = useState(null);
  const [activeId, setActiveId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const fileRef = useRef(null);
  const endRef = useRef(null);

  const loadSessions = useCallback(async () => {
    try {
      const { data } = await api.get(`${BASE}/sessions`);
      setSessions(data);
    } catch (err) {
      setError(errorMessage(err, "Could not load your chats."));
      setSessions([]);
    }
  }, []);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, busy]);

  async function open(id) {
    setError("");
    try {
      const { data } = await api.get(`${BASE}/sessions/${id}`);
      setActiveId(id);
      setMessages(data.messages);
      setDocuments(data.documents);
    } catch (err) {
      setError(errorMessage(err, "Could not open that chat."));
    }
  }

  function newChat() {
    setActiveId(null);
    setMessages([]);
    setDocuments([]);
    setText("");
    setError("");
  }

  async function ensureSession() {
    if (activeId) return activeId;
    const { data } = await api.post(`${BASE}/sessions`, {});
    setActiveId(data.id);
    return data.id;
  }

  async function send(content) {
    const question = (content ?? text).trim();
    if (!question || busy) return;
    setBusy(true);
    setError("");
    setText("");
    const optimistic = { id: `tmp-${Date.now()}`, role: "user", content: question, citations: [] };
    setMessages((m) => [...m, optimistic]);
    try {
      const sid = await ensureSession();
      const { data } = await api.post(`${BASE}/sessions/${sid}/messages`, { content: question }, { timeout: 120000 });
      setMessages((m) => [...m.filter((x) => x.id !== optimistic.id), data.user_message, data.assistant_message]);
      loadSessions();
    } catch (err) {
      setMessages((m) => m.filter((x) => x.id !== optimistic.id));
      setText(question); // keep the question so it can be sent again
      setError(errorMessage(err, "Could not get an answer."));
    } finally {
      setBusy(false);
    }
  }

  async function onFile(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setError("");
    if (!/\.(pdf|docx)$/i.test(file.name)) return setError("Only PDF and DOCX files are supported.");
    if (file.size > MAX_BYTES) return setError("The file is larger than 5 MB.");
    setUploading(true);
    try {
      const sid = await ensureSession();
      const body = new FormData();
      body.append("file", file);
      const { data } = await api.post(`${BASE}/sessions/${sid}/documents`, body, { timeout: 120000 });
      setDocuments((d) => [...d, data]);
      loadSessions();
    } catch (err) {
      setError(errorMessage(err, "Upload failed."));
    } finally {
      setUploading(false);
    }
  }

  async function removeDoc(doc) {
    try {
      await api.delete(`${BASE}/sessions/${activeId}/documents/${doc.id}`);
      setDocuments((d) => d.filter((x) => x.id !== doc.id));
    } catch (err) {
      setError(errorMessage(err, "Could not remove the document."));
    }
  }

  async function removeSession(s) {
    if (!window.confirm(`Delete the chat "${s.title}" and its documents?`)) return;
    try {
      await api.delete(`${BASE}/sessions/${s.id}`);
      if (s.id === activeId) newChat();
      loadSessions();
    } catch (err) {
      setError(errorMessage(err, "Could not delete."));
    }
  }

  const suggestions = documents.length ? [...DOC_SUGGESTIONS, ...SUGGESTIONS.slice(0, 3)] : SUGGESTIONS;

  return (
    <div className="chat-layout">
      <aside className="card chat-sessions">
        <button className="btn btn-primary" onClick={newChat}>New chat</button>
        {sessions === null ? <p className="muted small">Loading…</p> : sessions.length === 0 ? <p className="muted small">No chats yet.</p> : (
          <ul className="session-list">
            {sessions.map((s) => (
              <li key={s.id} className={s.id === activeId ? "active" : ""}>
                <button className="session-btn" onClick={() => open(s.id)} title={s.title}>{s.title}</button>
                <button className="icon no" onClick={() => removeSession(s)} aria-label={`Delete ${s.title}`}>✕</button>
              </li>
            ))}
          </ul>
        )}
      </aside>

      <section className="card chat-main interview-chat">
        <div className="row-between wrap">
          <div>
            <h2>Interview Prep Agent</h2>
            <p className="muted small">Uses your resume data, verified skills and internship matches. Upload a PDF or DOCX to ask questions about it.</p>
          </div>
          <div className="row">
            <input ref={fileRef} type="file" accept=".pdf,.docx" onChange={onFile} hidden />
            <button className="btn btn-ghost small" onClick={() => fileRef.current?.click()} disabled={uploading || busy}>
              {uploading ? "Reading document…" : "Upload PDF/DOCX"}
            </button>
          </div>
        </div>

        {documents.length > 0 && (
          <ul className="chips" aria-label="Documents in this chat">
            {documents.map((d) => (
              <li key={d.id} className="chip">
                📄 {d.filename}
                <button className="icon no" onClick={() => removeDoc(d)} aria-label={`Remove ${d.filename}`}>✕</button>
              </li>
            ))}
          </ul>
        )}

        <div className="chat-scroll tall" aria-live="polite">
          {messages.length === 0 && (
            <div className="stack">
              <div className="msg msg-bot">
                <div className="msg-body">
                  Hi! I'm your Interview Prep Agent. I read your resume data (skills, education, experience and projects) to recommend roles and
                  internships, then help you prepare: role-specific technical and HR questions, answer guidance, a roadmap and a learning path. You can
                  also upload a PDF or DOCX and ask me about it.
                </div>
              </div>
              <div className="row wrap">
                {suggestions.map((s) => (
                  <button key={s} className="btn btn-ghost small" onClick={() => send(s)} disabled={busy}>{s}</button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m) => (
            <div key={m.id} className={`msg ${m.role === "user" ? "msg-user" : "msg-bot wide"}`}>
              <div className="msg-body">{m.role === "user" ? m.content : <RichText text={m.content} />}</div>
              {m.citations?.length > 0 && (
                <details className="sources">
                  <summary>From your document</summary>
                  <ul>{m.citations.map((c) => <li key={c.n}><strong>{c.title}</strong>: <span className="muted">{c.snippet}…</span></li>)}</ul>
                </details>
              )}
            </div>
          ))}
          {busy && <div className="msg msg-bot"><div className="msg-body muted">Thinking…</div></div>}
          <div ref={endRef} />
        </div>

        {error && <div className="alert">{error}</div>}

        <form className="chat-input" onSubmit={(e) => { e.preventDefault(); send(); }}>
          <textarea
            rows={2}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
            placeholder="Ask about roles, interview questions, a roadmap, or your uploaded document… (Enter to send)"
            maxLength={2000}
            disabled={busy}
            aria-label="Message"
          />
          <button className="btn btn-primary" disabled={busy || !text.trim()}>{busy ? "Sending…" : "Send"}</button>
        </form>
      </section>
    </div>
  );
}
