"""Build the site diagrams as static SVG, in the panel deck's visual style.

Run: python docs/assets/diagrams/build.py
"""
from pathlib import Path
from html import escape

OUT = Path(__file__).parent
OUT.mkdir(parents=True, exist_ok=True)

PAPER, CARD, INK, INK2, INK3, RULE, HOT = "#f2ede2", "#f7f3ea", "#1b2130", "#4a5162", "#8b8f99", "#cfc6b3", "#b6422a"
HOT_SOFT = "#f6e7df"
SANS = "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Helvetica Neue', Arial, sans-serif"
MONO = "'JetBrains Mono', 'SF Mono', Menlo, Consolas, monospace"

STYLE = f"""<style>
  .nt {{ font: 600 16px {SANS}; fill: {INK}; }}
  .ns {{ font: 400 12.5px {SANS}; fill: {INK2}; }}
  .ann {{ font: 400 12px {MONO}; fill: {INK2}; }}
  .grp {{ font: 500 10.5px {MONO}; fill: {INK3}; letter-spacing: .12em; }}
  .foot {{ font: 400 12px {MONO}; fill: {INK2}; }}
  .hot .nt, .hot .ns, .ann.hot {{ fill: {HOT}; }}
  .muted .nt {{ fill: {INK2}; }}
  .wire {{ stroke: {INK}; stroke-width: 1.5; fill: none; }}
  .wire.hot {{ stroke: {HOT}; }}
  .dot {{ stroke: {INK3}; stroke-width: 1.2; stroke-dasharray: 2 4; stroke-linecap: round; fill: none; }}
  .rule {{ stroke: {RULE}; stroke-width: 1; }}
</style>"""


def svg(w, h, title, desc, body):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
        f'role="img" aria-labelledby="t d">\n<title id="t">{escape(title)}</title>\n<desc id="d">{escape(desc)}</desc>\n'
        f"{STYLE}\n"
        f'<defs>\n'
        f'  <marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9" orient="auto-start-reverse">'
        f'<path d="M1 1 L9 5 L1 9" fill="none" stroke="{INK}" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/></marker>\n'
        f'  <marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9" orient="auto-start-reverse">'
        f'<path d="M1 1 L9 5 L1 9" fill="none" stroke="{HOT}" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/></marker>\n'
        f'</defs>\n'
        f'<rect width="{w}" height="{h}" rx="10" fill="{PAPER}"/>\n{body}</svg>\n'
    )


def node(x, y, w, h, name, sub=None, kind=""):
    """kind: '' plain, 'hot' model call, 'muted' side path, 'fill' a key component."""
    stroke, fill, sw = INK, CARD, 1.5
    if kind == "hot":
        stroke, fill, sw = HOT, HOT_SOFT, 2
    elif kind == "muted":
        stroke = INK3
    elif kind == "fill":
        fill = "#e4dfd4"
    cx = x + w / 2
    out = [f'<g class="{kind}">',
           f'  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>']
    if sub:
        out.append(f'  <text class="nt" x="{cx}" y="{y + h / 2 - 3}" text-anchor="middle">{escape(name)}</text>')
        out.append(f'  <text class="ns" x="{cx}" y="{y + h / 2 + 16}" text-anchor="middle">{escape(sub)}</text>')
    else:
        out.append(f'  <text class="nt" x="{cx}" y="{y + h / 2 + 5.5}" text-anchor="middle">{escape(name)}</text>')
    out.append("</g>")
    return "\n".join(out) + "\n"


def wire(d, hot=False, both=False):
    m = "ah" if hot else "a"
    start = f' marker-start="url(#{m})"' if both else ""
    return f'<path class="wire{" hot" if hot else ""}" d="{d}" marker-end="url(#{m})"{start}/>\n'


def text(x, y, s, cls="ann", anchor="start"):
    return f'<text class="{cls}" x="{x}" y="{y}" text-anchor="{anchor}">{escape(s)}</text>\n'


