"""One tool loop. The model may call a tool or stop. It does not choose the policy.

A tool failure returns status=failed and no category. The caller keeps the
workflow row.
"""

from __future__ import annotations

import json
import time

from .contract import MODEL_CATEGORIES
from .llm import LLMError
from .parse import extract_first_json_object, strip_fences
from .policy import TIMEOUT_S, PolicyError, allow, cannot_downgrade
from .tools import TOOL_SPECS, ToolError, dispatch

AGENT_SYSTEM = """\
You investigate one pull request that is already flagged.
Call a tool or stop. Tools are read-only.
When you stop, answer with ONLY this JSON:
{"category": "<security|feature|refactor|docs|dependency-bump>", "rationale": "<one sentence>"}
Do not answer unclear. You cannot lower a security label; that is enforced outside this prompt.
"""


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _failed(trace: list, reason: str, started: float) -> dict:
    return {
        "status": "failed",
        "reason": reason,
        "category": None,
        "blocked_downgrade": False,
        "trace": trace,
        "tool_calls": sum(1 for step in trace if step.get("kind") == "tool" and "error" not in step),
        "latency_ms": _elapsed_ms(started),
    }


def _category_from(text: str) -> str | None:
    blob = extract_first_json_object(strip_fences(text))
    if blob is None:
        return None
    try:
        data = json.loads(blob)
    except ValueError:
        return None
    category = str(data.get("category", "")).strip().lower()
    if category not in MODEL_CATEGORIES:
        return None
    return category


def run_agent(
    record: dict,
    client,
    *,
    current_category: str | None = None,
    catalog: dict | None = None,
    timeout_s: float = TIMEOUT_S,
) -> dict:
    started = time.monotonic()
    trace: list[dict] = []
    tool_calls = 0
    user = json.dumps({
        "title": record.get("title") or "",
        "current_category": current_category,
        "files": [f.get("filename") for f in (record.get("files") or [])],
    })

    while True:
        if time.monotonic() - started > timeout_s:
            return _failed(trace, "timeout", started)
        try:
            step = client.complete_with_tools(AGENT_SYSTEM, user, TOOL_SPECS)
        except LLMError as exc:
            return _failed(trace, str(exc), started)

        if step.get("type") == "tool":
            name = step.get("name") or ""
            payload = step.get("input") or {}
            try:
                allow(name, tool_calls)
                output = dispatch(name, record, payload, catalog)
            except (PolicyError, ToolError) as exc:
                trace.append({"kind": "tool", "name": name, "input": payload, "error": str(exc)})
                return _failed(trace, str(exc), started)
            tool_calls += 1
            trace.append({"kind": "tool", "name": name, "input": payload, "output": output})
            user = json.dumps({"tool": name, "output": output})
            continue

        category = _category_from(step.get("text") or "")
        if category is None:
            return _failed(trace, "unreadable final answer", started)
        blocked = False
        if current_category:
            kept = cannot_downgrade(current_category, category)
            if kept != category:
                blocked = True
                category = kept
                trace.append({"kind": "policy", "action": "blocked_downgrade"})
        return {
            "status": "ok",
            "reason": "",
            "category": category,
            "blocked_downgrade": blocked,
            "trace": trace,
            "tool_calls": tool_calls,
            "latency_ms": _elapsed_ms(started),
        }
