"""One page of GitHub public events, then the same enrichment Connect does.

No classification. The button in the Streamlit entry point calls this, then
hands each record to triage().
"""

from __future__ import annotations

import requests

API = "https://api.github.com"
MAX_PRS = 3


def auth_headers(token: str | None) -> dict:
    headers = {
        "User-Agent": "pr-triage-pipeline",
        "Accept": "application/vnd.github+json",
    }
    token = (token or "").strip()
    if token:
        headers["Authorization"] = f"token {token}"
    return headers


def is_bot(login: str) -> bool:
    login = (login or "").lower()
    return (
        login.endswith("[bot]")
        or "dependabot" in login
        or "renovate" in login
        or login == "github-actions"
    )


def _payload(event: dict) -> dict:
    payload = event.get("payload")
    return payload if isinstance(payload, dict) else {}


def _actor(event: dict) -> str:
    actor = event.get("actor")
    if isinstance(actor, dict):
        return actor.get("login") or ""
    return ""


def _repo(event: dict) -> str:
    repo = event.get("repo")
    if isinstance(repo, dict):
        return repo.get("name") or ""
    return ""


def pr_card(event: dict) -> dict:
    """The little we know about a pull request before enrichment."""
    payload = _payload(event)
    stub = payload.get("pull_request") if isinstance(payload.get("pull_request"), dict) else {}
    return {
        "repo": _repo(event),
        "number": payload.get("number") or stub.get("number") or 0,
        "author": _actor(event),
        "action": payload.get("action") or "",
        "url": stub.get("html_url") or "",
    }


def account_events(events: list) -> tuple[dict, list]:
    """Count the firehose. Pull requests that do not survive are listed.

    Returns (summary, kept events). `kept` is opened, non-bot pull requests,
    in the order GitHub sent them.
    """
    by_type: dict[str, int] = {}
    dropped: list[dict] = []
    kept: list = []
    pull_requests = 0
    for event in events:
        if not isinstance(event, dict):
            by_type["malformed"] = by_type.get("malformed", 0) + 1
            continue
        kind = event.get("type") or "unknown"
        by_type[kind] = by_type.get(kind, 0) + 1
        if kind != "PullRequestEvent":
            continue
        pull_requests += 1
        card = pr_card(event)
        if card["action"] != "opened":
            card["reason"] = "not opened"
            dropped.append(card)
            continue
        if is_bot(card["author"]):
            card["reason"] = "bot"
            dropped.append(card)
            continue
        kept.append(event)
    summary = {
        "events": len(events),
        "by_type": by_type,
        "pull_requests": pull_requests,
        "not_pull_requests": len(events) - pull_requests,
        "dropped": dropped,
        "dropped_not_opened": sum(1 for card in dropped if card["reason"] == "not opened"),
        "dropped_bots": sum(1 for card in dropped if card["reason"] == "bot"),
        "kept": len(kept),
        "held": [],
    }
    return summary, kept


def opened_pull_requests(events: list) -> list:
    kept = []
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("type") != "PullRequestEvent":
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if payload.get("action") != "opened":
            continue
        actor = event.get("actor") if isinstance(event.get("actor"), dict) else {}
        if is_bot(actor.get("login") or ""):
            continue
        kept.append(event)
    return kept


def project_record(event: dict, pr: dict | None, changed_files: list | None) -> dict:
    """Same record shape as the mapping at the end of connect/ingest.yaml."""
    pr = pr if isinstance(pr, dict) else {}
    raw_files = changed_files if isinstance(changed_files, list) else []
    files = []
    for item in raw_files[:8]:
        if not isinstance(item, dict):
            continue
        patch = item.get("patch") or ""
        if not isinstance(patch, str):
            patch = str(patch)
        files.append({
            "filename": item.get("filename") or "",
            "status": item.get("status") or "",
            "additions": item.get("additions") or 0,
            "deletions": item.get("deletions") or 0,
            "patch": patch[:1500],
        })
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    stub = payload.get("pull_request") if isinstance(payload.get("pull_request"), dict) else {}
    actor = event.get("actor") if isinstance(event.get("actor"), dict) else {}
    user = pr.get("user") if isinstance(pr.get("user"), dict) else {}
    repo = event.get("repo") if isinstance(event.get("repo"), dict) else {}
    body = pr.get("body") or ""
    if not isinstance(body, str):
        body = str(body)
    changed = pr.get("changed_files")
    return {
        "event_id": event.get("id") or "",
        "pr_url": pr.get("url") or stub.get("url") or "",
        "html_url": pr.get("html_url") or "",
        "repo": repo.get("name") or "",
        "pr_number": pr.get("number") or payload.get("number") or 0,
        "author": user.get("login") or actor.get("login") or "",
        "draft": bool(pr.get("draft") or False),
        "event_created_at": event.get("created_at") or "",
        "title": pr.get("title") or "",
        "body": body[:2000],
        "additions": pr.get("additions") or 0,
        "deletions": pr.get("deletions") or 0,
        "files_changed": changed if changed is not None else len(files),
        "files": files,
    }


def _get_json(url: str, headers: dict):
    try:
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        return response.json(), ""
    except (requests.RequestException, ValueError) as exc:
        return None, str(exc)


def fetch_opened_prs(token: str | None = None, limit: int = MAX_PRS) -> dict:
    """Poll /events once and enrich up to `limit` opened pull requests.

    Returns steps, enriched records, and an account of what was dropped.
    """
    steps: list[dict] = []
    records: list[dict] = []
    headers = auth_headers(token)
    url = f"{API}/events?per_page=100"
    events, error = _get_json(url, headers)
    if error or not isinstance(events, list):
        steps.append({
            "step": "poll",
            "input": url,
            "output": error or "poll returned something other than a list",
        })
        summary, _kept = account_events([])
        return {"steps": steps, "records": records, "account": summary, "error": error or "bad poll"}

    summary, kept = account_events(events)
    dropped = summary["dropped_not_opened"] + summary["dropped_bots"]
    steps.append({
        "step": "poll",
        "input": url,
        "output": (
            f"{summary['events']} events, {summary['not_pull_requests']} not pull requests, "
            f"{dropped} pull requests dropped, {summary['kept']} opened and kept"
        ),
    })

    seen: set = set()
    taken = 0
    for event in kept:
        if taken >= limit:
            break
        event_id = event.get("id")
        if event_id in seen:
            continue
        seen.add(event_id)
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        stub = payload.get("pull_request") if isinstance(payload.get("pull_request"), dict) else {}
        pr_url = stub.get("url") or ""
        if not pr_url:
            steps.append({"step": "enrich", "input": str(event_id), "output": "no pull request url"})
            continue
        pr, pr_err = _get_json(pr_url, headers)
        changed, files_err = _get_json(pr_url + "/files?per_page=30", headers)
        record = project_record(
            event,
            pr if isinstance(pr, dict) else {},
            changed if isinstance(changed, list) else [],
        )
        note = f"title={record['title']!r} files={len(record['files'])}"
        problems = " ".join(part for part in (pr_err, files_err) if part)
        if problems:
            note = f"{note} ({problems})"
        steps.append({"step": "enrich", "input": pr_url, "output": note})
        records.append(record)
        taken += 1

    summary["held"] = [pr_card(event) for event in kept[limit:]]
    if summary["held"]:
        steps.append({
            "step": "cap",
            "input": f"{len(kept)} opened pull requests",
            "output": f"judging the first {limit}, {len(summary['held'])} left for the next click",
        })
    return {"steps": steps, "records": records, "account": summary, "error": ""}
