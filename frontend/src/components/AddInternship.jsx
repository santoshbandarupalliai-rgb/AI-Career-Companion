import { useState } from "react";
import { api, errorMessage } from "../api/client.js";

const EMPTY = {
  title: "", company: "", location: "", work_mode: "", stipend: "", duration: "",
  education_req: "", experience_req: "", eligibility_text: "", apply_url: "", description: "", skills: [],
};

function Field({ label, children }) {
  return (
    <label>
      {label}
      {children}
    </label>
  );
}

/** Paste a job description -> AI draft -> user edits and confirms -> saved. Nothing is saved before "Save". */
export default function AddInternship({ onSaved, onCancel }) {
  const [text, setText] = useState("");
  const [draft, setDraft] = useState(null);
  const [warnings, setWarnings] = useState([]);
  const [method, setMethod] = useState("");
  const [newSkill, setNewSkill] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const set = (k) => (e) => setDraft({ ...draft, [k]: e.target.value });

  async function extract(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const { data } = await api.post("/internships/extract", { text }, { timeout: 120000 });
      setDraft({ ...EMPTY, ...data });
      setWarnings(data.warnings || []);
      setMethod(data.method);
    } catch (err) {
      setError(errorMessage(err, "Could not read that text."));
    } finally {
      setBusy(false);
    }
  }

  function addSkill(e) {
    e.preventDefault();
    const name = newSkill.trim();
    if (!name || draft.skills.some((s) => s.name.toLowerCase() === name.toLowerCase())) return setNewSkill("");
    setDraft({ ...draft, skills: [...draft.skills, { name, importance: "required" }] });
    setNewSkill("");
  }

  const toggleImportance = (i) =>
    setDraft({
      ...draft,
      skills: draft.skills.map((s, j) => (j === i ? { ...s, importance: s.importance === "required" ? "preferred" : "required" } : s)),
    });
  const removeSkill = (i) => setDraft({ ...draft, skills: draft.skills.filter((_, j) => j !== i) });

  async function save(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const { method: _m, warnings: _w, ...fields } = draft;
    try {
      const { data } = await api.post("/internships", { ...fields, work_mode: fields.work_mode || null }, { timeout: 120000 });
      onSaved(data);
    } catch (err) {
      setError(errorMessage(err, "Could not save the internship."));
      setBusy(false);
    }
  }

  return (
    <section className="card stack">
      <div className="row-between">
        <h2>Add an internship from a job description</h2>
        <button className="btn btn-ghost small" onClick={onCancel} type="button">
          Close
        </button>
      </div>
      {error && <div className="alert">{error}</div>}

      {!draft ? (
        <form className="stack" onSubmit={extract}>
          <p className="muted small">
            Paste the posting text. We extract the details and skills, remove anything that is not in your text, and show you a draft to
            check. Nothing is saved until you confirm. Postings you add are visible only to you.
          </p>
          <textarea rows={10} value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste the job description here…" aria-label="Job description" />
          <div className="row">
            <button className="btn btn-primary" disabled={busy || text.trim().length < 40}>
              {busy ? "Reading…" : "Extract details"}
            </button>
            {text.trim().length < 40 && <span className="muted small">Paste at least a few sentences.</span>}
          </div>
        </form>
      ) : (
        <form className="stack" onSubmit={save}>
          <div className="notice-inline muted small">
            {method === "llm" ? "AI draft." : "Basic draft (AI unavailable)."} Review every field before saving.
          </div>
          {warnings.length > 0 && (
            <details className="warnings">
              <summary>{warnings.length} note{warnings.length > 1 ? "s" : ""} from the check</summary>
              <ul>
                {warnings.map((w, i) => (
                  <li key={i} className="small">{w}</li>
                ))}
              </ul>
            </details>
          )}
          <div className="form-grid">
            <Field label="Title *"><input value={draft.title} onChange={set("title")} required maxLength={200} /></Field>
            <Field label="Company *"><input value={draft.company} onChange={set("company")} required maxLength={200} /></Field>
            <Field label="Location"><input value={draft.location} onChange={set("location")} maxLength={150} /></Field>
            <Field label="Work mode">
              <select value={draft.work_mode} onChange={set("work_mode")}>
                <option value="">Not stated</option>
                <option value="remote">Remote</option>
                <option value="onsite">On-site</option>
                <option value="hybrid">Hybrid</option>
              </select>
            </Field>
            <Field label="Stipend"><input value={draft.stipend} onChange={set("stipend")} maxLength={100} /></Field>
            <Field label="Duration"><input value={draft.duration} onChange={set("duration")} maxLength={100} /></Field>
            <Field label="Education requirement"><input value={draft.education_req} onChange={set("education_req")} maxLength={300} /></Field>
            <Field label="Experience requirement"><input value={draft.experience_req} onChange={set("experience_req")} maxLength={300} /></Field>
            <Field label="Apply link"><input value={draft.apply_url} onChange={set("apply_url")} maxLength={500} placeholder="https://…" /></Field>
          </div>
          <Field label="Eligibility notes"><textarea rows={2} value={draft.eligibility_text} onChange={set("eligibility_text")} maxLength={5000} /></Field>

          <div>
            <h3>Skills</h3>
            <p className="muted small">Click a skill to switch it between required and preferred.</p>
            <ul className="chips">
              {draft.skills.map((s, i) => (
                <li key={s.name} className={`chip ${s.importance === "preferred" ? "preferred" : ""}`}>
                  <button type="button" className="chip-btn" onClick={() => toggleImportance(i)} title="Toggle required / preferred">
                    {s.name} · {s.importance}
                  </button>
                  <button type="button" className="icon no" onClick={() => removeSkill(i)} aria-label={`Remove ${s.name}`}>✕</button>
                </li>
              ))}
              {draft.skills.length === 0 && <li className="muted small">No skills found. Add them below.</li>}
            </ul>
            <div className="row">
              <input value={newSkill} onChange={(e) => setNewSkill(e.target.value)} placeholder="Add a skill" maxLength={100} aria-label="Add a skill"
                onKeyDown={(e) => e.key === "Enter" && addSkill(e)} />
              <button type="button" className="btn btn-ghost small" onClick={addSkill}>Add</button>
            </div>
          </div>

          <Field label="Full description (your pasted text)">
            <textarea rows={6} value={draft.description} onChange={set("description")} />
          </Field>

          <div className="row">
            <button className="btn btn-primary" disabled={busy || !draft.title.trim() || !draft.company.trim() || draft.description.trim().length < 20}>
              {busy ? "Saving…" : "Save internship"}
            </button>
            <button type="button" className="btn btn-ghost" onClick={() => setDraft(null)} disabled={busy}>
              Start over
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
