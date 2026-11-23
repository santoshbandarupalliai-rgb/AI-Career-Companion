import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext.jsx";
import { errorMessage } from "../api/client.js";

function passwordProblem(pw) {
  if (pw.length < 8) return "At least 8 characters";
  if (!/[A-Za-z]/.test(pw) || !/\d/.test(pw)) return "Include at least one letter and one number";
  return "";
}

export default function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const pwHint = password ? passwordProblem(password) : "";
  const canSubmit = fullName.trim() && email.trim() && password && !pwHint && !busy;

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await register(fullName.trim(), email.trim(), password);
      navigate("/dashboard", { replace: true });
    } catch (err) {
      setError(errorMessage(err, "Could not create the account."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-page">
      <form className="card auth-card" onSubmit={onSubmit} noValidate>
        <h1>Create account</h1>
        <p className="muted">Start building your internship profile.</p>
        <label>
          Full name
          <input autoComplete="name" value={fullName} onChange={(e) => setFullName(e.target.value)} required />
        </label>
        <label>
          Email
          <input type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        <label>
          Password
          <input
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            aria-describedby="pw-hint"
            required
          />
          <span id="pw-hint" className={`small ${pwHint ? "warn" : "muted"}`}>
            {pwHint || "8+ characters with a letter and a number"}
          </span>
        </label>
        {error && <div className="alert" role="alert">{error}</div>}
        <button className="btn btn-primary" disabled={!canSubmit}>
          {busy ? "Creating account…" : "Create account"}
        </button>
        <p className="muted small">
          Already registered? <Link to="/login">Sign in</Link>
        </p>
      </form>
    </div>
  );
}
