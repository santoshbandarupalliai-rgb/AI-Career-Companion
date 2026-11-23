import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, errorMessage } from "../api/client.js";

const KIND_LABEL = { resume: "Resume", cover_letter: "Cover letter" };

function FlagList({ flags, prefix }) {
  const mine = flags.filter((f) => f.where === prefix || f.where.startsWith(prefix + "."));
  if (mine.length === 0) return null;
  return (
    <ul className="flag-list">
      {mine.map((f, i) => (
        <li key={i} className="small">
          <span className="badge elig-not_met">Check</span> {f.message}
        </li>
      ))}
    </ul>
  );
}

function EditableList({ items, onChange, flags, prefix, rows = 2 }) {
  return (
    <div className="stack">
      {items.map((text, i) => (
        <div key={i} className="stack-sm">
          <textarea rows={rows} value={text} onChange={(e) => onChange(items.map((t, j) => (j === i ? e.target.value : t)))} aria-label={`${prefix} ${i + 1}`} />
          <FlagList flags={flags} prefix={`${prefix}.${i}`} />
        </div>
      ))}
    </div>
  );
}

function ResumeEditor({ content, setContent, flags }) {
  const setEntry = (kind, idx, patch) =>
    setContent({ ...content, [kind]: content[kind].map((e, i) => (i === idx ? { ...e, ...patch } : e)) });
  return (
    <div className="stack">
      <div>
        <h3>Summary</h3>
        <textarea rows={3} value={content.summary} onChange={(e) => setContent({ ...content, summary: e.target.value })} aria-label="Summary" />
        <FlagList flags={flags} prefix="summary" />
      </div>
      <div>
        <h3>Skills</h3>
        <p className="muted small">Only your verified skills can appear here.</p>
        <ul className="chips">
          {content.skills.map((s) => (
            <li key={s} className="chip">
              <span>{s}</span>
              <button type="button" className="icon no" aria-label={`Remove ${s}`} onClick={() => setContent({ ...content, skills: content.skills.filter((x) => x !== s) })}>
                ✕
              </button>
            </li>
          ))}
          {content.skills.length === 0 && <li className="muted small">None selected.</li>}
        </ul>
      </div>
      {["experience", "projects"].map(
        (kind) =>
          content[kind].length > 0 && (
            <div key={kind} className="stack">
              <h3>{kind === "experience" ? "Experience" : "Projects"}</h3>
              {content[kind].map((e, idx) => (
                <div key={`${e.source_index}-${idx}`} className="card stack">
                  <div>
                    <strong>{e.title}</strong>
                    {e.organization && <> at {e.organization}</>}
                    <div className="muted small">
                      {[[e.start, e.end].filter(Boolean).join(" – "), e.technologies?.join(", ")].filter(Boolean).join(" · ")} · copied from your resume
                    </div>
                  </div>
                  <EditableList items={e.bullets} onChange={(b) => setEntry(kind, idx, { bullets: b })} flags={flags} prefix={`${kind}.${idx}.bullet`} />
                  <button type="button" className="btn btn-ghost small" onClick={() => setContent({ ...content, [kind]: content[kind].filter((_, i) => i !== idx) })}>
                    Remove this {kind === "experience" ? "entry" : "project"}
                  </button>
                </div>
              ))}
            </div>
          )
      )}
      {content.education.length > 0 && (
        <div>
          <h3>Education</h3>
          {content.education.map((e, i) => (
            <p key={i} className="small">{e.text}</p>
          ))}
        </div>
      )}
    </div>
  );
}

function LetterEditor({ content, setContent, flags }) {
  return (
    <div className="stack">
      <p>{content.greeting}</p>
      {content.paragraphs.map((p, i) => (
        <div key={i} className="stack-sm">
          <textarea
            rows={4}
            value={p}
            onChange={(e) => setContent({ ...content, paragraphs: content.paragraphs.map((x, j) => (j === i ? e.target.value : x)) })}
            aria-label={`Paragraph ${i + 1}`}
          />
          <FlagList flags={flags} prefix={`cover_letter.p${i + 1}`} />
        </div>
      ))}
      <p>
        {content.closing}
        <br />
        {content.name}
      </p>
    </div>
  );
}

