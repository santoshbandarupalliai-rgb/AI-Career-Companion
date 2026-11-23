"""Export docs/02_PRODUCT_KNOWLEDGE_DOCUMENT.md to DOCX and PDF.

Run from the repo root:   backend\\.venv\\Scripts\\python backend\\scripts\\export_pkd.py
Output:                   docs/exports/Product_Knowledge_Document.docx and .pdf

No extra dependencies: python-docx writes the DOCX, PyMuPDF (already used for resume parsing)
lays out the PDF from simple HTML. Handles the Markdown subset the document uses: headings,
paragraphs, bullet and numbered lists, tables, fenced code, **bold**, *italic* and `code`.
"""

import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "docs" / "02_PRODUCT_KNOWLEDGE_DOCUMENT.md"
OUT = ROOT / "docs" / "exports"

_INLINE = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*)")


def parse(md: str) -> list[tuple]:
    """Markdown -> blocks: ("h", level, text) ("p", text) ("ul", [items]) ("ol", [items]) ("code", text) ("table", rows)."""
    blocks: list[tuple] = []
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            i += 1
            buf = []
            while i < len(lines) and not lines[i].startswith("```"):
                buf.append(lines[i])
                i += 1
            blocks.append(("code", "\n".join(buf)))
            i += 1
            continue
        m = re.match(r"^(#{1,6})\s+(.*\S)\s*$", line)
        if m:
            blocks.append(("h", len(m.group(1)), m.group(2)))
            i += 1
            continue
        if line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            blocks.append(("table", rows))
            continue
        if re.match(r"^\s*[-*]\s+", line):
            items = []
            while i < len(lines) and re.match(r"^\s*[-*]\s+", lines[i]):
                items.append(re.sub(r"^\s*[-*]\s+", "", lines[i]))
                i += 1
            blocks.append(("ul", items))
            continue
        if re.match(r"^\s*\d+\.\s+", line):
            items = []
            while i < len(lines) and re.match(r"^\s*\d+\.\s+", lines[i]):
                items.append(re.sub(r"^\s*\d+\.\s+", "", lines[i]))
                i += 1
            blocks.append(("ol", items))
            continue
        if not line.strip():
            i += 1
            continue
        para = [line.strip()]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#{1,6}\s|```|\||\s*[-*]\s+|\s*\d+\.\s+)", lines[i]):
            para.append(lines[i].strip())
            i += 1
        blocks.append(("p", " ".join(para)))
    return blocks


# ---------- DOCX ----------

def _runs(par, text: str) -> None:
    from docx.shared import Pt

    for part in _INLINE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            par.add_run(part[2:-2]).bold = True
        elif part.startswith("`") and part.endswith("`") and len(part) > 2:
            r = par.add_run(part[1:-1])
            r.font.name = "Consolas"
            r.font.size = Pt(9.5)
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            par.add_run(part[1:-1]).italic = True
        else:
            par.add_run(part)


def write_docx(blocks: list[tuple], path: Path) -> None:
    import docx
    from docx.shared import Pt

    d = docx.Document()
    d.styles["Normal"].font.name = "Calibri"
    d.styles["Normal"].font.size = Pt(11)
    for b in blocks:
        kind = b[0]
        if kind == "h":
            d.add_heading(re.sub(r"[*`]", "", b[2]), level=min(b[1] - 1, 4) if b[1] > 1 else 0)
        elif kind == "p":
            _runs(d.add_paragraph(), b[1])
        elif kind in ("ul", "ol"):
            style = "List Bullet" if kind == "ul" else "List Number"
            for item in b[1]:
                _runs(d.add_paragraph(style=style), item)
        elif kind == "code":
            p = d.add_paragraph()
            r = p.add_run(b[1])
            r.font.name = "Consolas"
            r.font.size = Pt(8.5)
        elif kind == "table":
            rows = b[1]
            cols = max(len(r) for r in rows)
            t = d.add_table(rows=len(rows), cols=cols)
            t.style = "Table Grid"
            for ri, row in enumerate(rows):
                for ci in range(cols):
                    cell = t.cell(ri, ci)
                    cell.text = ""
                    _runs(cell.paragraphs[0], row[ci] if ci < len(row) else "")
                    if ri == 0:
                        for run in cell.paragraphs[0].runs:
                            run.bold = True
            d.add_paragraph()
    d.save(str(path))


# ---------- PDF ----------

def _inline_html(text: str) -> str:
    out = []
    for part in _INLINE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            out.append(f"<b>{html.escape(part[2:-2])}</b>")
        elif part.startswith("`") and part.endswith("`") and len(part) > 2:
            out.append(f"<code>{html.escape(part[1:-1])}</code>")
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            out.append(f"<i>{html.escape(part[1:-1])}</i>")
        else:
            out.append(html.escape(part))
    return "".join(out)


def to_html(blocks: list[tuple]) -> str:
    css = (
        "body{font-family:sans-serif;font-size:10pt;line-height:1.35}"
        "h1{font-size:20pt;margin-top:0}h2{font-size:15pt;margin-top:14pt}h3{font-size:12pt;margin-top:10pt}h4{font-size:11pt}"
        "code,pre{font-family:monospace;font-size:8.5pt}pre{background-color:#f0f0f0;padding:4pt}"
        "table{border-collapse:collapse}td,th{border:1px solid #888;padding:3pt;font-size:9pt}th{background-color:#e8e8e8}"
    )
    parts = [f"<html><head><style>{css}</style></head><body>"]
    for b in blocks:
        kind = b[0]
        if kind == "h":
            lvl = min(b[1], 4)
            parts.append(f"<h{lvl}>{_inline_html(b[2])}</h{lvl}>")
        elif kind == "p":
            parts.append(f"<p>{_inline_html(b[1])}</p>")
        elif kind in ("ul", "ol"):
            tag = "ul" if kind == "ul" else "ol"
            parts.append(f"<{tag}>" + "".join(f"<li>{_inline_html(x)}</li>" for x in b[1]) + f"</{tag}>")
        elif kind == "code":
            parts.append(f"<pre>{html.escape(b[1])}</pre>")
        elif kind == "table":
            rows = b[1]
            parts.append("<table>")
            for ri, row in enumerate(rows):
                tag = "th" if ri == 0 else "td"
                parts.append("<tr>" + "".join(f"<{tag}>{_inline_html(c)}</{tag}>" for c in row) + "</tr>")
            parts.append("</table>")
    parts.append("</body></html>")
    return "".join(parts)


def write_pdf(blocks: list[tuple], path: Path) -> None:
    import pymupdf

    story = pymupdf.Story(html=to_html(blocks))
    writer = pymupdf.DocumentWriter(str(path))
    page_rect = pymupdf.paper_rect("a4")
    content = page_rect + (54, 54, -54, -54)
    more = True
    while more:
        dev = writer.begin_page(page_rect)
        more, _ = story.place(content)
        story.draw(dev)
        writer.end_page()
    writer.close()


def main() -> int:
    if not SRC.exists():
        print(f"Missing {SRC}", file=sys.stderr)
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    blocks = parse(SRC.read_text(encoding="utf-8"))
    write_docx(blocks, OUT / "Product_Knowledge_Document.docx")
    write_pdf(blocks, OUT / "Product_Knowledge_Document.pdf")
    print(f"Wrote {OUT / 'Product_Knowledge_Document.docx'} and .pdf ({len(blocks)} blocks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