def group(x1, x2, y, label):
    mid = (x1 + x2) / 2
    return (f'<path class="rule" d="M{x1} {y + 8} L{x1} {y + 3} L{x2} {y + 3} L{x2} {y + 8}" fill="none"/>\n'
            f'<rect x="{mid - len(label) * 4.4 - 8}" y="{y - 6}" width="{len(label) * 8.8 + 16}" height="16" fill="{PAPER}"/>\n'
            + text(mid, y + 7, label.upper(), "grp", "middle"))


# ---------------------------------------------------------------- system
def system():
    W, H = 1000, 384
    bw, bh, gap, x0, y1, y2 = 134, 68, 30, 23, 74, 208
    xs = [x0 + i * (bw + gap) for i in range(6)]
    cy = y1 + bh / 2
    b = ""
    b += group(xs[0], xs[0] + bw, 34, "GitHub")
    b += group(xs[1], xs[1] + bw, 34, "Redpanda Connect")
    b += group(xs[2], xs[2] + bw, 34, "Redpanda")
    b += group(xs[3], xs[3] + bw, 34, "Worker + model")
    b += group(xs[4], xs[5] + bw, 34, "Postgres + web")

    b += node(xs[0], y1, bw, bh, "GitHub", "public /events", "fill")
    b += node(xs[1], y1, bw, bh, "Connect", "filter · dedupe · fetch")
    b += node(xs[2], y1, bw, bh, "Redpanda", "topic pr.enriched")
    b += node(xs[3], y1, bw, bh, "Worker", "guard · gate · retry", "hot")
    b += node(xs[4], y1, bw, bh, "Postgres", "one row per PR")
    b += node(xs[5], y1, bw, bh, "Web page", "localhost:8000")
    for i in range(5):
        b += wire(f"M{xs[i] + bw} {cy} L{xs[i + 1] - 2} {cy}")

    b += node(xs[1], y2, bw, bh, "pr.dlq", "nothing was fetched", "muted")
    b += wire(f"M{xs[1] + bw / 2} {y1 + bh} L{xs[1] + bw / 2} {y2 - 2}")
    b += text(xs[1] + bw / 2 + 8, y1 + bh + 42, "no files")

    b += node(xs[3], y2, bw, bh, "Model", "Ollama, local", "hot")
    mx = xs[3] + bw / 2
    b += wire(f"M{mx} {y1 + bh + 2} L{mx} {y2 - 2}", hot=True, both=True)
    b += text(mx + 8, y1 + bh + 36, "2 calls,", "ann hot")
    b += text(mx + 8, y1 + bh + 52, "3 on a retry", "ann hot")

    b += node(xs[4], y2, bw, bh, "pr.triaged", "for other consumers", "muted")
    b += wire(f"M{xs[3] + bw - 22} {y1 + bh} L{xs[3] + bw - 22} {y1 + bh + 24} "
              f"L{xs[4] + bw / 2} {y1 + bh + 24} L{xs[4] + bw / 2} {y2 - 2}")

    b += node(xs[5], y2, bw, bh, "Prometheus", "lag and DLQ alerts", "muted")

    b += f'<line class="rule" x1="{x0}" y1="{H - 74}" x2="{W - x0}" y2="{H - 74}"/>\n'
    b += text(x0, H - 46, "220 events sampled → 18 kept: ~92% dropped before any fetch or model call", "foot")
    b += text(x0, H - 24, "red = the only part that calls a model", "foot")
    return svg(W, H, "PR Triage architecture",
               "GitHub public events go to Redpanda Connect, which filters, dedupes and fetches the code, "
               "then writes to the Redpanda topic pr.enriched, or to pr.dlq when nothing was fetched. "
               "The worker reads the topic, calls the local Ollama model two or three times, writes one Postgres "
               "row per pull request, and publishes pr.triaged. A web page reads Postgres. Prometheus alerts on lag and the DLQ.", b)


