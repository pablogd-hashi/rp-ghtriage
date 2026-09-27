"""Whether a triaged row is worth a tool loop, and what we store when it returns.

The worker publishes. This module decides and shapes the JSON. It does not
change the category column. A failed tool loop is a status, not a new label.
"""

from __future__ import annotations

from .contract import Category, LabelSource, TriageResult
from .reason import floor_disagreement


def investigate_enabled(value: str | None) -> bool:
    return (value or "0").strip() == "1"


def should_investigate(result: TriageResult) -> bool:
    """Security, a floor raise, or a note that still disagrees with the label."""
    if result.label_source is LabelSource.skipped:
        return False
    if result.floor_raised or result.category is Category.security:
        return True
    return floor_disagreement(
        result.category.value, result.risk_note, result.affected_area
    ) is not None


def investigation_from(outcome: dict) -> dict:
    """Keep the trace. Do not include a category when the loop failed."""
    if outcome.get("status") != "ok":
        return {
            "status": "failed",
            "reason": outcome.get("reason") or "tool loop failed",
            "trace": outcome.get("trace") or [],
        }
    return {
        "status": "ok",
        "category": outcome.get("category"),
        "tool_calls": outcome.get("tool_calls", 0),
        "blocked_downgrade": outcome.get("blocked_downgrade", False),
        "trace": outcome.get("trace") or [],
    }
