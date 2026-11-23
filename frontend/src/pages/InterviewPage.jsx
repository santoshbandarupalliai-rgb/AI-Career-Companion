import { useCallback, useEffect, useState } from "react";
import { api, errorMessage } from "../api/client.js";

const CAT = { technical: "Technical", behavioral: "Behavioral", resume: "About your resume", situational: "Situational" };

function Question({ sessionId, item, onUpdated }) {
  const [text, setText] = useState(item.user_answer || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const fb = item.feedback;

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const { data } = await api.post(`/interview/sessions/${sessionId}/items/${item.id}/answer`, { answer: text }, { timeout: 120000 });
      onUpdated(data);
    } catch (err) {
      setError(errorMessage(err, "Could not score your answer."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="card stack">
      <div className="row-between wrap">
        <div className="row wrap">
          <span className="badge">{item.position}</span>
          <span className="badge">{CAT[item.category]}</span>
          <span className="muted small">{item.difficulty}</span>
        </div>
        {item.score != null && <div className="score" aria-label={`Score ${item.score} out of 10`}>{item.score}/10</div>}
      </div>
      <p className="question">{item.question}</p>
      <form className="stack" onSubmit={submit}>
        <textarea rows={5} value={text} onChange={(e) => setText(e.target.value)} placeholder="Type your answer as you would say it in an interview…" maxLength={3000} aria-label={`Answer to question ${item.position}`} />
        <div className="row">
          <button className="btn btn-primary" disabled={busy || text.trim().length < 10}>
            {busy ? "Scoring…" : item.score != null ? "Score again" : "Get feedback"}
          </button>
          <span className="muted small">{text.length}/3000</span>
        </div>
      </form>
      {error && <div className="alert">{error}</div>}
      {fb && (
        <div className="stack feedback">
          <p className="muted small">
            AI feedback, not an official grade. Relevance {fb.relevance}/4 · Structure {fb.structure}/3 · Depth {fb.depth}/3
          </p>
          {fb.strengths.length > 0 && (
            <div>
              <h3>What worked</h3>
              <ul>{fb.strengths.map((s, i) => <li key={i} className="small">{s}</li>)}</ul>
            </div>
          )}
          {fb.improvements.length > 0 && (
            <div>
              <h3>To improve</h3>
              <ul>{fb.improvements.map((s, i) => <li key={i} className="small">{s}</li>)}</ul>
            </div>
          )}
          {fb.answer_outline && (
            <details>
              <summary className="small">What a strong answer would cover</summary>
              <p className="small pre">{fb.answer_outline}</p>
            </details>
          )}
        </div>
      )}
    </article>
  );
}

export default function InterviewPage() {
  const [sessions, setSessions] = useState(null);
  const [active, setActive] = useState(null);
  const [internships, setInternships] = useState([]);
  const [mode, setMode] = useState("role");
  const [role, setRole] = useState("");
  const [internshipId, setInternshipId] = useState("");
  const [count, setCount] = useState(8);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");

  const loadSessions = useCallback(async () => {
    try {
      const { data } = await api.get("/interview/sessions");
      setSessions(data);
    } catch (err) {
      setError(errorMessage(err, "Could not load your practice sessions."));
      setSessions([]);
    }
  }, []);

  useEffect(() => {
    loadSessions();
    api.get("/internships", { params: { limit: 100 } }).then(({ data }) => setInternships(data.items)).catch(() => {});
  }, [loadSessions]);

  async function open(id) {
    setError("");
    try {
      const { data } = await api.get(`/interview/sessions/${id}`);
      setActive(data);
    } catch (err) {
      setError(errorMessage(err, "Could not open that session."));
    }
  }

  async function create(e) {
    e.preventDefault();
    setCreating(true);
    setError("");
    try {
      const body = mode === "role" ? { role: role.trim(), count } : { internship_id: internshipId, count };
      const { data } = await api.post("/interview/sessions", body, { timeout: 120000 });
      setActive(data);
      loadSessions();
    } catch (err) {
      setError(errorMessage(err, "Could not create the questions."));
    } finally {
      setCreating(false);
    }
  }

  async function remove(s) {
    if (!window.confirm(`Delete the practice session for "${s.role}"? This cannot be undone.`)) return;
    try {
      await api.delete(`/interview/sessions/${s.id}`);
      if (active?.session.id === s.id) setActive(null);
      loadSessions();
    } catch (err) {
      setError(errorMessage(err, "Could not delete."));
    }
  }

  function updated(item) {
    setActive((a) => {
      const items = a.items.map((i) => (i.id === item.id ? item : i));
      const scores = items.filter((i) => i.score != null).map((i) => i.score);
      return {
        session: { ...a.session, answered: scores.length, average_score: scores.length ? Math.round((scores.reduce((x, y) => x + y, 0) / scores.length) * 10) / 10 : null },
        items,
      };
    });
    loadSessions();
  }

  const canCreate = mode === "role" ? role.trim().length >= 2 : !!internshipId;

  return (
    <div className="stack-lg">
      <div>
        <h1>Interview Prep</h1>
        <p className="muted">
          Practice questions written for a role or a specific internship, based on your verified skills and real projects. Answer in your own words and
          get scored feedback. Your sessions are saved.
        </p>
      </div>

      <form className="card stack" onSubmit={create}>
        <div className="row wrap">
          <label className="inline"><input type="radio" name="mode" checked={mode === "role"} onChange={() => setMode("role")} /> A role</label>
          <label className="inline"><input type="radio" name="mode" checked={mode === "internship"} onChange={() => setMode("internship")} /> A specific internship</label>
        </div>
        <div className="row wrap">
          {mode === "role" ? (
            <input className="grow" value={role} onChange={(e) => setRole(e.target.value)} placeholder="e.g. Backend developer, Data analyst" maxLength={150} aria-label="Target role" />
          ) : (
            <select className="grow" value={internshipId} onChange={(e) => setInternshipId(e.target.value)} aria-label="Internship">
              <option value="">Choose an internship…</option>
              {internships.map((i) => <option key={i.id} value={i.id}>{i.title} · {i.company}</option>)}
            </select>
          )}
          <select value={count} onChange={(e) => setCount(Number(e.target.value))} aria-label="Number of questions">
            {[5, 8, 10].map((n) => <option key={n} value={n}>{n} questions</option>)}
          </select>
          <button className="btn btn-primary" disabled={creating || !canCreate}>{creating ? "Writing questions…" : "Start practice"}</button>
        </div>
      </form>

      {error && <div className="alert">{error}</div>}

      <div className="chat-layout">
        <aside className="card chat-sessions">
          <h2>Your sessions</h2>
          {sessions === null ? <p className="muted small">Loading…</p> : sessions.length === 0 ? <p className="muted small">None yet.</p> : (
            <ul className="session-list">
              {sessions.map((s) => (
                <li key={s.id} className={s.id === active?.session.id ? "active" : ""}>
                  <button className="session-btn" onClick={() => open(s.id)} title={s.role}>
                    {s.role}
                    <span className="muted small"> · {s.answered}/{s.total}{s.average_score != null && ` · avg ${s.average_score}`}</span>
                  </button>
                  <button className="icon no" onClick={() => remove(s)} aria-label={`Delete ${s.role}`}>✕</button>
                </li>
              ))}
            </ul>
          )}
        </aside>
        <section className="stack">
          {!active ? (
            <div className="card notice">Start a practice session or open one from the list.</div>
          ) : (
            <>
              <div className="card row-between wrap">
                <div>
                  <h2>{active.session.role}</h2>
                  <p className="muted small">{active.session.answered} of {active.session.total} answered{active.session.average_score != null && ` · average ${active.session.average_score}/10`}</p>
                </div>
              </div>
              {active.items.map((item) => <Question key={item.id} sessionId={active.session.id} item={item} onUpdated={updated} />)}
            </>
          )}
        </section>
      </div>
    </div>
  );
}
