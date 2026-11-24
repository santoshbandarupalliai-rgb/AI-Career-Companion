import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, errorMessage, tokenStore } from "../api/client.js";

// Opened from the link in the verification email. Works whether or not the student is signed in.
export default function VerifyEmailPage() {
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const [state, setState] = useState(token ? "working" : "missing");
  const [message, setMessage] = useState("");
  const started = useRef(false);

  useEffect(() => {
    if (!token || started.current) return;
    started.current = true; // React strict mode runs effects twice; a token can only be used once
    api
      .post("/auth/verify-email", { token })
      .then(() => setState("ok"))
      .catch((err) => {
        setMessage(errorMessage(err, "Could not verify your email."));
        setState("error");
      });
  }, [token]);

  const signedIn = !!(tokenStore.access || tokenStore.refresh);

  return (
    <div className="auth-page">
      <div className="auth-hero" aria-hidden="true">
        <div className="brand"><span className="brand-mark">CC</span><span>Career Companion</span></div>
        <h2>One quick step to confirm it's you.</h2>
        <p>Verified emails keep accounts safe and let us reach you about your applications.</p>
      </div>
      <div className="card auth-card" role="status">
        <h1>Verify your email</h1>
        {state === "working" && <p className="muted">Checking your link…</p>}
        {state === "ok" && (
          <>
            <div className="ok">Your email address is verified. Thank you!</div>
            <Link className="btn btn-primary" to={signedIn ? "/dashboard" : "/login"}>{signedIn ? "Go to the dashboard" : "Sign in"}</Link>
          </>
        )}
        {state === "error" && (
          <>
            <div className="alert" role="alert">{message}</div>
            <Link className="btn btn-primary" to={signedIn ? "/dashboard" : "/login"}>{signedIn ? "Go to the dashboard to resend the link" : "Sign in to resend the link"}</Link>
          </>
        )}
        {state === "missing" && (
          <>
            <div className="alert" role="alert">This link is missing its token. Open the link from your email again.</div>
            <Link className="btn btn-primary" to="/login">Sign in</Link>
          </>
        )}
      </div>
    </div>
  );
}
