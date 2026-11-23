import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, errorMessage } from "../api/client.js";

function GapChip({ s }) {
  return (
    <li className="gap-item">
      <div>
        <strong>{s.name}</strong>
        <span className="muted small"> · {s.of > 1 ? `asked by ${s.demand} of ${s.of} postings` : s.importance}</span>
      </div>
      {s.unverified_in_resume && (
        <div className="small hint">
          In your resume but not verified. <Link to="/resume">Verify it</Link> if you have it.
        </div>
      )}
    </li>
  );
}

function Plan({ plan }) {
  return (
    <div className="stack">
      {plan.summary && <p>{plan.summary}</p>}
      <ol className="plan">
        {plan.steps.map((s) => (
          <li key={s.skill} className="card stack">
            <h3>{s.skill}</h3>
            <p className="small">
              <strong>Why:</strong> {s.why}
            </p>
            <p className="small">
              <strong>How to learn:</strong> {s.how_to_learn}
            </p>
            <p className="small">
              <strong>Practice project:</strong> {s.practice_project}
            </p>
          </li>
        ))}
      </ol>
    </div>
  );
}

export default function SkillGapPage() {
  const [params, setParams] = useSearchParams();
  const [internships, setInternships] = useState([]);
  const [mode, setMode] = useState(params.get("internship") ? "internship" : "role");
  const [internshipId, setInternshipId] = useState(params.get("internship") || "");
  const [roleInput, setRoleInput] = useState(params.get("role") || "");
  const [role, setRole] = useState(params.get("role") || "");
  const [gap, setGap] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [plan, setPlan] = useState(null);
  const [planBusy, setPlanBusy] = useState(false);

  useEffect(() => {
    api
      .get("/internships", { params: { limit: 100 } })
      .then(({ data }) => setInternships(data.items))
      .catch(() => {});
  }, []);

  const target = mode === "internship" ? (internshipId ? { internship_id: internshipId } : null) : role ? { role } : null;
  const targetKey = JSON.stringify(target);

  useEffect(() => {
    setPlan(null);
    if (!target) return setGap(null);
    let stale = false;
    setLoading(true);
    setError("");
    api
      .get("/skill-gap", { params: mode === "internship" ? { internship_id: internshipId } : { role }, timeout: 60000 })
      .then(({ data }) => !stale && setGap(data))
      .catch((err) => {
        if (!stale) {
          setGap(null);
          setError(errorMessage(err, "Could not compute the skill gap."));
        }
      })
      .finally(() => !stale && setLoading(false));
    return () => {
      stale = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [targetKey]);

  function submitRole(e) {
    e.preventDefault();
    const r = roleInput.trim();
    if (r.length < 2) return;
    setRole(r);
    setParams({ role: r });
  }

  async function makePlan() {
    setPlanBusy(true);
    setPlan(null);
    try {
      const { data } = await api.post("/skill-gap/plan", target, { timeout: 120000 });
      setPlan(data);
    } catch (err) {
      setPlan({ plan_available: false, message: errorMessage(err, "The learning plan is unavailable right now.") });
    } finally {
      setPlanBusy(false);
    }
  }

  const nothingMissing = gap && gap.critical.length === 0 && gap.secondary.length === 0;

  return (
    <div className="stack-lg">
      <div>
        <h1>Skill Gap</h1>
        <p className="muted">
          Which skills you are missing for a target, most important first. The gap is worked out by comparing your <strong>verified</strong> skills with
          the postings. Only the optional learning plan uses AI.
        </p>
      </div>

      <section className="card stack">
        <div className="row wrap">
          <label className="inline">
            <input type="radio" name="mode" checked={mode === "role"} onChange={() => setMode("role")} /> A target role
          </label>
          <label className="inline">
            <input type="radio" name="mode" checked={mode === "internship"} onChange={() => setMode("internship")} /> A specific internship
          </label>
        </div>
        {mode === "role" ? (
          <form className="row wrap" onSubmit={submitRole}>
            <input className="grow" value={roleInput} onChange={(e) => setRoleInput(e.target.value)} placeholder="e.g. Backend developer, Data analyst" aria-label="Target role" maxLength={150} />
            <button className="btn btn-primary" disabled={roleInput.trim().length < 2}>
              Analyse
            </button>
          </form>
        ) : (
          <select
            value={internshipId}
            onChange={(e) => {
              setInternshipId(e.target.value);
              setParams(e.target.value ? { internship: e.target.value } : {});
            }}
            aria-label="Internship"
          >
            <option value="">Choose an internship…</option>
            {internships.map((i) => (
              <option key={i.id} value={i.id}>
                {i.title} · {i.company}
              </option>
            ))}
          </select>
        )}
        {mode === "role" && <p className="muted small">For a role we compare against the closest matching postings in the knowledge base.</p>}
      </section>

      {error && <div className="alert">{error}</div>}
      {loading && <p className="muted">Analysing…</p>}

      {gap && !loading && (
        <>
          <section className="card stack">
            <div className="row-between wrap">
              <div>
                <h2>{gap.target.label}</h2>
                {gap.target.type === "role" && gap.target.postings_considered.length > 0 && (
                  <p className="muted small">Based on: {gap.target.postings_considered.join("; ")}</p>
                )}
              </div>
              {gap.coverage != null && (
                <div className="score" title="Share of the target's skill demand covered by your verified skills">
                  {Math.round(gap.coverage)}%
                </div>
              )}
            </div>
            {gap.notes.map((n, i) => (
              <p key={i} className="notice-inline small">
                {n} {n.includes("verified skills") && <Link to="/resume">Review my skills</Link>}
              </p>
            ))}
          </section>

          <div className="gap-cols">
            <section className="card stack">
              <h2>Acquired <span className="count">{gap.acquired.length}</span></h2>
              {gap.acquired.length === 0 ? <p className="muted small">None yet.</p> : (
                <ul className="chips">{gap.acquired.map((s) => <li key={s} className="chip static have">{s}</li>)}</ul>
              )}
            </section>
            <section className="card stack">
              <h2>Critical gaps <span className="count">{gap.critical.length}</span></h2>
              <p className="muted small">Required by the posting(s).</p>
              {gap.critical.length === 0 ? <p className="muted small">None.</p> : <ul className="plain">{gap.critical.map((s) => <GapChip key={s.name} s={s} />)}</ul>}
            </section>
            <section className="card stack">
              <h2>Secondary gaps <span className="count">{gap.secondary.length}</span></h2>
              <p className="muted small">Preferred, nice to have.</p>
              {gap.secondary.length === 0 ? <p className="muted small">None.</p> : <ul className="plain">{gap.secondary.map((s) => <GapChip key={s.name} s={s} />)}</ul>}
            </section>
          </div>

          {!nothingMissing && (
            <section className="card stack">
              <div className="row-between wrap">
                <h2>Learning plan</h2>
                <button className="btn btn-primary" onClick={makePlan} disabled={planBusy}>
                  {planBusy ? "Writing plan…" : plan?.plan ? "Regenerate plan (AI)" : "Create learning plan (AI)"}
                </button>
              </div>
              {!plan && <p className="muted small">An AI-written plan for the skills above. It contains no links or course names.</p>}
              {plan && !plan.plan_available && <div className="alert">{plan.message}</div>}
              {plan?.plan && <Plan plan={plan.plan} />}
            </section>
          )}
        </>
      )}
    </div>
  );
}
