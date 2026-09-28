#!/usr/bin/env python3
"""Fail closed. Refuse writes to main, a pull request merge, and a volume wipe.

`main` is the demo. `gh pr create` must pass `--base sdd/factory`.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def current_branch() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    return (proc.stdout or "").strip()


def deny_reason(command: str) -> str | None:
    if re.search(r"\bgh\s+pr\s+merge\b", command):
        return "gh pr merge is refused. A person merges into sdd/factory. The base is never main."
    if re.search(r"\bgh\s+pr\s+create\b", command):
        if re.search(r"--base(?:=|\s+)main\b", command) or not re.search(
            r"--base(?:=|\s+)sdd/factory\b", command
        ):
            return "gh pr create must use --base sdd/factory. A pull request against main is refused."
    if re.search(r"\bdocker(?:-|\s+)compose\s+down\b", command) and re.search(
        r"(?:^|\s)(-v|--volumes)(?:\s|$)", command
    ):
        return "docker compose down -v is refused."

    if re.search(r"\bgit\s+push\b", command) and (
        re.search(r":main(?:\s|$)", command)
        or re.search(r"(?:^|[\s=])main(?:\s|$)", command)
    ):
        return "A push that names main is refused. main is the demo."
    if re.search(r"\bgit\s+checkout\s+main\b", command) or re.search(
        r"\bgit\s+switch\s+main\b", command
    ):
        return "Checking out main is refused."
    if re.search(r"\bgit\s+checkout\s+(?:-B|-b)\s+main\b", command):
        return "Checking out main is refused."
    if re.search(r"\bgit\s+(update-ref|branch)\b", command) and re.search(
        r"refs/heads/main|(?:^|\s)main(?:\s|$)", command
    ):
        if re.search(r"(-f|-M|--force|update-ref)", command):
            return "Rewriting main is refused."
    if current_branch() == "main" and re.search(
        r"\bgit\s+(merge|rebase|reset|commit|pull)\b", command
    ):
        return "Writing to main is refused. main is the demo."
    return None


def main() -> int:
    raw = sys.stdin.read() or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {}
    command = data.get("command") or ""
    reason = deny_reason(command)
    if reason:
        json.dump(
            {"permission": "deny", "user_message": reason, "agent_message": reason},
            sys.stdout,
        )
        return 0
    json.dump({"permission": "allow"}, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
