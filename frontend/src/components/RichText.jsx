// Renders the small Markdown subset the assistants use (headings, bullet and numbered lists, **bold**)
// as React elements. No HTML is injected, so model output cannot add markup or scripts.

function inline(text, keyBase) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((p, i) =>
    p.startsWith("**") && p.endsWith("**") && p.length > 4 ? <strong key={`${keyBase}-${i}`}>{p.slice(2, -2)}</strong> : p
  );
}

export default function RichText({ text }) {
  const lines = (text || "").replace(/\r\n/g, "\n").split("\n");
  const blocks = [];
  let list = null;

  const flush = () => {
    if (list) {
      const Tag = list.ordered ? "ol" : "ul";
      blocks.push(<Tag key={`l${blocks.length}`} className="rt-list" start={list.ordered ? list.start : undefined}>{list.items}</Tag>);
      list = null;
    }
  };

  lines.forEach((raw, i) => {
    const line = raw.trimEnd();
    const bullet = line.match(/^\s*[*\-•]\s+(.*)$/);
    const numbered = line.match(/^\s*(\d+)[.)]\s+(.*)$/);
    const heading = line.match(/^\s*#{1,6}\s+(.*)$/);
    if (bullet || numbered) {
      const ordered = !!numbered && !bullet;
      if (!list || list.ordered !== ordered) {
        flush();
        list = { ordered, items: [], start: numbered && !bullet ? Number(numbered[1]) : undefined };
      }
      const content = bullet ? bullet[1] : numbered[2];
      list.items.push(<li key={i}>{inline(content, i)}</li>);
      return;
    }
    flush();
    if (!line.trim()) return;
    if (heading) {
      blocks.push(<p key={i} className="rt-heading">{inline(heading[1], i)}</p>);
      return;
    }
    blocks.push(<p key={i} className="rt-p">{inline(line, i)}</p>);
  });
  flush();
  return <div className="rich-text">{blocks}</div>;
}
