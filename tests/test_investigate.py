"""Who gets a tool loop, and what a failed loop is allowed to write."""

from __future__ import annotations

from triage.contract import Category, LabelSource, TriageResult
from triage.investigate import investigation_from, investigate_enabled, should_investigate


def result(**over) -> TriageResult:
    base = dict(
        category=Category.docs,
        confidence=0.9,
        rationale="docs",
        label_source=LabelSource.model,
        floor_raised=False,
    )
    base.update(over)
    return TriageResult(**base)


def test_flag_defaults_off():
    assert investigate_enabled(None) is False
    assert investigate_enabled("0") is False
    assert investigate_enabled("1") is True


def test_security_and_floor_rows_are_sent():
    assert should_investigate(result(category=Category.security)) is True
    assert should_investigate(result(floor_raised=True, category=Category.security)) is True


def test_disagreement_is_sent_and_ordinary_rows_are_not():
    assert should_investigate(result(
        category=Category.refactor,
        affected_area="security",
        risk_note="unauthorized access",
    )) is True
    assert should_investigate(result()) is False
    assert should_investigate(result(
        category=Category.unclear,
        label_source=LabelSource.skipped,
        confidence=0,
    )) is False


def test_failed_tool_loop_does_not_carry_a_category():
    payload = investigation_from({
        "status": "failed",
        "reason": "no such file: missing.go",
        "category": "docs",
        "trace": [{"kind": "tool", "error": "no such file: missing.go"}],
    })
    assert payload["status"] == "failed"
    assert "category" not in payload
    assert payload["trace"][0]["error"].startswith("no such file")
