import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext.jsx";
import { MODULES } from "../modules.js";

export default function DashboardPage() {
  const { user } = useAuth();
  const firstName = user?.full_name?.split(" ")[0] || "there";
  return (
    <div>
      <h1>Hi, {firstName}</h1>
      <p className="muted">Start with your profile and resume. Every other module builds on them.</p>
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
  );
}
