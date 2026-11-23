export default function ComingSoonPage({ module }) {
  return (
    <div>
      <h1>{module.label}</h1>
      <p className="muted">{module.desc}</p>
      <div className="card notice">Not built yet. Arrives in build phase {module.phase}.</div>
    </div>
  );
}
