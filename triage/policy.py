"""What the investigator is allowed to do. One place, so the loop stays small."""

from __future__ import annotations

ALLOWLIST = frozenset({"read_file", "list_changed_files", "osv_lookup"})
MAX_TOOL_CALLS = 3
TIMEOUT_S = 10


class PolicyError(Exception):
    """The loop asked for something the envelope does not allow."""


def allow(name: str, calls_so_far: int) -> None:
    if name not in ALLOWLIST:
        raise PolicyError(f"{name} is not allowlisted")
    if calls_so_far >= MAX_TOOL_CALLS:
        raise PolicyError(f"tool budget is {MAX_TOOL_CALLS}")


def cannot_downgrade(current: str, proposed: str) -> str:
    """A security label stays security. The agent may still raise one."""
    if current == "security" and proposed != "security":
        return "security"
    return proposed
