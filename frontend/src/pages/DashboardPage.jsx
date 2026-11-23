import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, errorMessage } from "../api/client.js";
import { useAuth } from "../auth/AuthContext.jsx";
import { MODULES } from "../modules.js";

const STATUS_LABEL = {
  saved: "Saved", applied: "Applied", oa: "Online assessment", interview: "Interview",
  offer: "Offer", rejected: "Rejected", withdrawn: "Withdrawn",
};

function StatusPanel({ data }) {
  const { profile, resume, skills, applications } = data;
  const tracked = Object.entries(applications.by_status).filter(([, n]) => n > 0);
  return (
    <div className="grid status-grid">
      <Link to="/profile" className="card stack-sm status-card">
        <div className="muted small">Profile</div>
        <div className="status-num">{profile.filled}/{profile.total}</div>
        <div className="small muted">
          {profile.missing.length === 0 ? "All key fields filled." : `Missing: ${profile.missing.join(", ")}`}
        </div>
      </Link>
      <Link to="/profile" className="card stack-sm status-card">
        <div className="muted small">Resume</div>
        <div className="status-num">{resume.has_active ? "Active" : "None"}</div>
        <div className="small muted">
          {resume.has_active ? resume.active_filename : resume.count > 0 ? "Uploaded, but none is set as active." : "Nothing uploaded yet."}
        </div>
      </Link>
      <Link to="/resume" className="card stack-sm status-card">
        <div className="muted small">Skills</div>
        <div className="status-num">{skills.verified} verified</div>
        <div className="small muted">
          {skills.extracted > 0 ? `${skills.extracted} waiting for your review. ` : ""}
          Only verified skills are used for matching.
        </div>
      </Link>
      <Link to="/applications" className="card stack-sm status-card">
        <div className="muted small">Applications</div>
        <div className="status-num">{applications.total}</div>
        <div className="small muted">
          {tracked.length === 0 ? "None tracked yet." : tracked.map(([s, n]) => `${STATUS_LABEL[s] || s} ${n}`).join(" · ")}
        </div>
      </Link>
    </div>
  );
}

export default function DashboardPage() {
  const { user } = useAuth();
  const firstName = user?.full_name?.split(" ")[0] || "there";
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await api.get("/dashboard");
      setData(res.data);
    } catch (err) {
      setError(errorMessage(err, "Could not load your status."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="stack-lg">
      <div>
        <h1>Hi, {firstName}</h1>
        <p className="muted">Your progress at a glance. Every module builds on your profile, resume and verified skills.</p>
      </div>

      {loading && !data && <p className="muted">Loading your status…</p>}
      {error && (
        <div className="alert row-between wrap">
          <span>{error}</span>
          <button className="btn btn-ghost small" onClick={load} disabled={loading}>{loading ? "Retrying…" : "Try again"}</button>
        </div>
      )}

      {data && (
        <>
          <div className="card row-between wrap next-step">
            <div>
              <div className="muted small">Next step</div>
              <div>{data.next_step.message}</div>
            </div>
            <Link className="btn btn-primary" to={data.next_step.path}>{data.next_step.label}</Link>
          </div>
          <StatusPanel data={data} />
          {data.applications.upcoming_deadlines.length > 0 && (
            <div className="card stack-sm">
              <h2>Upcoming deadlines</h2>
              <ul className="plain-list">
                {data.applications.upcoming_deadlines.map((d) => (
                  <li key={d.application_id} className="row-between wrap">
                    <span>{d.role} · {d.company} <span className="muted small">({STATUS_LABEL[d.status] || d.status})</span></span>
                    <span className="small">{d.deadline} · {d.days_left === 0 ? "today" : `in ${d.days_left} day${d.days_left === 1 ? "" : "s"}`}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}

      <div>
        <h2>Modules</h2>
        <div className="grid">
          {MODULES.map((m) => (
            <Link key={m.path} to={m.path} className="card module-card">
              <div className="module-title">
                {m.num ? `${m.num}. ` : ""}
                {m.label}
              </div>
              <div className="muted small">{m.desc}</div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