function Draft({ draft, onSaved, onDiscard }) {
  const [content, setContent] = useState(draft.content);
  const [flags, setFlags] = useState(draft.flags);
  const [ack, setAck] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const warnings = flags.filter((f) => f.severity === "warning");
  const removed = flags.filter((f) => f.severity === "removed");

  async function save() {
    setBusy(true);
    setError("");
    try {
      const { data } = await api.post("/tailoring/documents", {
        kind: draft.kind, internship_id: draft.internship_id, title: draft.title, content, acknowledge_flags: ack,
      });
      onSaved(data);
    } catch (err) {
      const d = err.response?.data?.detail;
      if (err.response?.status === 409 && d?.flags) {
        setFlags(d.flags); // the server re-checked what you edited
        setError("Some items are still flagged. Fix them, or tick the box to confirm they are accurate, then save again.");
      } else {
        setError(errorMessage(err, "Could not save."));
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card stack">
      <div className="row-between wrap">
        <h2>{draft.title}</h2>
        <span className="badge">Draft: not saved</span>
      </div>
      {draft.notes.map((n, i) => (
        <p key={i} className="notice-inline small">{n}</p>
      ))}
      {removed.length > 0 && (
        <details className="warnings">
          <summary>{removed.length} item{removed.length > 1 ? "s" : ""} removed automatically</summary>
          <ul>{removed.map((f, i) => <li key={i} className="small">{f.message}</li>)}</ul>
        </details>
      )}
      <div className={warnings.length ? "alert" : "ok"}>
        {warnings.length
          ? `${warnings.length} item${warnings.length > 1 ? "s" : ""} could not be matched to your profile or resume. They are marked "Check" below. Edit or delete them. Flags refresh when you save.`
          : "Every claim in this draft was found in your profile or resume."}
      </div>

      {draft.kind === "resume" ? (
        <ResumeEditor content={content} setContent={setContent} flags={flags} />
      ) : (
        <LetterEditor content={content} setContent={setContent} flags={flags} />
      )}

      <details>
        <summary className="small muted">Facts this draft is based on ({draft.facts_used.length})</summary>
        <ul>{draft.facts_used.map((f, i) => <li key={i} className="small">{f}</li>)}</ul>
      </details>

      {error && <div className="alert">{error}</div>}
      {warnings.length > 0 && (
        <label className="inline">
          <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} /> I have checked the flagged items and they are accurate.
        </label>
      )}
      <div className="row">
        <button className="btn btn-primary" onClick={save} disabled={busy || (warnings.length > 0 && !ack)}>
          {busy ? "Saving…" : "Approve and save"}
        </button>
        <button className="btn btn-ghost" onClick={onDiscard} disabled={busy}>Discard</button>
      </div>
    </section>
  );
}

export default function CustomizePage() {
  const [internships, setInternships] = useState([]);
  const [target, setTarget] = useState("");
  const [draft, setDraft] = useState(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [docs, setDocs] = useState(null);
  const [message, setMessage] = useState("");

  const loadDocs = useCallback(() => {
    api.get("/tailoring/documents").then(({ data }) => setDocs(data)).catch((err) => setError(errorMessage(err)));
  }, []);

  useEffect(() => {
    api.get("/internships", { params: { limit: 100 } }).then(({ data }) => setInternships(data.items)).catch(() => {});
    loadDocs();
  }, [loadDocs]);

  async function generate(kind) {
    setBusy(kind);
    setError("");
    setMessage("");
    setDraft(null);
    try {
      const { data } = await api.post("/tailoring/generate", { internship_id: target, kind }, { timeout: 120000 });
      setDraft(data);
    } catch (err) {
      setError(errorMessage(err, "Could not generate a draft."));
    } finally {
      setBusy("");
    }
  }

  async function download(d) {
    try {
      const res = await api.get(`/tailoring/documents/${d.id}/download`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${d.title.replace(/[^A-Za-z0-9._-]+/g, "_")}.docx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(errorMessage(err, "Download failed."));
    }
  }

  async function remove(d) {
    if (!window.confirm(`Delete "${d.title}"? This cannot be undone.`)) return;
    try {
      await api.delete(`/tailoring/documents/${d.id}`);
      loadDocs();
    } catch (err) {
      setError(errorMessage(err, "Could not delete."));
    }
  }

  return (
    <div className="stack-lg">
      <div>
        <h1>Resume & Cover Letter</h1>
        <p className="muted">
          Tailor your resume and a cover letter to an internship. The AI may only rephrase what is already in your profile and resume: employers,
          titles and dates are copied from your resume, the skills list uses only your <Link to="/resume">verified skills</Link>, and anything it cannot
          match is flagged for you to check. Nothing is saved until you approve it.
        </p>
      </div>

      <section className="card stack">
        <label>
          Internship
          <select value={target} onChange={(e) => { setTarget(e.target.value); setDraft(null); }} aria-label="Internship">
            <option value="">Choose an internship…</option>
            {internships.map((i) => (
              <option key={i.id} value={i.id}>{i.title} · {i.company}</option>
            ))}
          </select>
        </label>
        <div className="row wrap">
          <button className="btn btn-primary" disabled={!target || !!busy} onClick={() => generate("resume")}>
            {busy === "resume" ? "Writing resume…" : "Tailor my resume"}
          </button>
          <button className="btn btn-primary" disabled={!target || !!busy} onClick={() => generate("cover_letter")}>
            {busy === "cover_letter" ? "Writing letter…" : "Write a cover letter"}
          </button>
        </div>
      </section>

      {error && <div className="alert">{error}</div>}
      {message && <div className="ok">{message}</div>}
      {draft && (
        <Draft
          key={draft.title + draft.kind}
          draft={draft}
          onDiscard={() => setDraft(null)}
          onSaved={() => {
            setDraft(null);
            setMessage("Saved. You can download it below.");
            loadDocs();
          }}
        />
      )}

      <section className="card stack">
        <h2>Saved documents</h2>
        {docs === null ? (
          <p className="muted small">{error ? "Saved documents are unavailable right now." : "Loading…"}</p>
        ) : docs.length === 0 ? (
          <p className="muted small">Nothing saved yet.</p>
        ) : (
          <ul className="resume-list">
            {docs.map((d) => (
              <li key={d.id}>
                <div className="resume-name">
                  {d.title} <span className="badge">{KIND_LABEL[d.kind]}</span>
                </div>
                <div className="muted small">
                  {new Date(d.created_at).toLocaleDateString()}
                  {d.flagged_count > 0 && ` · saved with ${d.flagged_count} flagged item${d.flagged_count > 1 ? "s" : ""} you confirmed`}
                </div>
                <div className="actions">
                  <button className="btn btn-ghost small" onClick={() => download(d)}>Download .docx</button>
                  <button className="btn btn-ghost small danger" onClick={() => remove(d)}>Delete</button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
