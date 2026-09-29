"""Entry point. The button fetches GitHub, then the page shows the drops,
what each agent did, and the action stored at the end.
"""

from __future__ import annotations

import html
import json
import os
from pathlib import Path

import requests
import streamlit as st

from triage.github import MAX_PRS, fetch_opened_prs
from triage.llm import LLMError, get_client
from triage.parse import extract_first_json_object, repair, strip_fences
from triage.reason import triage

ROOT = Path(__file__).resolve().parents[1]

AGENTS = {
    "guard": "Guard",
    "classify": "Classifier",
    "gate": "Gate",
    "retry": "Retry",
    "details": "Details",
    "model": "Model",
}

TONE = {
    "security": "#ff5a4f",
    "feature": "#7eb6ff",
    "refactor": "#d6c07a",
    "docs": "#7dcea0",
    "dependency-bump": "#e0a45a",
    "unclear": "#b7b1a6",
    "skipped": "#8b939e",
    "muted": "#b7b1a6",
}


def load_dotenv() -> None:
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def point_ollama_at_localhost() -> None:
    """Compose names the model host `ollama`. On the laptop that name does not resolve."""
    if Path("/.dockerenv").exists():
        return
    host = os.environ.get("OLLAMA_HOST", "")
    if "://ollama:" in host:
        os.environ["OLLAMA_HOST"] = host.replace("://ollama:", "://127.0.0.1:", 1)


def use_installed_model() -> str:
    """Use a chat model this Ollama actually has.

    The page defaults to qwen2.5:3b, which Docker pulls and a laptop often does not.
    Returns a sentence when it had to substitute, else "".
    """
    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    if "OLLAMA_MODEL_REQUESTED" not in os.environ:
        os.environ["OLLAMA_MODEL_REQUESTED"] = (
            os.environ.get("OLLAMA_MODEL", "qwen2.5:3b").strip() or "qwen2.5:3b"
        )
    wanted = os.environ["OLLAMA_MODEL_REQUESTED"]
    try:
        response = requests.get(f"{host}/api/tags", timeout=2)
        response.raise_for_status()
        models = response.json().get("models") or []
    except (requests.RequestException, ValueError):
        return ""
    names = []
    chat = []
    for item in models:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or ""
        if not name:
            continue
        names.append(name)
        if item.get("capabilities") == ["embedding"]:
            continue
        chat.append(name)
    if wanted in names:
        os.environ["OLLAMA_MODEL"] = wanted
        return ""
    for name in names:
        if name.startswith(wanted + ":") or name.split(":")[0] == wanted:
            os.environ["OLLAMA_MODEL"] = name
            return ""
    if not chat:
        return f"{wanted} is not installed, and Ollama has no chat model."
    pick = next((name for name in chat if name.startswith("qwen")), chat[0])
    os.environ["OLLAMA_MODEL"] = pick
    return f"{wanted} is not installed. This run uses {pick}."


def model_problem(client) -> str:
    host = getattr(client, "host", None)
    if not host:
        return ""
    try:
        response = requests.get(f"{host}/api/tags", timeout=2)
        response.raise_for_status()
    except requests.RequestException as exc:
        return f"model unreachable ({exc})"
    return ""


