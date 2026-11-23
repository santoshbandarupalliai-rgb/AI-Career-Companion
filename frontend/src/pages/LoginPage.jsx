import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext.jsx";
import { errorMessage } from "../api/client.js";

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await login(email.trim(), password);
      navigate(location.state?.from || "/dashboard", { replace: true });
    } catch (err) {
      setError(errorMessage(err, "Sign-in failed."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-hero" aria-hidden="true">
        <div className="brand"><span className="brand-mark">CC</span><span>Career Companion</span></div>
        <h2>From resume to offer, with nothing made up.</h2>
        <p>Parse your resume, verify your skills, find explainable internship matches, tailor honest applications and track every step.</p>
      </div>
      <form className="card auth-card" onSubmit={onSubmit} noValidate>
        <h1>Sign in</h1>
        <p className="muted">Welcome back to Career Companion.</p>
        <label>
          Email
          <input type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        <label>
          Password
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        {error && <div className="alert" role="alert">{error}</div>}
        <button className="btn btn-primary" disabled={busy || !email || !password}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
        <p className="muted small">
          No account yet? <Link to="/register">Create one</Link>
        </p>
      </form>
    </div>
  );
}
