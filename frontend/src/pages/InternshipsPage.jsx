import { useCallback, useEffect, useRef, useState } from "react";
import { api, errorMessage } from "../api/client.js";
import AddInternship from "../components/AddInternship.jsx";

const PAGE = 12;
const MODE_LABEL = { remote: "Remote", onsite: "On-site", hybrid: "Hybrid" };

function InternshipCard({ item, onDelete }) {
  const [open, setOpen] = useState(false);
  const meta = [item.location, MODE_LABEL[item.work_mode], item.stipend, item.duration]
    .filter(Boolean)
    .filter((v, i, a) => a.findIndex((x) => x.toLowerCase() === v.toLowerCase()) === i);
  return (
    <article className="card stack internship">
      <div className="row-between wrap">
        <div>
          <h2>{item.title}</h2>
          <div className="muted">{item.company}</div>
        </div>
        <div className="row">
          {item.score != null && <span className="badge" title="Semantic similarity to your search (0 to 1). Higher is more relevant.">Relevance {item.score.toFixed(2)}</span>}
          <span className={`badge ${item.source === "sample" ? "sample" : "complete"}`} title={item.source === "sample" ? "Fictional sample posting for demonstration" : "Added by you"}>
            {item.source === "sample" ? "Sample" : "Yours"}
          </span>
        </div>
      </div>
      {meta.length > 0 && <div className="muted small">{meta.join(" · ")}</div>}
      <ul className="chips">
        {item.skills.map((s) => (
          <li key={s.name} className={`chip static ${s.importance === "preferred" ? "preferred" : ""}`} title={s.importance}>
            {s.name}
          </li>
        ))}
      </ul>
      {item.snippet && !open && <p className="small muted snippet">…{item.snippet}…</p>}
      {open && (
        <div className="stack">
          <p className="small pre">{item.description}</p>
          <dl className="kv">
            {item.education_req && <div><dt>Education</dt><dd>{item.education_req}</dd></div>}
            {item.experience_req && <div><dt>Experience</dt><dd>{item.experience_req}</dd></div>}
            {item.eligibility_text && <div><dt>Eligibility</dt><dd>{item.eligibility_text}</dd></div>}
            {item.apply_url && (
              <div><dt>Apply</dt><dd><a href={item.apply_url} target="_blank" rel="noopener noreferrer">{item.apply_url}</a></dd></div>
            )}
          </dl>
          {item.source === "sample" && <p className="muted small">This is a fictional sample posting. There is nothing to apply to.</p>}
        </div>
      )}
      <div className="actions">
        <button className="btn btn-ghost small" onClick={() => setOpen(!open)}>{open ? "Hide details" : "Show details"}</button>
        {item.source === "user" && (
          <button className="btn btn-ghost small danger" onClick={() => onDelete(item)}>Delete</button>
        )}
      </div>
    </article>
  );
}