# ---------------------------------------------------------------- triage flow
def triage():
    W, H = 1000, 470
    h, y1, y2, y3 = 64, 70, 196, 322
    cy1, cy2, cy3 = y1 + h / 2, y2 + h / 2, y3 + h / 2
    G = (56, 128); C1 = (212, 132); P = (372, 96); GT = (496, 140); C3 = (680, 132); R = (840, 136)
    b = ""
    b += f'<circle cx="26" cy="{cy1}" r="7" fill="{INK}"/>\n'
    b += text(26, cy1 - 18, "PR", "grp", "middle")
    b += wire(f"M33 {cy1} L{G[0] - 2} {cy1}")
    b += node(G[0], y1, G[1], h, "Guard", "should_skip")
    b += wire(f"M{G[0] + G[1]} {cy1} L{C1[0] - 2} {cy1}")
    b += node(C1[0], y1, C1[1], h, "Call 1", "classify + score", "hot")
    b += wire(f"M{C1[0] + C1[1]} {cy1} L{P[0] - 2} {cy1}")
    b += node(P[0], y1, P[1], h, "Parse", "repair format")
    b += wire(f"M{P[0] + P[1]} {cy1} L{GT[0] - 2} {cy1}")
    b += node(GT[0], y1, GT[1], h, "Gate", "score ≥ 0.65?")
    b += wire(f"M{GT[0] + GT[1]} {cy1} L{C3[0] - 2} {cy1}")
    b += text((GT[0] + GT[1] + C3[0]) / 2, cy1 - 10, "yes", "ann", "middle")
    b += node(C3[0], y1, C3[1], h, "Call 2", "risk note", "hot")
    b += wire(f"M{C3[0] + C3[1]} {cy1} L{R[0] - 2} {cy1}")
    b += node(R[0], y1, R[1], h, "Row", "model · model_retry", "fill")

    # skip branch
    gx = G[0] + G[1] / 2
    b += wire(f"M{gx} {y1 + h} L{gx} {y2 - 2}")
    b += text(gx + 8, y1 + h + 34, "draft, no files")
    b += node(G[0], y2, G[1], h, "Row", "skipped · 0 calls", "muted")

    # retry branch
    tx = GT[0] + GT[1] / 2
    b += wire(f"M{tx} {y1 + h} L{tx} {y2 - 2}")
    b += text(tx + 8, y1 + h + 34, "no / unreadable")
    b += node(GT[0], y2, GT[1], h, "Retry", "stricter prompt", "hot")
    b += wire(f"M{tx} {y2 + h} L{tx} {y3 - 2}")
    b += node(GT[0], y3, GT[1], h, "Parse + gate", "score ≥ 0.65?")
    c3x = C3[0] + C3[1] / 2
    b += wire(f"M{GT[0] + GT[1]} {cy3} L{c3x} {cy3} L{c3x} {y1 + h + 2}")
    b += text(GT[0] + GT[1] + 12, cy3 - 10, "yes")
    b += wire(f"M{GT[0]} {cy3} L{C1[0] + 220 + 2} {cy3}")
    b += text(GT[0] - 12, cy3 - 10, "no", "ann", "end")
    b += node(C1[0], y3, 220, h, "Row", "fallback · unclear · 2 calls", "muted")

    b += f'<line class="rule" x1="26" y1="{H - 56}" x2="{W - 26}" y2="{H - 56}"/>\n'
    b += f'<rect x="26" y="{H - 36}" width="14" height="14" rx="3" fill="{HOT_SOFT}" stroke="{HOT}" stroke-width="1.5"/>\n'
    b += text(48, H - 24, "a model call", "foot")
    b += f'<rect x="170" y="{H - 36}" width="14" height="14" rx="3" fill="{CARD}" stroke="{INK}" stroke-width="1.5"/>\n'
    b += text(192, H - 24, "plain code, no model", "foot")
    b += text(W - 26, H - 24, "every path writes a row", "foot", "end")
    return svg(W, H, "Triage steps for one pull request",
               "The guard skips drafts and PRs with no files, with zero model calls. Otherwise call 1 classifies and scores. "
               "Parse repairs the format and the gate checks the score is at least 0.65. If yes, call 2 writes the risk note "
               "and the row is saved as model. If not, a stricter retry runs; if it passes, call 2 runs and the row is "
               "model_retry; if it fails, the row is unclear with label_source fallback.", b)