def inject_css() -> None:
    st.markdown(
        """
        <style>
        .block-container { padding-top: 2.2rem; max-width: 1180px; }
        .tile .num { font-size: 4.4rem; font-weight: 720; letter-spacing: -0.045em; line-height: 0.9; }
        .tile .label { margin-top: 0.55rem; font-size: 0.74rem; letter-spacing: 0.16em; text-transform: uppercase; color: #c8c2b6; }
        .tile .note { margin-top: 0.35rem; color: #9a9488; min-height: 2.4rem; }
        .tile.drop .num { color: #ff5a4f; }
        .tile.keep .num { color: #3dd68c; }
        .story { font-size: 1.35rem; line-height: 1.45; margin: 0.4rem 0 1rem; }
        .stack { display: flex; width: 100%; height: 18px; border-radius: 999px; overflow: hidden; background: #1c2128; margin: 0.2rem 0 1.4rem; }
        .stack i { display: block; height: 100%; }
        .legend { color: #9a9488; font-size: 0.85rem; margin-top: -1rem; margin-bottom: 1.4rem; }
        .legend b { color: #f3efe6; font-weight: 600; }
        .typerow { display: grid; grid-template-columns: 11rem 1fr 2.2rem; gap: 0.7rem; align-items: center; margin: 0.28rem 0; }
        .typelabel { color: #c8c2b6; }
        .typebar { display: block; height: 8px; background: #ff5a4f; border-radius: 999px; opacity: 0.85; }
        .typecount { text-align: right; color: #f3efe6; }
        .ledger { width: 100%; border-collapse: collapse; margin-bottom: 0.6rem; }
        .ledger td { padding: 0.55rem 0.2rem; border-bottom: 1px solid rgba(243,239,230,0.08); vertical-align: baseline; }
        .dropwhy { color: #ff5a4f; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; font-size: 0.82rem; width: 8rem; }
        .who { font-size: 1.05rem; }
        .by { color: #9a9488; text-align: right; }
        .rail { display: flex; flex-wrap: wrap; gap: 0.45rem; align-items: center; margin: 0.3rem 0 0.8rem; }
        .pip { border: 1px solid rgba(243,239,230,0.16); border-radius: 999px; padding: 0.28rem 0.7rem; color: #6f6a62; letter-spacing: 0.08em; font-size: 0.72rem; text-transform: uppercase; }
        .pip.on { color: #f3efe6; border-color: rgba(243,239,230,0.45); }
        .pip.action { color: #ff5a4f; border-color: rgba(255,90,79,0.7); }
        .path { max-width: 680px; margin: 0.2rem 0 0.4rem; }
        .step { display: grid; grid-template-columns: 1.4rem 1fr; gap: 0.45rem 0.7rem; }
        .stepno { color: #9a9488; padding-top: 0.1rem; }
        .steptitle { font-size: 1.05rem; font-weight: 680; }
        .job { color: #c8c2b6; margin: 0.12rem 0 0.35rem; overflow-wrap: anywhere; }
        .branch { border-left: 3px solid #3a414c; margin: 0.18rem 0; padding: 0.22rem 0.6rem; color: #6f6a62; overflow-wrap: anywhere; }
        .branch.took { border-left-color: #3dd68c; color: #f3efe6; background: rgba(61, 214, 140, 0.07); }
        .thought { margin-top: 0.35rem; overflow-wrap: anywhere; }
        .varrow { color: #6f6a62; padding: 0.15rem 0 0.15rem 0.15rem; line-height: 1; }
        .verdict { border: 1px solid rgba(243,239,230,0.1); border-left: 8px solid var(--tone); background: #12161d; padding: 1.15rem 1.3rem 1.2rem; margin: 0.8rem 0 1.6rem; max-width: 100%; }
        .verdict .kicker { letter-spacing: 0.22em; font-size: 0.72rem; color: #9a9488; }
        .verdict .word { font-size: 3rem; font-weight: 740; letter-spacing: 0.03em; line-height: 1.05; margin: 0.2rem 0 0.45rem; color: var(--tone); }
        .verdict .because { color: #f3efe6; font-size: 1.02rem; font-weight: 400; line-height: 1.45; overflow-wrap: anywhere; }
        .verdict .meta { color: #9a9488; margin-bottom: 0.35rem; }
        @media (max-width: 800px) { .io { grid-template-columns: 1fr; } }
        .prhead { margin-bottom: 0.2rem; }
        .prhead .repo { font-size: 1.7rem; font-weight: 700; }
        .prhead .title { font-size: 1.15rem; color: #f3efe6; }
        .prhead .meta { color: #9a9488; }
        .section { margin-top: 1.6rem; font-size: 0.78rem; letter-spacing: 0.18em; text-transform: uppercase; color: #9a9488; }
        div.stButton > button { border-radius: 999px; padding: 0.7rem 1.5rem; font-size: 1.05rem; font-weight: 650; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def show(body: str) -> None:
    st.markdown(body, unsafe_allow_html=True)


def esc(value) -> str:
    return html.escape(str(value if value is not None else ""))


def parsed_model(text: str) -> dict | None:
    blob = extract_first_json_object(strip_fences(text or ""))
    if not blob:
        return None
    try:
        data = json.loads(repair(blob))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def one_sentence(text: str, limit: int = 160) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return (cut or text[:limit]) + "…"


def gate_facts(step: dict) -> tuple[str | None, str]:
    text = step.get("input") or ""
    threshold = "0.65"
    found = text.split("threshold=")
    if len(found) > 1:
        threshold = found[1].split()[0]
    if "score=None" in text:
        return None, threshold
    score = None
    for part in text.replace("retry ", "").split():
        if part.startswith("score="):
            score = part.split("=", 1)[1]
    return score, threshold


def model_bits(step: dict) -> tuple[dict | None, str, str]:
    data = parsed_model(step.get("output") or "")
    if not data:
        return None, "", ""
    confidence = data.get("confidence") if isinstance(data.get("confidence"), dict) else {}
    category = str(data.get("category") or "")
    score = confidence.get("score", "")
    thought = one_sentence(str(confidence.get("rationale") or ""))
    return data, f"{category} at {score}".strip(), thought


def explain(step: dict) -> tuple[str, str, list[tuple[str, str]]]:
    """Job sentence, the model's thought, and if/then lines. 'took' is the branch used."""
    name = step.get("step") or ""
    out = (step.get("output") or "").strip()
    if name == "guard":
        job = "Runs before any model call. Drafts and empty diffs are not worth one."
        if out == "proceed":
            return job, "", [
                ("dim", "if draft, no files, or nothing to read → skip"),
                ("took", "else → ask the model"),
            ]
        return job, "", [
            ("took", f"if {out} → skip"),
            ("dim", "else → ask the model"),
        ]
    if name == "classify":
        job = "The model reads the title and the diff, then picks one label."
        _data, result, thought = model_bits(step)
        if not result:
            return job, "", [("took", "the answer did not parse → the gate will ask again")]
        return job, thought, [("took", result)]
    if name == "gate":
        job = "A label is stored only when the score clears 0.65."
        score, threshold = gate_facts(step)
        shown = score if score is not None else "no score"
        if out == "keep":
            return job, "", [
                ("dim", f"if missing or below {threshold} → ask again"),
                ("took", f"{shown} ≥ {threshold} → keep this label"),
            ]
        if out == "fallback":
            return job, "", [
                ("took", f"second score {shown} is still below {threshold} → store unclear"),
                ("dim", f"if the second score ≥ {threshold} → keep it"),
            ]
        if score is None:
            took = "no score → ask again"
        else:
            took = f"{shown} < {threshold} → ask again"
        return job, "", [
            ("took", took),
            ("dim", f"if the score ≥ {threshold} → keep it"),
        ]
    if name == "retry":
        job = "Same diff, stricter prompt. This is the second and last try."
        _data, result, thought = model_bits(step)
        if not result:
            return job, "", [("took", "the second answer did not parse → store unclear")]
        return job, thought, [("took", result)]
    if name == "details":
        job = "The label is already chosen. This call only adds the area and one risk."
        data = parsed_model(out)
        if not data:
            return job, "", [("took", "no note came back → the label still stands")]
        area = str(data.get("affected_area") or "").strip()
        thought = one_sentence(str(data.get("risk_note") or ""))
        line = f"area: {area}" if area else "area not named"
        return job, thought, [("took", line)]
    return "The model was not asked.", "", [("took", one_sentence(out, 120) or "no model")]


def short_outcome(step: dict) -> str:
    name = step.get("step") or ""
    out = (step.get("output") or "").strip()
    if name == "guard":
        return "proceed" if out == "proceed" else out
    if name == "gate":
        return out or "gate"
    if name in {"classify", "retry"}:
        data = parsed_model(out)
        if not data:
            return "unparsed"
        confidence = data.get("confidence") if isinstance(data.get("confidence"), dict) else {}
        return f"{data.get('category', '')} {confidence.get('score', '')}".strip()
    if name == "details":
        data = parsed_model(out)
        if not data:
            return "no note" if not out.startswith("details call failed") else "failed"
        return str(data.get("affected_area") or "note")
    return out[:48]


def action_of(result) -> tuple[str, str, str, str]:
    if result is None:
        return "NOT JUDGED", "No label was stored.", "muted", ""
    source = result.label_source.value
    meta = f"{source} · {result.llm_calls} model calls"
    if source == "skipped":
        return "SKIPPED", result.rationale, "skipped", meta
    if source == "fallback":
        return "UNCLEAR", result.rationale, "unclear", meta
    meta = f"confidence {result.confidence} · {meta}"
    return result.category.value.upper(), result.rationale, result.category.value, meta


def verdict(word: str, why: str, tone: str, meta: str = "") -> None:
    color = TONE.get(tone, TONE["muted"])
    meta_html = f'<div class="meta">{esc(meta)}</div>' if meta else ""
    show(
        f'<div class="verdict" style="--tone:{color}">'
        f'<div class="kicker">Action</div>'
        f'<div class="word">{esc(word)}</div>'
        f"{meta_html}"
        f'<div class="because">{esc(why)}</div>'
        f"</div>"
    )


def dropped_sentence(account: dict) -> str:
    opened = account["dropped_not_opened"]
    bots = account["dropped_bots"]
    dropped = opened + bots
    if dropped == 0:
        return ""
    if dropped == 1 and opened == 1:
        return "1 pull request was dropped: it was not newly opened."
    if dropped == 1 and bots == 1:
        return "1 pull request was dropped: it came from a bot."
    bits = []
    if opened == 1:
        bits.append("1 was not newly opened")
    elif opened:
        bits.append(f"{opened} were not newly opened")
    if bots == 1:
        bits.append("1 came from a bot")
    elif bots:
        bits.append(f"{bots} came from bots")
    return f"{dropped} pull requests were dropped: {', '.join(bits)}."


def story(account: dict, judged: int) -> str:
    not_prs = account["not_pull_requests"]
    sentences = [f"{account['events']} events came off the firehose."]
    if not_prs == 0:
        sentences.append("All of them were pull requests.")
    elif not_prs == 1:
        sentences.append("1 was not a pull request.")
    else:
        sentences.append(f"{not_prs} were not pull requests.")
    dropped = dropped_sentence(account)
    if dropped:
        sentences.append(dropped)
    elif account["pull_requests"]:
        sentences.append("Every pull request on this page stayed.")
    if judged == 1:
        sentences.append("1 reached the agents.")
    elif judged:
        sentences.append(f"{judged} reached the agents.")
    else:
        sentences.append("No agent ran.")
    held = account.get("held") or []
    if len(held) == 1:
        sentences.append("1 more opened pull request waits for the next click.")
    elif held:
        sentences.append(f"{len(held)} more opened pull requests wait for the next click.")
    return " ".join(sentences)


def scoreboard(account: dict, judged: int) -> None:
    dropped = account["dropped_not_opened"] + account["dropped_bots"]
    note = []
    if account["dropped_not_opened"]:
        note.append(f"{account['dropped_not_opened']} not newly opened")
    if account["dropped_bots"]:
        note.append(f"{account['dropped_bots']} bots")
    tiles = [
        ("", account["events"], "Events", "one page of the public firehose"),
        ("", account["not_pull_requests"], "Not pull requests", "pushes, stars, reviews, the rest"),
        ("drop", dropped, "Pull requests dropped", " · ".join(note) or "none on this page"),
        ("keep", judged, "Reached the agents", f"first {MAX_PRS} opened pull requests"),
    ]
    columns = st.columns(4)
    for column, (tone, number, label, caption) in zip(columns, tiles):
        column.markdown(
            f'<div class="tile {tone}"><div class="num">{number}</div>'
            f'<div class="label">{esc(label)}</div><div class="note">{esc(caption)}</div></div>',
            unsafe_allow_html=True,
        )
    total = max(account["events"], 1)
    held = len(account.get("held") or [])
    parts = [
        (account["not_pull_requests"], "#3a414c"),
        (dropped, "#ff5a4f"),
        (held, "#d6c07a"),
        (judged, "#3dd68c"),
    ]
    spans = "".join(
        f'<i style="width:{100 * count / total}%;background:{color}"></i>'
        for count, color in parts
        if count
    )
    show(f'<div class="stack">{spans}</div>')
    show(
        '<div class="legend">'
        '<b style="color:#9aa3b2">■</b> not a pull request '
        '&nbsp;&nbsp;<b style="color:#ff5a4f">■</b> pull request dropped '
        '&nbsp;&nbsp;<b style="color:#d6c07a">■</b> waiting '
        '&nbsp;&nbsp;<b style="color:#3dd68c">■</b> judged'
        "</div>"
    )


def type_chart(by_type: dict) -> None:
    if not by_type:
        return
    show('<div class="section">What the page contained</div>')
    peak = max(by_type.values())
    rows = []
    for name, count in sorted(by_type.items(), key=lambda item: item[1], reverse=True):
        label = name.removesuffix("Event").lower() if isinstance(name, str) else str(name)
        width = max(4, int(100 * count / peak))
        rows.append(
            f'<div class="typerow"><span class="typelabel">{esc(label)}</span>'
            f'<span><i class="typebar" style="width:{width}%"></i></span>'
            f'<span class="typecount">{count}</span></div>'
        )
    show("".join(rows))


def ledger(account: dict) -> None:
    dropped = account["dropped"]
    show(f'<div class="section">Dropped pull requests · {len(dropped)}</div>')
    if not dropped:
        if account["pull_requests"]:
            st.write("Every pull request on this page was opened by a person, so none were dropped.")
        else:
            st.write("This page of the firehose contained no pull requests to drop.")
        return
    rows = []
    for card in dropped:
        why = "bot" if card["reason"] == "bot" else (card["action"] or "not opened")
        who = f"{card['repo']} #{card['number']}"
        rows.append(
            "<tr>"
            f'<td class="dropwhy">{esc(why)}</td>'
            f'<td class="who">{esc(who)}</td>'
            f'<td class="by">{esc(card["author"])}</td>'
            "</tr>"
        )
    show(f'<table class="ledger">{"".join(rows)}</table>')
    held = account.get("held") or []
    if held:
        waiting = ", ".join(f"{card['repo']} #{card['number']}" for card in held)
        st.caption(f"Waiting for a later click: {waiting}")


def decision_path(trace: list[dict]) -> None:
    blocks = []
    for index, step in enumerate(trace, start=1):
        if index > 1:
            blocks.append('<div class="varrow">↓</div>')
        job, thought, branches = explain(step)
        title = AGENTS.get(step["step"], step["step"])
        branch_html = "".join(
            f'<div class="branch {state}">{esc(line)}</div>' for state, line in branches
        )
        thought_html = f'<div class="thought">{esc(thought)}</div>' if thought else ""
        blocks.append(
            '<div class="step">'
            f'<div class="stepno">{index}</div>'
            '<div class="stepbody">'
            f'<div class="steptitle">{esc(title)}</div>'
            f'<div class="job">{esc(job)}</div>'
            f"{branch_html}{thought_html}"
            "</div></div>"
        )
    show(f'<div class="path">{"".join(blocks)}</div>')


def judgement(_index: int, item: dict) -> None:
    record = item["record"]
    result = item["result"]
    repo = f"{record.get('repo') or 'unknown'} #{record.get('pr_number') or '?'}"
    title = record.get("title") or "untitled"
    meta = f"{record.get('author') or 'unknown'} · +{record.get('additions') or 0} −{record.get('deletions') or 0} · {len(record.get('files') or [])} files"
    show(
        '<div class="prhead">'
        f'<div class="repo">{esc(repo)}</div>'
        f'<div class="title">{esc(title)}</div>'
        f'<div class="meta">{esc(meta)}</div>'
        "</div>"
    )
    if record.get("html_url"):
        st.markdown(record["html_url"])
    if item["trace"]:
        decision_path(item["trace"])
    word, why, tone, meta = action_of(result)
    verdict(word, why, tone, meta)


def empty_stage() -> None:
    show('<div class="story">Fetch one page of GitHub events. Each judged pull request shows the branch it took, and why.</div>')
    columns = st.columns(4)
    stages = [
        ("01", "Firehose", "One hundred public events."),
        ("02", "Drops", "Not a pull request. Not newly opened. A bot."),
        ("03", "Agents", "Guard, Classifier, Gate, Details."),
        ("04", "Action", "The label that would be stored."),
    ]
    for column, (number, title, caption) in zip(columns, stages):
        column.markdown(
            f'<div class="tile"><div class="num" style="font-size:2rem">{number}</div>'
            f'<div class="label">{title}</div><div class="note">{caption}</div></div>',
            unsafe_allow_html=True,
        )


def render_run(run: dict) -> None:
    account = run["account"]
    judged = len(run["pull_requests"])
    show(f'<div class="story">{esc(story(account, judged))}</div>')
    if run.get("error"):
        st.error(run["error"])
    scoreboard(account, judged)
    type_chart(account.get("by_type") or {})
    ledger(account)
    show(f'<div class="section">Agents · {esc(run.get("model") or "")}</div>')
    if not run["pull_requests"]:
        dropped = account["dropped_not_opened"] + account["dropped_bots"]
        if dropped == 1:
            why = "1 pull request was dropped, and no opened pull request reached an agent."
        else:
            why = f"{dropped} pull requests were dropped, and no opened pull request reached an agent."
        verdict("NOTHING STORED", why, "muted")
        return
    for index, item in enumerate(run["pull_requests"]):
        judgement(index, item)


def run() -> None:
    load_dotenv()
    point_ollama_at_localhost()
    model_note = use_installed_model()
    st.set_page_config(page_title="PR Triage", layout="wide")
    inject_css()
    st.title("PR Triage")
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    st.caption("GitHub token is set." if token else "No GitHub token. Anonymous limit is 60 requests per hour.")
    if model_note:
        show(f'<div class="story">{esc(model_note)}</div>')

    clicked = st.button("Fetch from GitHub", type="primary")
    if clicked:
        with st.status("Reading the firehose…", expanded=True) as status:
            fetched = fetch_opened_prs(token or None, limit=MAX_PRS)
            account = fetched["account"]
            dropped = account["dropped_not_opened"] + account["dropped_bots"]
            drop_label = "1 pull request dropped" if dropped == 1 else f"{dropped} pull requests dropped"
            status.write(f"{account['events']} events. {drop_label}.")
            try:
                client = get_client()
                model = client.name
                problem = model_problem(client)
            except LLMError as exc:
                client = None
                model = str(exc)
                problem = model
            pull_requests = []
            for record in fetched["records"]:
                name = f"{record.get('repo')} #{record.get('pr_number')}"
                status.write(f"Enriching {name} — {record.get('title') or 'untitled'}")
                trace: list[dict] = []

                def watch(step: dict, _name: str = name) -> None:
                    title = AGENTS.get(step["step"], step["step"])
                    status.write(f"{_name} · {title} · {short_outcome(step)}")

                if client is None or problem:
                    result = None
                    trace.append({
                        "step": "model",
                        "input": record.get("pr_url") or "",
                        "output": problem or model,
                    })
                    watch(trace[-1])
                else:
                    result = triage(record, client, trace=trace, on_step=watch)
                word, _why, _tone, _meta = action_of(result)
                status.write(f"{name} · Action — {word}")
                pull_requests.append({"record": record, "trace": trace, "result": result})
            st.session_state["run"] = {
                "account": account,
                "pull_requests": pull_requests,
                "model": model,
                "error": fetched.get("error") or "",
            }
            actions = ", ".join(action_of(item["result"])[0] for item in pull_requests) or "nothing stored"
            status.update(
                label=f"{drop_label} · {actions}",
                state="complete",
                expanded=False,
            )

    run_state = st.session_state.get("run")
    if not run_state:
        empty_stage()
        return
    render_run(run_state)


run()
