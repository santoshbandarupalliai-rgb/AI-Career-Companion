import { useCallback, useEffect, useState } from "react";
import { api, errorMessage } from "../api/client.js";

function Chip({ skill, children }) {
  return (
    <li className="chip" title={skill.evidence ? `Found in resume: "…${skill.evidence}…"` : skill.source === "manual" ? "Added by you" : ""}>
      <span>{skill.name}</span>
      {children}
    </li>
  );
}

export default function SkillReview({ version = 0 }) {
  const [skills, setSkills] = useState(null);
  const [error, setError] = useState("");
  const [newSkill, setNewSkill] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/skills");
      setSkills(data);
    } catch (err) {
      setError(errorMessage(err));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load, version]);

  async function run(fn) {
    setError("");
    setBusy(true);
    try {
      await fn();
      await load();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const setStatus = (s, status) => run(() => api.patch(`/skills/${s.id}`, { status }));

  async function addSkill(e) {
    e.preventDefault();
    const name = newSkill.trim();
    if (!name) return;
    await run(() => api.post("/skills", { name }));
    setNewSkill("");
  }

  if (!skills) return <section className="card">{error ? <div className="alert">{error}</div> : <p className="muted">Loading skills…</p>}</section>;

  return (
    <section className="card stack">
      <div className="row-between wrap">
        <h2>Skills</h2>
        {skills.extracted.length > 0 && (
          <button
            className="btn btn-primary small"
            disabled={busy}
            onClick={() => run(() => api.post("/skills/verify", { ids: skills.extracted.map((s) => s.id) }))}
          >
            Verify all {skills.extracted.length}
          </button>
        )}
      </div>
      {error && <div className="alert">{error}</div>}

      <div className="skill-cols">
        <div>
          <h3>
            Needs your review <span className="count">{skills.extracted.length}</span>
          </h3>
          <p className="muted small">Found in your resume. Confirm the ones you really have.</p>
          {skills.extracted.length === 0 ? (
            <p className="muted small">Nothing to review.</p>
          ) : (
            <ul className="chips">
              {skills.extracted.map((s) => (
                <Chip key={s.id} skill={s}>
                  <button className="icon ok" aria-label={`Verify ${s.name}`} disabled={busy} onClick={() => setStatus(s, "verified")}>
                    ✓
                  </button>
                  <button className="icon no" aria-label={`Reject ${s.name}`} disabled={busy} onClick={() => setStatus(s, "rejected")}>
                    ✕
                  </button>
                </Chip>
              ))}
            </ul>
          )}
        </div>

        <div>
          <h3>
            Verified <span className="count">{skills.verified.length}</span>
          </h3>
          <p className="muted small">Used for matching, skill-gap analysis and applications.</p>
          <ul className="chips">
            {skills.verified.map((s) => (
              <Chip key={s.id} skill={s}>
                {s.source === "manual" ? (
                  <button className="icon" aria-label={`Remove ${s.name}`} disabled={busy} onClick={() => run(() => api.delete(`/skills/${s.id}`))}>
                    ✕
                  </button>
                ) : (
                  <button className="icon" aria-label={`Undo verify ${s.name}`} title="Move back to review" disabled={busy} onClick={() => setStatus(s, "extracted")}>
                    ↺
                  </button>
                )}
              </Chip>
            ))}
          </ul>
          <form className="row" onSubmit={addSkill}>
            <input placeholder="Add a skill you have" value={newSkill} maxLength={60} onChange={(e) => setNewSkill(e.target.value)} aria-label="New skill" />
            <button className="btn btn-ghost" disabled={busy || !newSkill.trim()}>
              Add
            </button>
          </form>
        </div>

        <div>
          <h3>
            Rejected <span className="count">{skills.rejected.length}</span>
          </h3>
          <p className="muted small">Ignored everywhere and not re-added by future extractions.</p>
          <ul className="chips">
            {skills.rejected.map((s) => (
              <Chip key={s.id} skill={s}>
                <button className="icon" aria-label={`Restore ${s.name}`} title="Move back to review" disabled={busy} onClick={() => setStatus(s, "extracted")}>
                  ↺
                </button>
              </Chip>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