# ---------------------------------------------------------------- sdd pipeline
def sdd():
    W, H = 1000, 330
    w, h, y = 128, 64, 70
    xs = [24, 220, 416, 640, 848]
    names = [("01 spec", "what and why"), ("02 plan", "seam + files"), ("03 change", "the diff"),
             ("05 review", "reads 01–04"), ("06 pr", "base sdd/factory")]
    cy = y + h / 2
    b = ""
    b += group(xs[0], xs[4] + w, 34, "each phase writes one file · that file is the next phase's only input")
    for (n, s), x in zip(names, xs):
        b += node(x, y, w, h, n, s, "hot")
    for i in range(4):
        b += wire(f"M{xs[i] + w} {cy} L{xs[i + 1] - 2} {cy}")
    # checks below each gap
    checks = [(0, ["validate_request"]), (1, ["validate_request"]), (2, ["validate_request", "gate.py"])]
    yc = 176
    for i, labels in checks:
        mid = (xs[i] + w + xs[i + 1]) / 2
        b += f'<path class="dot" d="M{mid} {cy + 4} L{mid} {yc}"/>\n'
        b += f'<circle cx="{mid}" cy="{cy}" r="4" fill="{PAPER}" stroke="{INK}" stroke-width="1.5"/>\n'
        bw = 146 if len(labels) == 1 else 156
        bh = 32 if len(labels) == 1 else 50
        b += f'<rect x="{mid - bw / 2}" y="{yc}" width="{bw}" height="{bh}" rx="16" fill="{CARD}" stroke="{INK}" stroke-width="1.5"/>\n'
        for j, lab in enumerate(labels):
            b += text(mid, yc + 21 + j * 18, lab, "ann", "middle")
    b += text(xs[3] + w / 2 - 6, yc + 21, "pytest + evals", "ann", "start") if False else ""
    b += text(xs[2] + w + 112 - 30, yc + 72, "pytest + eval gate", "ann", "middle")
    b += f'<path class="dot" d="M{xs[4] + w / 2} {y + h + 4} L{xs[4] + w / 2} {yc}"/>\n'
    b += text(xs[4] + w / 2, yc + 21, "a person merges", "ann", "middle")

    b += f'<line class="rule" x1="24" y1="{H - 56}" x2="{W - 24}" y2="{H - 56}"/>\n'
    b += f'<rect x="24" y="{H - 36}" width="14" height="14" rx="3" fill="{HOT_SOFT}" stroke="{HOT}" stroke-width="1.5"/>\n'
    b += text(46, H - 24, "written by the agent", "foot")
    b += f'<rect x="230" y="{H - 36}" width="14" height="14" rx="7" fill="{CARD}" stroke="{INK}" stroke-width="1.5"/>\n'
    b += text(252, H - 24, "checked by code", "foot")
    b += text(W - 24, H - 24, "nothing merges · nothing goes to main", "foot", "end")
    return svg(W, H, "Spec-driven factory phases",
               "The agent writes 01 spec, 02 plan, 03 change, 05 review and 06 pr. After spec, plan and change, "
               "validate_request.py checks the folder, the seam and the diff. After the change, gate.py runs pytest and "
               "the eval gate. The pull request targets sdd/factory and a person merges.", b)


(OUT / "system.svg").write_text(system())
(OUT / "triage-flow.svg").write_text(triage())
(OUT / "sdd-phases.svg").write_text(sdd())
print("ok")
