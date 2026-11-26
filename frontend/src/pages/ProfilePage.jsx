import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, errorMessage } from "../api/client.js";
import ResumeManager from "../components/ResumeManager.jsx";

const FIELDS = [
  { key: "college", label: "College / University" },
  { key: "degree", label: "Degree", placeholder: "e.g. B.Tech" },
  { key: "branch", label: "Branch / Major", placeholder: "e.g. Computer Science" },
  { key: "cgpa", label: "CGPA (out of 10)", type: "number", step: "0.01", min: 0, max: 10 },
  { key: "graduation_year", label: "Graduation year", type: "number", min: 1990, max: 2100 },
  { key: "target_role", label: "Target role", placeholder: "e.g. Backend Developer Intern" },
  { key: "location", label: "Location" },
  { key: "phone", label: "Phone" },
  { key: "linkedin_url", label: "LinkedIn URL" },
  { key: "github_url", label: "GitHub URL" },
  { key: "portfolio_url", label: "Portfolio URL" },
];

export default function ProfilePage() {
  const [form, setForm] = useState(null);
  const [saved, setSaved] = useState(null);
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState({});
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .get("/profile")
      .then(({ data }) => {
        const f = Object.fromEntries(FIELDS.map((x) => [x.key, data[x.key] ?? ""]));
        f.bio = data.bio ?? "";
        setForm(f);
        setSaved(f);
      })
      .catch((err) => setError(errorMessage(err)));
  }, []);

  async function onSave(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setFieldErrors({});
    setStatus("");
    try {
      const { data } = await api.put("/profile", form);
      const f = Object.fromEntries(FIELDS.map((x) => [x.key, data[x.key] ?? ""]));
      f.bio = data.bio ?? "";
      setForm(f);
      setSaved(f);
      setStatus("Profile saved.");
    } catch (err) {
      const errs = err.response?.data?.errors;
      if (errs) setFieldErrors(Object.fromEntries(errs.map((x) => [x.field, x.message])));
      setError(errorMessage(err, "Could not save the profile."));
    } finally {
      setBusy(false);
    }
  }

  if (!form) return error ? <div className="alert">{error}</div> : <p className="muted">Loading…</p>;

  const dirty = JSON.stringify(form) !== JSON.stringify(saved);

  return (
    <div>
      <h1>Profile & Resumes</h1>
      <p className="muted">
        Your profile is entered by you only: nothing is copied into it from a resume. Skills come from your resume and you confirm them on the{" "}
        <Link to="/resume">Resume Parsing</Link> page.
      </p>

      <div className="two-col">
        <form className="card stack" onSubmit={onSave} noValidate>
          <div className="row-between">
            <h2>Academic & career profile</h2>
          </div>
          <div className="form-grid">
            {FIELDS.map((f) => (
              <label key={f.key}>
                {f.label}
                <input
                  type={f.type || "text"}
                  step={f.step}
                  min={f.min}
                  max={f.max}
                  placeholder={f.placeholder}
                  value={form[f.key]}
                  onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
                  aria-invalid={!!fieldErrors[f.key]}
                />
                {fieldErrors[f.key] && <span className="small warn">{fieldErrors[f.key]}</span>}
              </label>
            ))}
          </div>
          <label>
            Short bio
            <textarea rows={3} value={form.bio} onChange={(e) => setForm({ ...form, bio: e.target.value })} />
          </label>
          {error && <div className="alert">{error}</div>}
          {status && !dirty && <div className="ok">{status}</div>}
          <div>
            <button className="btn btn-primary" disabled={busy || !dirty}>
              {busy ? "Saving…" : "Save profile"}
            </button>
          </div>
        </form>

        <ResumeManager />
      </div>
    </div>
  );
}
