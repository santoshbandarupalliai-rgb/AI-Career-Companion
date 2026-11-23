import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, errorMessage } from "../api/client.js";

export const STATUSES = [
  ["saved", "Saved"],
  ["applied", "Applied"],
  ["oa", "Online assessment"],
  ["interview", "Interview"],
  ["offer", "Offer"],
  ["rejected", "Rejected"],
  ["withdrawn", "Withdrawn"],
];
const LABEL = Object.fromEntries(STATUSES);
const EMPTY_FORM = { company: "", role: "", status: "saved", deadline: "", notes: "" };

function fmtDate(d) {
  return d ? new Date(`${d}T00:00:00`).toLocaleDateString() : "";
}

function daysLeft(d) {
  if (!d) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((new Date(`${d}T00:00:00`) - today) / 86400000);
}

function AddForm({ resumes, onAdded }) {
  const [form, setForm] = useState(EMPTY_FORM);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const body = { ...form, deadline: form.deadline || null, notes: form.notes || null, resume_id: form.resume_id || null };
      const { data } = await api.post("/applications", body);
      setForm(EMPTY_FORM);
      onAdded(data);
    } catch (err) {
      setError(errorMessage(err, "Could not add the application."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card stack" onSubmit={submit}>
      <h2>Add an external application</h2>
      <p className="muted small">
        For postings in the knowledge base, use <strong>Track</strong> on the <Link to="/internships">Internships</Link> page so company and role are copied
        from the posting.
      </p>
      <div className="form-grid">
        <label>
          Company
          <input value={form.company} onChange={set("company")} maxLength={200} required />
        </label>
        <label>
          Role
          <input value={form.role} onChange={set("role")} maxLength={200} required />
        </label>
        <label>
          Status
          <select value={form.status} onChange={set("status")}>
            {STATUSES.map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </label>
        <label>
          Deadline
          <input type="date" value={form.deadline} onChange={set("deadline")} />
        </label>
        {resumes.length > 0 && (
          <label>
            Resume used
            <select value={form.resume_id || ""} onChange={set("resume_id")}>
              <option value="">Not set</option>
              {resumes.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.original_filename}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      <label>
        Notes
        <textarea rows={2} value={form.notes} onChange={set("notes")} maxLength={5000} />
      </label>
      {error && <div className="alert">{error}</div>}
      <div>
        <button className="btn btn-primary" disabled={busy}>
          {busy ? "Adding…" : "Add application"}
        </button>
      </div>
    </form>
  );
}

function ApplicationCard({ app, resumes, onChanged, onDeleted }) {
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState(null);
  const [edit, setEdit] = useState(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const left = daysLeft(app.deadline);
  const closed = ["offer", "rejected", "withdrawn"].includes(app.status);

  async function loadDetail() {
    try {
      const { data } = await api.get(`/applications/${app.id}`);
      setDetail(data);
    } catch (err) {
      setError(errorMessage(err, "Could not load the history."));
    }
  }

  function toggle() {
    const next = !open;
    setOpen(next);
    if (next) {
      setEdit({ applied_on: app.applied_on || "", deadline: app.deadline || "", notes: app.notes || "", resume_id: app.resume_id || "" });
      loadDetail();
    }
  }

  async function changeStatus(status) {
    if (status === app.status) return;
    setBusy(true);
    setError("");
    try {
      const { data } = await api.post(`/applications/${app.id}/status`, { status, note: note.trim() || null });
      setNote("");
      setDetail(data);
      onChanged(data);
    } catch (err) {
      setError(errorMessage(err, "Could not change the status."));
    } finally {
      setBusy(false);
    }
  }

  async function save(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const body = {
        applied_on: edit.applied_on || null,
        deadline: edit.deadline || null,
        notes: edit.notes || null,
        resume_id: edit.resume_id || null,
      };
      const { data } = await api.patch(`/applications/${app.id}`, body);
      setDetail(data);
      onChanged(data);
    } catch (err) {
      setError(errorMessage(err, "Could not save the changes."));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!window.confirm(`Remove "${app.role}" at ${app.company} from your tracker? Its history is deleted too.`)) return;
    try {
      await api.delete(`/applications/${app.id}`);
      onDeleted(app.id);
    } catch (err) {
      setError(errorMessage(err, "Could not remove the application."));
    }
  }

  return (
    <article className="card stack app-card">
      <div className="row-between wrap">
        <div className="stack-sm">
          <h2>
            {app.role} <span className="muted">at {app.company}</span>{" "}
            {app.internship_source === "sample" && <span className="badge sample">Sample</span>}
          </h2>
          <div className="muted small row wrap">
            {app.applied_on && <span>Applied {fmtDate(app.applied_on)}</span>}
            {app.deadline && (
              <span className={!closed && left !== null && left <= 3 ? "warn" : ""}>
                Deadline {fmtDate(app.deadline)}
                {!closed && left !== null && (left < 0 ? " (passed)" : left === 0 ? " (today)" : ` (${left} day${left === 1 ? "" : "s"} left)`)}
              </span>
            )}
            {app.resume_name && <span>Resume: {app.resume_name}</span>}
          </div>
        </div>
        <div className="row">
          <select
            className={`status-select status-${app.status}`}
            value={app.status}
            disabled={busy}
            onChange={(e) => changeStatus(e.target.value)}
            aria-label={`Status of ${app.role} at ${app.company}`}
          >
            {STATUSES.map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
          <button className="btn btn-ghost small" onClick={toggle} aria-expanded={open}>
            {open ? "Close" : "Details"}
          </button>
        </div>
      </div>
      {app.notes && !open && <p className="muted small pre clamp">{app.notes}</p>}
      {error && <div className="alert">{error}</div>}
      {open && edit && (
        <div className="stack app-detail">
          <label>
            Note for the next status change (optional)
            <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} placeholder="e.g. HR call scheduled" />
          </label>
          <form className="stack" onSubmit={save}>
            <div className="form-grid">
              <label>
                Applied on
                <input type="date" value={edit.applied_on} onChange={(e) => setEdit({ ...edit, applied_on: e.target.value })} />
              </label>
              <label>
                Deadline
                <input type="date" value={edit.deadline} onChange={(e) => setEdit({ ...edit, deadline: e.target.value })} />
              </label>
              <label>
                Resume used
                <select value={edit.resume_id} onChange={(e) => setEdit({ ...edit, resume_id: e.target.value })}>
                  <option value="">Not set</option>
                  {resumes.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.original_filename}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <label>
              Notes
              <textarea rows={3} value={edit.notes} onChange={(e) => setEdit({ ...edit, notes: e.target.value })} maxLength={5000} />
            </label>
            <div className="actions">
              <button className="btn btn-primary small" disabled={busy}>
                Save
              </button>
              <button type="button" className="btn btn-ghost small danger" onClick={remove}>
                Remove
              </button>
            </div>
          </form>
          <div>
            <h3>History</h3>
            {!detail ? (
              <p className="muted small">Loading…</p>
            ) : (
              <ol className="history">
                {detail.events.map((ev) => (
                  <li key={ev.id}>
                    <span className="muted small">{new Date(ev.created_at).toLocaleString()}</span>{" "}
                    {ev.from_status ? `${LABEL[ev.from_status]} → ${LABEL[ev.to_status]}` : `Added as ${LABEL[ev.to_status]}`}
                    {ev.note && <span className="muted"> · {ev.note}</span>}
                  </li>
                ))}
              </ol>
            )}
          </div>
        </div>
      )}
    </article>
  );
}

export default function ApplicationsPage() {
  const [data, setData] = useState(null);
  const [filter, setFilter] = useState("");
  const [resumes, setResumes] = useState([]);
  const [showAdd, setShowAdd] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/applications", { params: filter ? { status: filter } : {} });
      setData(data);
      setError("");
    } catch (err) {
      setError(errorMessage(err, "Could not load your applications."));
    }
  }, [filter]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    api.get("/resumes").then((r) => setResumes(r.data), () => setResumes([]));
  }, []);

  const total = data ? Object.values(data.counts).reduce((a, b) => a + b, 0) : 0;

  return (
    <div className="stack-lg">
      <div className="row-between wrap">
        <div>
          <h1>Applications</h1>
          <p className="muted">Track every application from saved to offer. Each status change is kept in the history.</p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowAdd((s) => !s)} aria-expanded={showAdd}>
          {showAdd ? "Close" : "Add application"}
        </button>
      </div>

      {showAdd && (
        <AddForm
          resumes={resumes}
          onAdded={() => {
            setShowAdd(false);
            load();
          }}
        />
      )}

      {data && (
        <div className="actions" role="group" aria-label="Filter by status">
          <button className={`btn small ${filter === "" ? "btn-primary" : "btn-ghost"}`} onClick={() => setFilter("")}>
            All {total}
          </button>
          {STATUSES.map(([v, l]) => (
            <button key={v} className={`btn small ${filter === v ? "btn-primary" : "btn-ghost"}`} onClick={() => setFilter(v)}>
              {l} {data.counts[v]}
            </button>
          ))}
        </div>
      )}

      {error && <div className="alert">{error}</div>}
      {!data && !error && <p className="muted">Loading…</p>}
      {data && data.items.length === 0 && (
        <div className="card muted">
          {filter
            ? `No applications with status ${LABEL[filter]}.`
            : "Nothing tracked yet. Use Track on an internship, add an external application, or ask the Career Assistant."}
        </div>
      )}
      <div className="match-list">
        {data?.items.map((a) => (
          <ApplicationCard
            key={a.id}
            app={a}
            resumes={resumes}
            onChanged={() => load()}
            onDeleted={() => load()}
          />
        ))}
      </div>
    </div>
  );
}