export default function InternshipsPage() {
  const [items, setItems] = useState(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [adding, setAdding] = useState(false);
  const [smart, setSmart] = useState(true);
  const [q, setQ] = useState("");
  const [submittedQ, setSubmittedQ] = useState("");
  const [filters, setFilters] = useState({ work_mode: "", source: "", skill: "", location: "" });
  const reqId = useRef(0);

  const load = useCallback(
    async (offset = 0) => {
      const id = ++reqId.current; // ignore out-of-order responses
      setLoading(true);
      setError("");
      const params = Object.fromEntries(Object.entries(filters).filter(([, v]) => v));
      try {
        let data;
        if (submittedQ && smart) {
          const res = await api.get("/internships/search", { params: { ...params, q: submittedQ, limit: 15 }, timeout: 60000 });
          data = { items: res.data, total: res.data.length };
        } else {
          const res = await api.get("/internships", { params: { ...params, q: submittedQ || undefined, limit: PAGE, offset } });
          data = res.data;
        }
        if (id !== reqId.current) return;
        setItems((prev) => (offset > 0 && prev ? [...prev, ...data.items] : data.items));
        setTotal(data.total);
      } catch (err) {
        if (id === reqId.current) setError(errorMessage(err, "Could not load internships."));
      } finally {
        if (id === reqId.current) setLoading(false);
      }
    },
    [filters, submittedQ, smart]
  );

  useEffect(() => {
    load(0);
  }, [load]);

  const setFilter = (k) => (e) => setFilters({ ...filters, [k]: e.target.value });
  const searching = Boolean(submittedQ);

  function submit(e) {
    e.preventDefault();
    const next = q.trim();
    if (smart && next.length === 1) return setError("Type at least 2 characters to search.");
    setSubmittedQ(next);
  }

  async function remove(item) {
    if (!window.confirm(`Delete "${item.title}" at ${item.company}? This cannot be undone.`)) return;
    try {
      await api.delete(`/internships/${item.id}`);
      setItems((prev) => prev.filter((i) => i.id !== item.id));
      setTotal((t) => t - 1);
    } catch (err) {
      setError(errorMessage(err, "Could not delete."));
    }
  }

  return (
    <div className="stack-lg">
      <div className="row-between wrap">
        <div>
          <h1>Internship Knowledge Base</h1>
          <p className="muted">
            Browse postings or search by meaning, e.g. “build a chatbot over documents”. Postings marked <span className="badge sample">Sample</span> are
            fictional demo data.
          </p>
        </div>
        <button className="btn btn-primary" onClick={() => setAdding(true)} disabled={adding}>
          Add from job description
        </button>
      </div>

      {adding && (
        <AddInternship
          onCancel={() => setAdding(false)}
          onSaved={() => {
            setAdding(false);
            load(0);
          }}
        />
      )}

      <form className="card stack" onSubmit={submit}>
        <div className="row wrap">
          <input
            className="grow"
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={smart ? "Describe what you are looking for…" : "Title or company"}
            aria-label="Search internships"
          />
          <button className="btn btn-primary">Search</button>
          {searching && (
            <button type="button" className="btn btn-ghost" onClick={() => { setQ(""); setSubmittedQ(""); }}>
              Clear
            </button>
          )}
        </div>
        <div className="row wrap">
          <label className="inline">
            <input type="checkbox" checked={smart} onChange={(e) => setSmart(e.target.checked)} /> Smart (semantic) search
          </label>
          <select value={filters.work_mode} onChange={setFilter("work_mode")} aria-label="Work mode">
            <option value="">Any work mode</option>
            <option value="remote">Remote</option>
            <option value="onsite">On-site</option>
            <option value="hybrid">Hybrid</option>
          </select>
          <select value={filters.source} onChange={setFilter("source")} aria-label="Source">
            <option value="">Samples and mine</option>
            <option value="sample">Samples only</option>
            <option value="user">Mine only</option>
          </select>
          <input value={filters.skill} onChange={setFilter("skill")} placeholder="Skill, e.g. Python" aria-label="Filter by skill" />
          <input value={filters.location} onChange={setFilter("location")} placeholder="Location" aria-label="Filter by location" />
        </div>
      </form>

      {error && <div className="alert">{error}</div>}
      {items === null ? (
        !error && <p className="muted">Loading…</p>
      ) : items.length === 0 ? (
        <div className="card notice">
          {loading ? "Searching…" : searching || Object.values(filters).some(Boolean)
            ? "No internships match. Try different words or clear a filter."
            : "No internships yet. Add one from a job description."}
        </div>
      ) : (
        <>
          <p className="muted small" aria-live="polite">
            {searching && smart ? `Top ${items.length} by relevance` : `Showing ${items.length} of ${total}`}
            {loading && " · updating…"}
          </p>
          <div className="internship-list">
            {items.map((item) => (
              <InternshipCard key={item.id} item={item} onDelete={remove} />
            ))}
          </div>
          {!(searching && smart) && items.length < total && (
            <button className="btn btn-ghost" onClick={() => load(items.length)} disabled={loading}>
              {loading ? "Loading…" : "Load more"}
            </button>
          )}
        </>
      )}
    </div>
  );
}
