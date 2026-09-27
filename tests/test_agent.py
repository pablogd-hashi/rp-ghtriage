"""The tool loop, the allowlist, and the rule that security cannot be lowered."""

from __future__ import annotations

import json

import pytest

from triage.agent import run_agent
from triage.llm import ScriptedToolLLM
from triage.policy import PolicyError, allow, cannot_downgrade
from triage.tools import ToolError, list_changed_files, osv_lookup, read_file

PATCH = "@@ -1 +1 @@\n-old\n+new\n"


def record() -> dict:
    return {
        "title": "bump deps",
        "files": [{"filename": "go.mod", "patch": PATCH}],
    }


def test_read_file_returns_the_patch_and_refuses_unknown_paths():
    assert read_file(record(), "go.mod") == PATCH
    with pytest.raises(ToolError):
        read_file(record(), "missing.go")


def test_list_changed_files_and_osv_catalog():
    assert list_changed_files(record()) == ["go.mod"]
    catalog = {"osv": {"left-pad@1.0.0": {"vulns": [{"id": "TEST-1"}]}}}
    assert osv_lookup(record(), "left-pad", "1.0.0", catalog)["vulns"][0]["id"] == "TEST-1"
    assert osv_lookup(record(), "golang.org/x/crypto", "0.17.0", catalog)["vulns"] == []


def test_allowlist_and_budget():
    allow("read_file", 2)
    with pytest.raises(PolicyError):
        allow("delete_repo", 0)
    with pytest.raises(PolicyError):
        allow("read_file", 3)


def test_cannot_downgrade_security():
    assert cannot_downgrade("security", "docs") == "security"
    assert cannot_downgrade("refactor", "security") == "security"
    assert cannot_downgrade("docs", "docs") == "docs"


def test_agent_reads_a_file_then_stops():
    final = json.dumps({"category": "security", "rationale": "the patch disables expiry"})
    client = ScriptedToolLLM([
        {"type": "tool", "name": "read_file", "input": {"path": "go.mod"}},
        final,
    ])
    result = run_agent(record(), client, current_category="dependency-bump")
    assert result["status"] == "ok"
    assert result["category"] == "security"
    assert result["tool_calls"] == 1
    assert result["trace"][0]["name"] == "read_file"
    assert "network" not in json.dumps(result)


def test_tool_failure_keeps_no_new_label():
    client = ScriptedToolLLM([
        {"type": "tool", "name": "read_file", "input": {"path": "nope.go"}},
    ])
    result = run_agent(record(), client, current_category="refactor")
    assert result["status"] == "failed"
    assert result["category"] is None


def test_fourth_tool_call_is_refused():
    client = ScriptedToolLLM([
        {"type": "tool", "name": "list_changed_files", "input": {}},
        {"type": "tool", "name": "list_changed_files", "input": {}},
        {"type": "tool", "name": "list_changed_files", "input": {}},
        {"type": "tool", "name": "list_changed_files", "input": {}},
    ])
    result = run_agent(record(), client, current_category="docs")
    assert result["status"] == "failed"
    assert result["tool_calls"] == 3


def test_agent_cannot_lower_security():
    final = json.dumps({"category": "docs", "rationale": "just a comment"})
    client = ScriptedToolLLM([final])
    result = run_agent(record(), client, current_category="security")
    assert result["status"] == "ok"
    assert result["category"] == "security"
    assert result["blocked_downgrade"] is True
