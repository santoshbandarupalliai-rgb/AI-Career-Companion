import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, errorMessage } from "../api/client.js";
import SkillReview from "../components/SkillReview.jsx";
import { STATUS_LABEL, formatDate, resumeName } from "../components/ResumeManager.jsx";

function Section({ title, children, empty }) {
  return (
    <section className="card stack">
      <h2>{title}</h2>
      {empty ? <p className="muted small">Not found in the resume.</p> : children}
    </section>
  );
}

function dateRange(a, b) {
  return [a, b].filter(Boolean).join(" – ");
}

export default function ResumePage() {
  const [resumes, setResumes] = useState(null);
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [showRaw, setShowRaw] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [skillsVersion, setSkillsVersion] = useState(0);

  useEffect(() => {
    api
      .get("/resumes")
      .then(({ data }) => {
        setResumes(data);
        const active = data.find((r) => r.is_active) || data[0];
        if (active) setSelected(active.id);
      })
      .catch((err) => setError(errorMessage(err)));
  }, []);

  const loadDetail = useCallback(async (id) => {
    if (!id) return;
    setDetail(null);
    try {
      const { data } = await api.get(`/resumes/${id}`);
      setDetail(data);
    } catch (err) {
      setError(errorMessage(err));
    }
  }, []);

  useEffect(() => {
    loadDetail(selected);
  }, [selected, loadDetail]);

  async function reextract() {
    setBusy(true);
    setError("");
    try {
      const { data } = await api.post(`/resumes/${selected}/reextract`, null, { timeout: 120000 });
      setDetail(data);
      setSkillsVersion((v) => v + 1);
    } catch (err) {
      setError(errorMessage(err, "Re-extraction failed."));
    } finally {
      setBusy(false);
    }
  }

  if (resumes === null) return error ? <div className="alert">{error}</div> : <p className="muted">Loading…</p>;
  if (resumes.length === 0)
    return (
      <div>
        <h1>Resume Parsing</h1>
        <div className="card notice">
          No resume uploaded yet. <Link to="/profile">Upload one on the Profile page</Link>.
        </div>
        <SkillReview version={skillsVersion} />
      </div>
    );

  const ex = detail?.extraction;
  const d = ex?.data;

  return (
    <div className="stack-lg">
      <div className="row-between wrap">
        <div>
          <h1>Resume Parsing</h1>
          <p className="muted">What we read from your resume. Confirm your skills below. Only verified skills count as yours.</p>
        </div>
        <div className="row">
          <select value={selected || ""} onChange={(e) => setSelected(e.target.value)} aria-label="Choose resume">
            {resumes.map((r) => (
              <option key={r.id} value={r.id}>
                {resumeName(r)}
                {r.is_active ? " (active)" : ""}
              </option>
            ))}
          </select>
          <button className="btn btn-ghost" onClick={reextract} disabled={busy || !detail}>
            {busy ? "Re-running…" : "Re-run extraction"}
          </button>
        </div>
      </div>

      {error && <div className="alert">{error}</div>}
      {!detail ? (
        <p className="muted">Loading…</p>
      ) : (
        <>
          <div className="card">
            <div className="row wrap">
              <span className={`badge ${detail.extraction_status}`}>{STATUS_LABEL[detail.extraction_status]}</span>
              {ex && (
                <span className="muted small">
                  {ex.method === "llm" ? `AI extraction (${ex.model})` : "Basic extraction (AI unavailable)"} ·{" "}
                  {formatDate(ex.created_at)}
                </span>
              )}
            </div>
            {ex?.warnings?.length > 0 && (
              <details className="warnings">
                <summary>{ex.warnings.length} note{ex.warnings.length > 1 ? "s" : ""} from the extraction check</summary>
                <ul>
                  {ex.warnings.map((w, i) => (
                    <li key={i} className="small">
                      {w}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </div>

          <SkillReview version={skillsVersion} />

          {d && (
            <div className="two-col">
              <Section title="Contact" empty={!Object.values(d.personal).some(Boolean)}>
                <dl className="kv">
                  {Object.entries(d.personal)
                    .filter(([, v]) => v)
                    .map(([k, v]) => (
                      <div key={k}>
                        <dt>{k}</dt>
                        <dd>{v}</dd>
                      </div>
                    ))}
                </dl>
              </Section>
              <Section title="Summary" empty={!d.summary}>
                <p>{d.summary}</p>
              </Section>
              <Section title="Education" empty={!d.education.length}>
                {d.education.map((e, i) => (
                  <div key={i}>
                    <strong>{[e.degree, e.field].filter(Boolean).join(", ")}</strong>
                    <div className="muted small">{[e.institution, dateRange(e.start, e.end), e.score].filter(Boolean).join(" · ")}</div>
                  </div>
                ))}
              </Section>
              <Section title="Experience" empty={!d.experience.length}>
                {d.experience.map((e, i) => (
                  <div key={i}>
                    <strong>{e.title}</strong> {e.organization && <>at {e.organization}</>}
                    <div className="muted small">{[dateRange(e.start, e.end), e.location].filter(Boolean).join(" · ")}</div>
                    <ul>
                      {e.bullets.map((b, j) => (
                        <li key={j} className="small">
                          {b}
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </Section>
              <Section title="Projects" empty={!d.projects.length}>
                {d.projects.map((p, i) => (
                  <div key={i}>
                    <strong>{p.name}</strong>
                    {p.technologies.length > 0 && <div className="muted small">{p.technologies.join(", ")}</div>}
                    {p.description && <p className="small">{p.description}</p>}
                  </div>
                ))}
              </Section>
              <Section title="Certifications & achievements" empty={!d.certifications.length && !d.achievements.length}>
                <ul>
                  {d.certifications.map((c, i) => (
                    <li key={`c${i}`} className="small">
                      {[c.name, c.issuer, c.year].filter(Boolean).join(" · ")}
                    </li>
                  ))}
                  {d.achievements.map((a, i) => (
                    <li key={`a${i}`} className="small">
                      {a}
                    </li>
                  ))}
                </ul>
              </Section>
            </div>
          )}

          <div className="card">
            <button className="btn btn-ghost small" onClick={() => setShowRaw(!showRaw)}>
              {showRaw ? "Hide" : "Show"} raw extracted text
            </button>
            {showRaw && <pre className="raw">{detail.raw_text}</pre>}
          </div>
        </>
      )}
    </div>
  );
}
