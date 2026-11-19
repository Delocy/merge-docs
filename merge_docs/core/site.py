"""Build the static catalogue site for GitHub Pages: search, one page per module, recent API changes."""
from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from pathlib import Path

from merge_docs.core.contract import ModuleContract, Shape
from merge_docs.core.diff import Change
from merge_docs.core.notes import notes_path


@dataclass(frozen=True)
class MergedChanges:
    pr: int
    title: str
    url: str
    merged_at: str
    changes: tuple[Change, ...]


def page_name(slug: str) -> str:
    """A file and URL name that can't carry quotes, spaces or slashes, whatever the repo's file names are."""
    return re.sub(r"[^A-Za-z0-9._-]+", "-", slug.replace("/", "-")).strip("-") + ".html"


def _e(text: object) -> str:
    return html.escape(str(text), quote=True)


def _inline(text: str) -> str:
    """Escape text, then turn `code` spans into <code>."""
    return re.sub(r"`([^`\n]+)`", lambda m: f"<code>{m.group(1)}</code>", _e(text))


def render_notes(note_md: str) -> str:
    """A small, safe subset of Markdown: headings, bullets, paragraphs, inline code, fenced code."""
    out, para, items, fence, code = [], [], [], None, []

    def flush():
        if para:
            out.append(f"<p>{_inline(' '.join(para))}</p>")
            para.clear()
        if items:
            out.append("<ul>" + "".join(f"<li>{_inline(i)}</li>" for i in items) + "</ul>")
            items.clear()

    for line in note_md.split("\n"):
        if line.startswith("```") or line.startswith("~~~"):
            if fence:
                out.append(f"<pre><code>{_e(chr(10).join(code))}</code></pre>")
                fence, code = None, []
            else:
                flush()
                fence = line[:3]
            continue
        if fence:
            code.append(line)
        elif not line.strip():
            flush()
        elif m := re.match(r"^(#{1,6}) (.*)$", line):
            flush()
            out.append(f"<h3>{_inline(m.group(2))}</h3>")
        elif m := re.match(r"^[-*] (.*)$", line):
            if para:
                flush()
            items.append(m.group(1))
        elif items and line.startswith("  "):
            items[-1] += " " + line.strip()
        else:
            para.append(line.strip())
    if fence:
        out.append(f"<pre><code>{_e(chr(10).join(code))}</code></pre>")
    flush()
    return "\n".join(out)


def _method(m: str) -> str:
    return f'<span class="method m-{_e(m.lower())}">{_e(m)}</span>'


def _shape(shape: Shape, empty: str) -> str:
    if not shape.declared:
        return f'<p class="muted">{_e(empty)}</p>'
    head = f'<p class="model">Model <code>{_e(shape.label)}</code></p>'
    if not shape.fields:
        return head + '<p class="muted">No fields.</p>'
    rows = "".join(
        f"<tr><td><code>{_e(f.name)}</code></td><td><code>{_e(f.type)}</code></td>"
        f"<td>{'<span class=\"req\">required</span>' if f.required else 'optional'}</td></tr>"
        for f in shape.fields
    )
    return head + f'<table><thead><tr><th>Field</th><th>Type</th><th>Required</th></tr></thead><tbody>{rows}</tbody></table>'


def _layout(title: str, repo: str, body: str, depth: int = 0, active: str = "") -> str:
    up = "../" * depth
    nav = "".join(
        f'<a href="{up}{href}"{" aria-current=\"page\"" if active == key else ""}>{label}</a>'
        for key, href, label in [("search", "index.html", "Catalogue"), ("changes", "changes.html", "API changes")]
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(title)}</title>
<link rel="stylesheet" href="{up}style.css">
</head>
<body>
<header class="top"><div class="wrap">
  <a class="brand" href="{up}index.html">API Catalogue <span>{_e(repo)}</span></a>
  <nav>{nav}</nav>
</div></header>
<main class="wrap">
{body}
</main>
<footer class="wrap muted">Read from the code on every push by merge-docs. Contracts show only what the code declares.</footer>
</body>
</html>
"""


CSS = """
:root { --bg:#f6f7f5; --surface:#ffffff; --ink:#1b2126; --muted:#5d6a72; --rule:#dde2e0; --accent:#0d6e6e;
  --get:#1f7a4a; --post:#1f5fa8; --put:#9a6a00; --patch:#9a6a00; --delete:#b03a3a; --req:#9a3412;
  --mono: ui-monospace, "SF Mono", Menlo, Consolas, monospace; --sans: Inter, -apple-system, "Segoe UI", system-ui, sans-serif; }
