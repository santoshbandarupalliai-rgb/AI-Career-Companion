import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, errorMessage } from "../api/client.js";

const MAX_BYTES = 5 * 1024 * 1024;

export function formatDate(iso) {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export const STATUS_LABEL = {
  complete: "Parsed",
  partial: "Partially parsed",
  failed: "Parsing failed",
  pending: "Parsing…",
};

export default function ResumeManager({ onActiveExtraction }) {
  const [resumes, setResumes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const inputRef = useRef(null);

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/resumes");
      setResumes(data);
      const active = data.find((r) => r.is_active);
      if (active && onActiveExtraction) {
        const detail = await api.get(`/resumes/${active.id}`);
        onActiveExtraction(detail.data.extraction?.data || null);
      } else if (onActiveExtraction) {
        onActiveExtraction(null);
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [onActiveExtraction]);

  useEffect(() => {
    load();
  }, [load]);

  async function onFile(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setError("");
    setNotice("");
    if (!/\.(pdf|docx)$/i.test(file.name)) return setError("Only PDF and DOCX files are supported.");
    if (file.size > MAX_BYTES) return setError("The file is larger than 5 MB.");
    const body = new FormData();
    body.append("file", file);
    setUploading(true);
    try {
      const { data } = await api.post("/resumes", body, { timeout: 120000 });
      setNotice(
        data.extraction_status === "complete"
          ? "Resume uploaded and parsed. Review the extracted skills."
          : "Resume uploaded, but AI parsing was only partial. You can re-run it on the Resume Parsing page."
      );
      await load();
    } catch (err) {
      setError(errorMessage(err, "Upload failed."));
    } finally {
      setUploading(false);
    }
  }

  async function act(fn, okMsg) {
    setError("");
    setNotice("");
    try {
      await fn();
      if (okMsg) setNotice(okMsg);
      await load();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function download(r) {
    try {
      const res = await api.get(`/resumes/${r.id}/file`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = r.original_filename;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (err) {
      setError(errorMessage(err, "Download failed."));
    }
  }

  return (
    <section className="card stack">
      <h2>Resumes</h2>
      <div className="dropzone">
        <p className="muted small">PDF or DOCX, up to 5 MB. Text-based files only (not scans).</p>
        <input ref={inputRef} type="file" accept=".pdf,.docx" onChange={onFile} hidden />
        <button className="btn btn-primary" onClick={() => inputRef.current?.click()} disabled={uploading}>
          {uploading ? "Uploading & parsing… (up to a minute)" : "Upload resume"}
        </button>
      </div>
      {error && <div className="alert" role="alert">{error}</div>}
      {notice && (
        <div className="ok">
          {notice} <Link to="/resume">Open Resume Parsing →</Link>
        </div>
      )}
      {loading ? (
        <p className="muted">Loading…</p>
      ) : resumes.length === 0 ? (
        <p className="muted">No resumes yet.</p>
      ) : (
        <ul className="resume-list">
          {resumes.map((r) => (
            <li key={r.id} className={r.is_active ? "active" : ""}>
              <div className="resume-name" title={r.original_filename}>
                {r.original_filename}
                {r.is_active && <span className="badge">Active</span>}
              </div>
              <div className="muted small">
                {formatDate(r.uploaded_at)} · {(r.size_bytes / 1024).toFixed(0)} KB · {STATUS_LABEL[r.extraction_status]}
              </div>
              <div className="actions">
                {!r.is_active && (
                  <button className="btn btn-ghost small" onClick={() => act(() => api.post(`/resumes/${r.id}/activate`))}>
                    Make active
                  </button>
                )}
                <button className="btn btn-ghost small" onClick={() => download(r)}>
                  Download
                </button>
                <button
                  className="btn btn-ghost small danger"
                  onClick={() => {
                    if (window.confirm(`Delete "${r.original_filename}"? Unconfirmed skills found only in it are removed too.`))
                      act(() => api.delete(`/resumes/${r.id}`), "Resume deleted.");
                  }}
                >
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
