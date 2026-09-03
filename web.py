"""The window onto the results. One page, one JSON endpoint, no build step.

Deliberately server-rendered from an f-string: no templating engine, no static
files, no JavaScript framework. The whole page is in this file and can be read in
one sitting.
"""

from __future__ import annotations

import html
import os

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from triage import store

app = FastAPI(title="PR Triage")

CATEGORIES = ["security", "feature", "refactor", "docs", "dependency-bump", "unclear"]

# security is red because it is the one a human must look at. `unclear` is amber
# because it means "we could not tell", also a call for a human, just a quieter one.
CATEGORY_COLOUR = {
    "security": "#c0392b",
    "feature": "#2470a8",
    "refactor": "#7d5ba6",
    "docs": "#5c6b73",
    "dependency-bump": "#4a7c59",
    "unclear": "#b8860b",
}

# How the answer was reached. Shown on every row on purpose: when something odd
# appears in a live demo, this column explains it without anyone guessing.
SOURCE_HELP = {
    "model": "first answer, confident enough to keep",
    "model_retry": "first answer was unusable or unsure; stricter retry worked",
    "fallback": "both attempts failed, we wrote 'unclear' rather than guessing",
    "skipped": "never asked the model (draft PR, or nothing to read)",
}

CSS = """
:root { --bg:#fbfbfa; --fg:#1a1a1a; --muted:#6b6b6b; --line:#e3e3e0; --card:#fff; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#191918; --fg:#eeeeec; --muted:#9a9a95; --line:#333330; --card:#212120; }
}
* { box-sizing:border-box; }
body { margin:0; padding:2rem 1.5rem; background:var(--bg); color:var(--fg);
       font:14px/1.5 ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif; }
.wrap { max-width:1400px; margin:0 auto; }
h1 { font-size:1.35rem; margin:0 0 .25rem; }
.sub { color:var(--muted); margin:0 0 1.5rem; font-size:.9rem; }
.filters { display:flex; gap:.4rem; flex-wrap:wrap; margin-bottom:1.25rem; }
.filters a { text-decoration:none; padding:.3rem .7rem; border:1px solid var(--line);
             border-radius:999px; color:var(--fg); font-size:.85rem; background:var(--card); }
.filters a.on { background:var(--fg); color:var(--bg); border-color:var(--fg); }
.scroll { overflow-x:auto; border:1px solid var(--line); border-radius:8px; background:var(--card); }
table { border-collapse:collapse; width:100%; min-width:1100px; }
th { text-align:left; font-size:.72rem; text-transform:uppercase; letter-spacing:.05em;
     color:var(--muted); padding:.7rem .8rem; border-bottom:1px solid var(--line); font-weight:600; }
td { padding:.7rem .8rem; border-bottom:1px solid var(--line); vertical-align:top; }
tr:last-child td { border-bottom:none; }
.badge { display:inline-block; padding:.15rem .55rem; border-radius:4px; color:#fff;
         font-size:.75rem; font-weight:600; white-space:nowrap; }
.src { font-size:.75rem; color:var(--muted); font-family:ui-monospace,monospace; white-space:nowrap; }
.src.fallback, .src.skipped { color:#b8860b; }
.mono { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.8rem; }
.title { max-width:320px; }
.note { max-width:340px; color:var(--muted); font-size:.85rem; }
a.pr { color:inherit; text-decoration:none; border-bottom:1px solid var(--line); }
.empty { padding:3rem 1rem; text-align:center; color:var(--muted); }
.legend { margin-top:1.25rem; font-size:.8rem; color:var(--muted); }
.legend code { background:var(--card); border:1px solid var(--line); padding:.05rem .3rem; border-radius:3px; }
"""


def _esc(v) -> str:
    return html.escape(str(v)) if v is not None else ""


def _row(r: dict) -> str:
    cat = r["category"]
    colour = CATEGORY_COLOUR.get(cat, "#666")
    src = r["label_source"]
    pr = f'{_esc(r["repo"])}#{r["pr_number"]}'
    link = (r.get("pr_url") or "").replace("api.github.com/repos", "github.com").replace("/pulls/", "/pull/")
    return f"""<tr>
  <td class="mono"><a class="pr" href="{_esc(link)}" target="_blank" rel="noopener">{pr}</a></td>
  <td class="title">{_esc(r.get("title") or "—")}</td>
  <td><span class="badge" style="background:{colour}">{_esc(cat)}</span></td>
  <td class="mono">{r["confidence"]:.2f}</td>
  <td><span class="src {_esc(src)}" title="{_esc(SOURCE_HELP.get(src, ""))}">{_esc(src)}</span></td>
  <td>{_esc(r.get("affected_area") or "—")}</td>
  <td class="note">{_esc(r.get("risk_note") or r.get("rationale") or "—")}</td>
  <td class="mono">{_esc(r.get("files_changed"))}</td>
  <td class="mono">{_esc(r.get("llm_calls"))}</td>
  <td class="mono">{_esc(r.get("latency_ms"))}ms</td>
</tr>"""


@app.get("/", response_class=HTMLResponse)
def index(category: str | None = None, limit: int = 100):
    conn = store.connect()
    try:
        rows = store.recent(conn, category, limit)
        counts = store.counts_by_category(conn)
    finally:
        conn.close()

    total = sum(counts.values())
    chips = [f'<a href="/" class="{"on" if not category else ""}">all · {total}</a>']
    for c in CATEGORIES:
        n = counts.get(c, 0)
        chips.append(f'<a href="/?category={c}" class="{"on" if category == c else ""}">{c} · {n}</a>')

    body = "".join(_row(r) for r in rows) if rows else ""
    table = f"""<div class="scroll"><table>
  <thead><tr>
    <th>PR</th><th>Title</th><th>Category</th><th>Conf</th><th>How</th>
    <th>Area</th><th>Risk note</th><th>Files</th><th>Calls</th><th>Latency</th>
  </tr></thead><tbody>{body}</tbody></table></div>""" if rows else """
  <div class="scroll"><div class="empty">
    Nothing triaged yet.<br><br>
    Recorded rows should load on <code>docker compose up</code>.
    If this is empty, check <code>docker compose logs seed</code>.
  </div></div>"""

    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>PR Triage</title><meta http-equiv="refresh" content="10">
<style>{CSS}</style></head><body><div class="wrap">
<h1>Pull request triage</h1>
<p class="sub">New PRs from the GitHub public firehose, classified by reading the actual diff.
Page refreshes every 10s.</p>
<div class="filters">{"".join(chips)}</div>
{table}
<p class="legend"><strong>How</strong> says where the label came from,
<code>model</code> {SOURCE_HELP['model']} ·
<code>model_retry</code> {SOURCE_HELP['model_retry']} ·
<code>fallback</code> {SOURCE_HELP['fallback']} ·
<code>skipped</code> {SOURCE_HELP['skipped']}.</p>
</div></body></html>"""


@app.get("/api/results")
def api_results(category: str | None = None, limit: int = 100):
    conn = store.connect()
    try:
        rows = store.recent(conn, category, limit)
    finally:
        conn.close()
    for r in rows:
        for k in ("event_created_at", "triaged_at"):
            if r.get(k):
                r[k] = r[k].isoformat()
    return JSONResponse(rows)


@app.get("/healthz")
def healthz():
    try:
        conn = store.connect(retries=1)
        conn.close()
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=503)
