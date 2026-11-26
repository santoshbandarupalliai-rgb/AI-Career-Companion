import { useCallback, useEffect, useRef, useState } from "react";
import { api, errorMessage } from "../api/client.js";
import { resumeName } from "../components/ResumeManager.jsx";
import PrepAgent from "../components/PrepAgent.jsx";

const CAT = { technical: "Technical", behavioral: "Behavioral", resume: "About your resume", situational: "Situational" };
const LEVEL_CLASS = { Strong: "level-strong", Developing: "level-developing", "Needs practice": "level-needs" };

function Feedback({ item }) {
  const fb = item.feedback;
  return (
    <div className="stack-sm">
      <div className="row wrap">
        <span className="score-chip" aria-label={`Score ${item.score} out of 10`}>{item.score}/10</span>
        <span className="muted small">Relevance {fb.relevance}/4 · Structure {fb.structure}/3 · Depth {fb.depth}/3</span>
      </div>
      {fb.strengths.length > 0 && (
        <div>
          <strong className="small">What worked</strong>
          <ul className="tight">{fb.strengths.map((s, i) => <li key={i} className="small">{s}</li>)}</ul>
        </div>
      )}
      {fb.improvements.length > 0 && (
        <div>
          <strong className="small">To improve</strong>
          <ul className="tight">{fb.improvements.map((s, i) => <li key={i} className="small">{s}</li>)}</ul>
        </div>
      )}
      {fb.answer_outline && (
        <details>
          <summary className="small">What a strong answer would cover</summary>
          <p className="small pre">{fb.answer_outline}</p>
        </details>
      )}
      <p className="muted small">AI feedback, not an official grade.</p>
    </div>
  );
}

function Report({ report }) {
  return (
    <div className="card stack report">
      <div className="row-between wrap">
        <div>
          <h2>Diagnostic report</h2>
          <p className="muted small">{report.answered} of {report.total} questions answered{report.unanswered > 0 ? ` · ${report.unanswered} skipped or left` : ""}</p>
        </div>
        <div className="row">
          {report.average_score != null && <span className="score-chip big">{report.average_score}/10</span>}
          <span className={`badge level ${LEVEL_CLASS[report.level] || ""}`}>{report.level}</span>
        </div>
      </div>
      <p>{report.level_note}</p>
      {report.by_category.length > 0 && (
        <div className="stack-sm">
          <strong className="small">Average score by question type</strong>
          {report.by_category.map((c) => (
            <div key={c.category} className="bar-row">
              <span className="small bar-label">{CAT[c.category]}</span>
              <span className="bar" role="img" aria-label={`${CAT[c.category]} ${c.average} out of 10`}><span style={{ width: `${c.average * 10}%` }} /></span>
              <span className="small">{c.average}</span>
            </div>
          ))}
          {report.strongest && report.weakest && (
            <p className="muted small">Strongest: {CAT[report.strongest]} · Needs most work: {CAT[report.weakest]}</p>
          )}
        </div>
      )}
      <div className="gap-cols">
        {report.top_strengths.length > 0 && (
          <div>
            <h3>Keep doing</h3>
            <ul className="tight">{report.top_strengths.map((s, i) => <li key={i} className="small">{s}</li>)}</ul>
          </div>
        )}
        {report.top_improvements.length > 0 && (
          <div>
            <h3>Work on</h3>
            <ul className="tight">{report.top_improvements.map((s, i) => <li key={i} className="small">{s}</li>)}</ul>
          </div>
        )}
      </div>
      <p className="muted small">Calculated from your saved scores. Start another session to track your progress.</p>
    </div>
  );
}