@media (prefers-color-scheme: dark) { :root { --bg:#111517; --surface:#181e21; --ink:#e3e8ea; --muted:#93a1a8; --rule:#29333a;
  --accent:#5cc7c1; --get:#5ccf8f; --post:#79aef2; --put:#e2b54d; --patch:#e2b54d; --delete:#f08484; --req:#f2a074; } }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--ink); font: 16px/1.55 var(--sans); }
.wrap { max-width: 960px; margin: 0 auto; padding-left: max(16px, env(safe-area-inset-left)); padding-right: max(16px, env(safe-area-inset-right)); }
.top { background: var(--surface); border-bottom: 1px solid var(--rule); }
.top .wrap { display:flex; flex-wrap:wrap; gap: .5rem 1.5rem; align-items:center; justify-content:space-between; padding-block: .9rem; }
.brand { font-weight: 700; color: var(--ink); text-decoration: none; letter-spacing: -.01em; }
.brand span { font: 500 .85rem var(--mono); color: var(--muted); margin-left: .5rem; }
nav { display:flex; gap: 1rem; } nav a { color: var(--muted); text-decoration:none; } nav a[aria-current] { color: var(--accent); font-weight:600; }
main { padding-block: 2rem 3rem; }
h1 { font-size: 1.7rem; letter-spacing: -.02em; margin: 0 0 .25rem; overflow-wrap:anywhere; }
h2 { font-size: 1.1rem; margin: 0; display:flex; flex-wrap:wrap; gap:.6rem; align-items:center; font-family: var(--mono); overflow-wrap:anywhere; }
a { color: var(--accent); }
code { font-family: var(--mono); font-size: .9em; }
.muted { color: var(--muted); }
.search { width:100%; font: inherit; padding: .8rem 1rem; border: 1px solid var(--rule); border-radius: 8px; background: var(--surface); color: var(--ink); margin: 1rem 0; }
.search:focus { outline: 2px solid var(--accent); outline-offset: 1px; }
.results { list-style:none; padding:0; margin:0; display:grid; gap:.6rem; }
.results li { background: var(--surface); border: 1px solid var(--rule); border-radius: 8px; padding: .8rem 1rem; }
.results a { font-weight:600; text-decoration:none; overflow-wrap:anywhere; }
.results .eps { display:flex; flex-wrap:wrap; gap:.35rem .8rem; margin-top:.35rem; font: .85rem var(--mono); color: var(--muted); }
.endpoint { background: var(--surface); border:1px solid var(--rule); border-radius: 10px; padding: 1rem 1.1rem; margin-top: 1rem; }
.endpoint h3 { font-size: .8rem; text-transform: uppercase; letter-spacing: .08em; color: var(--muted); margin: 1rem 0 .4rem; }
.handler { margin:.3rem 0 0; font-size:.9rem; }
.method { font: 700 .75rem var(--mono); padding: .15rem .45rem; border-radius: 4px; color: #fff; letter-spacing: .04em; }
.m-get { background: var(--get); } .m-post { background: var(--post); } .m-put, .m-patch { background: var(--put); } .m-delete { background: var(--delete); }
@media (prefers-color-scheme: dark) { .method { color: #111517; } }
.table-wrap { overflow-x:auto; }
table { border-collapse: collapse; width: 100%; font-size: .92rem; }
th, td { text-align:left; padding: .4rem .6rem; border-bottom: 1px solid var(--rule); vertical-align: top; }
th { font-size: .75rem; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); font-weight: 600; }
.req { color: var(--req); font-weight: 600; }
.model { margin: 0 0 .4rem; font-size: .9rem; }
.notes { background: var(--surface); border:1px solid var(--rule); border-radius: 10px; padding: .4rem 1.1rem; margin-top: 2rem; }
.notes h3 { margin: .9rem 0 .3rem; }
pre { overflow-x:auto; background: var(--bg); padding: .7rem; border-radius: 6px; }
.pr { background: var(--surface); border:1px solid var(--rule); border-radius:10px; padding: .8rem 1.1rem; margin-top: 1rem; }
.pr h2 { font-family: var(--sans); font-size: 1rem; }
.pr ul { margin: .5rem 0 0; padding-left: 1.2rem; font-size: .92rem; }
footer { padding-block: 0 2.5rem; font-size: .85rem; }
"""

JS = """
(function () {
  const input = document.getElementById('q');
  const list = document.getElementById('results');
  const count = document.getElementById('count');
  let index = [];
  function esc(s) { return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
  function render(items) {
    count.textContent = items.length + (items.length === 1 ? ' feature' : ' features');
    list.innerHTML = items.map(e =>
      '<li><a href="' + esc(e.url) + '">' + esc(e.slug) + '</a><div class="eps">' +
      e.endpoints.map(p => '<span>' + esc(p) + '</span>').join('') + '</div></li>').join('') ||
      '<li class="muted">No feature matches. Try a path segment such as <code>orders</code> or a field name.</li>';
  }
  function filter() {
    const terms = input.value.toLowerCase().split(/\\s+/).filter(Boolean);
    render(index.filter(e => {
      const hay = (e.slug + ' ' + e.endpoints.join(' ') + ' ' + e.fields.join(' ')).toLowerCase();
      return terms.every(t => hay.includes(t));
    }));
  }
  fetch('search.json').then(r => r.json()).then(data => { index = data; filter(); });
  input.addEventListener('input', filter);
})();
"""


def build_site(contracts: dict[str, ModuleContract], notes: dict[str, str], changes: list[MergedChanges],
               repo: str, out_dir: Path) -> list[Path]:
    out = Path(out_dir)
    (out / "features").mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    def write(rel: str, text: str) -> None:
        path = out / rel
        path.write_text(text)
        written.append(path)

    modules = sorted(contracts.values(), key=lambda c: c.slug)
    index = [{
        "slug": c.slug, "url": f"features/{page_name(c.slug)}",
        "endpoints": [e.key for e in c.endpoints],
        "fields": sorted({f.name for e in c.endpoints for s in (e.request, e.response) for f in s.fields}),
    } for c in modules]
    write("search.json", json.dumps(index, indent=1))
    write("style.css", CSS)
    write("search.js", JS)

    static_list = "".join(
        f'<li><a href="features/{_e(page_name(c.slug))}">{_e(c.slug)}</a><div class="eps">'
        + "".join(f"<span>{_e(e.key)}</span>" for e in c.endpoints) + "</div></li>" for c in modules)
    write("index.html", _layout(f"API Catalogue · {repo}", repo, f"""
<h1>Find an API</h1>
<p class="muted">Every FastAPI endpoint in <code>{_e(repo)}</code>, read from the code. Search by feature, path or field name.</p>
<label for="q" class="muted">Search</label>
<input id="q" class="search" type="search" placeholder="e.g. orders, /api/stats, customer_id" autocomplete="off">
<p id="count" class="muted">{len(modules)} features</p>
<ul id="results" class="results">{static_list}</ul>
<script src="search.js"></script>
""", active="search"))

    for c in modules:
        cards = []
        for e in c.endpoints:
            cards.append(f"""<section class="endpoint" id="{_e(page_name(e.key)[:-5])}">
<h2>{_method(e.method)} <span>{_e(e.path)}</span></h2>
<p class="handler muted">Handler <code>{_e(e.func)}</code></p>
<h3>Request body</h3><div class="table-wrap">{_shape(e.request, "No request body declared in the code.")}</div>
<h3>Response</h3><div class="table-wrap">{_shape(e.response, "Response shape not declared in the code.")}</div>
</section>""")
        note = notes.get(c.module)
        note_html = render_notes(note) if note else (
            f'<p class="muted">No notes yet. Add <code>{_e(notes_path(c.module))}</code> to explain how this feature works.</p>')
        write(f"features/{page_name(c.slug)}", _layout(f"{c.slug} · API Catalogue", repo, f"""
<p class="muted"><a href="../index.html">Catalogue</a> / feature</p>
<h1>{_e(c.slug)}</h1>
<p class="muted">Source <code>{_e(c.module)}</code> · {len(c.endpoints)} endpoint{'s' if len(c.endpoints) != 1 else ''}</p>
{''.join(cards) or '<p class="muted">No endpoints.</p>'}
<section class="notes"><h3>Notes</h3>{note_html}</section>
""", depth=1))

    prs = []
    for m in changes:
        items = "".join(f"<li><code>{_e(ch.module)}</code>: {_inline(ch.detail)}</li>" for ch in m.changes)
        prs.append(f'<section class="pr"><h2><a href="{_e(m.url)}">#{m.pr} {_e(m.title)}</a>'
                   f'<span class="muted">merged {_e(m.merged_at)}</span></h2><ul>{items}</ul></section>')
    write("changes.html", _layout(f"API changes · {repo}", repo, f"""
<h1>Recent API changes</h1>
<p class="muted">Contract changes from recently merged pull requests.</p>
{''.join(prs) or '<p class="muted">No merged PRs with API changes yet.</p>'}
""", active="changes"))
    return written
