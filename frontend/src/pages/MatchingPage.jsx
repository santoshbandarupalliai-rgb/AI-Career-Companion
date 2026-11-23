import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, errorMessage } from "../api/client.js";

const MODE_LABEL = { remote: "Remote", onsite: "On-site", hybrid: "Hybrid" };
const STATUS_LABEL = { met: "Met", not_met: "Not met", unknown: "Unknown" };

function Skills({ title, items, kind }) {
  return (
    <div>
      <h3>{title}</h3>
      {items.length === 0 ? (
        <p className="muted small">None</p>
      ) : (
        <ul className="chips">
          {items.map((s) => (
            <li key={s} className={`chip static ${kind}`}>
              {s}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Breakdown({ id }) {
  const [m, setM] = useState(null);
  const [error, setError] = useState("");
  const [exp, setExp] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .get(`/matching/${id}`)
      .then(({ data }) => setM(data))
      .catch((err) => setError(errorMessage(err, "Could not load the breakdown.")));
  }, [id]);

  async function explain() {
    setBusy(true);
    try {
      const { data } = await api.post(`/matching/${id}/explain`, null, { timeout: 120000 });
      setExp(data);
    } catch (err) {
      setExp({ available: false, message: errorMessage(err, "The explanation is unavailable right now.") });
    } finally {
      setBusy(false);
    }
  }

  if (error) return <div className="alert">{error}</div>;
  if (!m) return <p className="muted small">Loading breakdown…</p>;

  return (
    <div className="stack">
      <table className="factor-table">
        <thead>
          <tr>
            <th>Factor</th>
            <th>Weight</th>
            <th>Score</th>
            <th>Points</th>
          </tr>
        </thead>
        <tbody>
          {m.factors.map((f) => (
            <tr key={f.key} className={f.applicable ? "" : "na"}>
              <td>
                <strong>{f.label}</strong>
                <div className="muted small">{f.detail}</div>
              </td>
              <td>{f.applicable ? `${Math.round(f.effective_weight * 100)}%` : "–"}</td>
              <td>{f.applicable ? `${Math.round(f.value * 100)}%` : "n/a"}</td>
              <td>{f.applicable ? f.contribution.toFixed(1) : "0"}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <td colSpan={3}>
              <strong>Total</strong>
            </td>
            <td>
              <strong>{m.overall.toFixed(1)}</strong>
            </td>
          </tr>
        </tfoot>
      </table>

      <div className="skill-cols">
        <Skills title="Required: you have" items={m.matched_required} kind="have" />
        <Skills title="Required: missing" items={m.missing_required} kind="lack" />
        <Skills title="Preferred: you have" items={m.matched_preferred} kind="have" />
        <Skills title="Preferred: missing" items={m.missing_preferred} kind="lack" />
      </div>

      {m.eligibility.length > 0 && (
        <div>
          <h3>Eligibility stated in the posting (not part of the score)</h3>
          <ul className="plain">
            {m.eligibility.map((e) => (
              <li key={e.key} className="small">
                <span className={`badge elig-${e.status}`}>{STATUS_LABEL[e.status]}</span> <strong>{e.label}</strong>: {e.detail}
              </li>
            ))}
          </ul>
        </div>
      )}

      {m.notes.map((n, i) => (
        <p key={i} className="notice-inline small">
          {n}
        </p>
      ))}

      <div className="actions">
        <button className="btn btn-ghost small" onClick={explain} disabled={busy}>
          {busy ? "Writing…" : "Explain in words (AI)"}
        </button>
        <Link className="btn btn-ghost small" to={`/skill-gap?internship=${id}`}>
          See skill gap
        </Link>
      </div>
      {exp && (exp.available ? <p className="narrative">{exp.narrative}</p> : <div className="alert">{exp.message}</div>)}
    </div>
  );
}

function MatchCard({ item }) {
  const [open, setOpen] = useState(false);
  const meta = [item.location, MODE_LABEL[item.work_mode]].filter(Boolean).filter((v, i, a) => a.findIndex((x) => x.toLowerCase() === v.toLowerCase()) === i);
  return (
    <article className="card stack match-card">
      <div className="row-between wrap">
        <div className="row">
          <div className="score" aria-label={`Match score ${item.overall} out of 100`}>
            {Math.round(item.overall)}
          </div>
          <div>
            <h2>{item.title}</h2>
            <div className="muted">
              {item.company}
              {meta.length > 0 && ` · ${meta.join(" · ")}`}
            </div>
          </div>
        </div>
        {item.source === "sample" && <span className="badge sample">Sample</span>}
      </div>
      <div className="small">
        Required skills: <strong>{item.required_matched}</strong> of {item.required_total} verified
        {item.missing_required.length > 0 && (
          <span className="muted"> · missing {item.missing_required.join(", ")}</span>
        )}
      </div>
      <div className="actions">
        <button className="btn btn-ghost small" onClick={() => setOpen(!open)}>
          {open ? "Hide breakdown" : "Why this score?"}
        </button>
      </div>
      {open && <Breakdown id={item.internship_id} />}
    </article>
  );
}

export default function MatchingPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");

  useEffect(() => {
    api
      .get("/matching", { params: { limit: 200 }, timeout: 60000 })
      .then(({ data }) => setData(data))
      .catch((err) => setError(errorMessage(err, "Could not compute matches.")));
  }, []);

  const items = (data?.items || []).filter((i) => `${i.title} ${i.company}`.toLowerCase().includes(q.trim().toLowerCase()));

  return (
    <div className="stack-lg">
      <div>
        <h1>Job Matching</h1>
        <p className="muted">
          How well each internship fits you, and exactly why. Scores are calculated by fixed rules from your <strong>verified</strong> skills, not by
          AI, so the same profile always gives the same score.
        </p>
      </div>

      {error && <div className="alert">{error}</div>}
      {data === null && !error && <p className="muted">Calculating…</p>}

      {data && data.notes.map((n, i) => (
        <div key={i} className="card notice">
          {n} <Link to="/resume">Review my skills</Link>
        </div>
      ))}

      {data && (
        <>
          <div className="row wrap">
            <input className="grow" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter by title or company" aria-label="Filter matches" />
            <span className="muted small">
              {items.length} posting{items.length === 1 ? "" : "s"} · based on {data.verified_skill_count} verified skill{data.verified_skill_count === 1 ? "" : "s"}
            </span>
          </div>
          {items.length === 0 ? (
            <div className="card notice">No internships to show. Add some in the Internship Knowledge Base.</div>
          ) : (
            <div className="match-list">
              {items.map((i) => (
                <MatchCard key={i.internship_id} item={i} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