// One interview as a conversation: the interviewer asks a question, you answer, it gives feedback, then asks the next one.
function MockInterview({ detail, onUpdated }) {
  const { session, items } = detail;
  const [skipped, setSkipped] = useState(() => new Set());
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [report, setReport] = useState(null);
  const [reportBusy, setReportBusy] = useState(false);
  const endRef = useRef(null);

  const current = items.find((i) => i.score == null && !skipped.has(i.id));
  const finished = !current;
  const shown = items.filter((i) => i.score != null || skipped.has(i.id) || i === current);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [shown.length, busy, report]);

  const loadReport = useCallback(async () => {
    setReportBusy(true);
    setError("");
    try {
      const { data } = await api.get(`/interview/sessions/${session.id}/report`);
      setReport(data);
    } catch (err) {
      setError(errorMessage(err, "Could not build the report."));
    } finally {
      setReportBusy(false);
    }
  }, [session.id]);

  useEffect(() => {
    if (finished && items.some((i) => i.score != null) && !report) loadReport();
  }, [finished]); // eslint-disable-line react-hooks/exhaustive-deps

  async function send(e) {
    e?.preventDefault();
    if (!current || text.trim().length < 10 || busy) return;
    setBusy(true);
    setError("");
    try {
      const { data } = await api.post(`/interview/sessions/${session.id}/items/${current.id}/answer`, { answer: text.trim() }, { timeout: 120000 });
      setText("");
      setReport(null);
      onUpdated(data);
    } catch (err) {
      setError(errorMessage(err, "Could not score your answer."));
    } finally {
      setBusy(false);
    }
  }

  function skip() {
    setSkipped((s) => new Set(s).add(current.id));
    setText("");
    setReport(null);
  }

  const answered = items.filter((i) => i.score != null).length;

  return (
    <div className="card chat-main interview-chat">
      <div className="row-between wrap">
        <div>
          <h2>{session.role}</h2>
          <p className="muted small">Question {Math.min(items.findIndex((i) => i === current) + 1 || items.length, items.length)} of {items.length} · {answered} answered{session.average_score != null && ` · average ${session.average_score}/10`}</p>
        </div>
        {answered > 0 && !report && (
          <button className="btn btn-ghost small" onClick={loadReport} disabled={reportBusy}>{reportBusy ? "Building…" : "Show diagnostic report"}</button>
        )}
      </div>

      <div className="chat-scroll tall" aria-live="polite">
        <div className="msg msg-bot">
          <div className="msg-body">
            Hi! I'm your mock interviewer for <strong>{session.role}</strong>. I'll ask {items.length} questions, one at a time. Answer the way you would in a
            real interview and I'll give you feedback after each answer.
          </div>
        </div>
        {shown.map((item) => (
          <div key={item.id} className="stack-sm">
            <div className="msg msg-bot">
              <div className="row wrap">
                <span className="badge">Q{item.position}</span>
                <span className="badge">{CAT[item.category]}</span>
                <span className="muted small">{item.difficulty}</span>
              </div>
              <div className="msg-body question-text">{item.question}</div>
            </div>
            {item.score != null ? (
              <>
                <div className="msg msg-user"><div className="msg-body">{item.user_answer}</div></div>
                <div className="msg msg-bot wide"><Feedback item={item} /></div>
              </>
            ) : skipped.has(item.id) ? (
              <div className="msg msg-user muted-bubble"><div className="msg-body">Skipped</div></div>
            ) : null}
          </div>
        ))}
        {busy && <div className="msg msg-bot"><div className="msg-body muted">Reviewing your answer…</div></div>}
        {finished && (
          <div className="msg msg-bot">
            <div className="msg-body">
              {answered > 0
                ? "That was the last question. Here is your diagnostic summary."
                : "You skipped every question. Answer at least one to get a diagnostic."}
            </div>
          </div>
        )}
        {report && <Report report={report} />}
        <div ref={endRef} />
      </div>

      {error && <div className="alert">{error}</div>}

      {current ? (
        <form className="chat-input" onSubmit={send}>
          <textarea
            rows={3}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) send(e); }}
            placeholder="Type your answer as you would say it in an interview… (Ctrl+Enter to send)"
            maxLength={3000}
            disabled={busy}
            aria-label={`Answer to question ${current.position}`}
          />
          <div className="stack-sm">
            <button className="btn btn-primary" disabled={busy || text.trim().length < 10}>{busy ? "Sending…" : "Send answer"}</button>
            <button type="button" className="btn btn-ghost small" onClick={skip} disabled={busy}>Skip question</button>
          </div>
        </form>
      ) : null}
      {current && <p className="muted small">{text.length}/3000 · at least a sentence, please</p>}
    </div>
  );
}

function MockInterviewSection() {
  const [sessions, setSessions] = useState(null);
  const [active, setActive] = useState(null);
  const [internships, setInternships] = useState([]);
  const [resumes, setResumes] = useState([]);
  const [mode, setMode] = useState("role");
  const [role, setRole] = useState("");
  const [internshipId, setInternshipId] = useState("");
  const [resumeId, setResumeId] = useState("");
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
    api.get("/resumes").then(({ data }) => setResumes(data)).catch(() => {});
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
      const body = { count, resume_id: resumeId || undefined, ...(mode === "role" ? { role: role.trim() } : { internship_id: internshipId }) };
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
      <p className="muted">
        The interviewer asks questions written for a role or a specific internship (based on your verified skills and real projects), you answer in your
        own words, and each answer is scored with feedback. At the end you get a diagnostic report. Your sessions are saved.
      </p>

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
          {resumes.length > 1 && (
            <select value={resumeId} onChange={(e) => setResumeId(e.target.value)} aria-label="Resume to ask about">
              <option value="">Active resume</option>
              {resumes.map((r) => <option key={r.id} value={r.id}>{resumeName(r)}{r.is_active ? " (active)" : ""}</option>)}
            </select>
          )}
          <select value={count} onChange={(e) => setCount(Number(e.target.value))} aria-label="Number of questions">
            {[5, 8, 10].map((n) => <option key={n} value={n}>{n} questions</option>)}
          </select>
          <button className="btn btn-primary" disabled={creating || !canCreate}>{creating ? "Writing questions…" : "Start mock interview"}</button>
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
            <div className="card notice">Start a mock interview or open a past session from the list.</div>
          ) : (
            <MockInterview key={active.session.id} detail={active} onUpdated={updated} />
          )}
        </section>
      </div>
    </div>
  );
}

export default function InterviewPage() {
  const [tab, setTab] = useState("agent");
  return (
    <div className="stack-lg">
      <div className="page-head">
        <h1>Interview Prep</h1>
        <p className="muted">
          Chat with the Interview Prep Agent to find the roles that suit your resume and prepare for them, or practise with a scored mock interview.
        </p>
      </div>
      <div className="tabs" role="tablist">
        <button role="tab" aria-selected={tab === "agent"} className={`tab ${tab === "agent" ? "active" : ""}`} onClick={() => setTab("agent")}>Prep Agent</button>
        <button role="tab" aria-selected={tab === "mock"} className={`tab ${tab === "mock" ? "active" : ""}`} onClick={() => setTab("mock")}>Mock interview</button>
      </div>
      {tab === "agent" ? <PrepAgent /> : <MockInterviewSection />}
    </div>
  );
}
