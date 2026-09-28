#!/usr/bin/env python3
"""If triage/ or tests/ changed since gate.py, ask for another run.

`main` is the demo. The gate runs on a request branch. The pull request
base is `sdd/factory`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STAMP = ROOT / ".cursor" / "hooks" / "last-gate"
WATCH = ("triage/", "tests/")


def git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=ROOT, text=True, capture_output=True
    )
    return proc.stdout or ""


def changed() -> list[str]:
    seen: list[str] = []
    for blob in (
        git("diff", "--name-only", "HEAD"),
        git("diff", "--name-only", "--cached"),
        git("ls-files", "--others", "--exclude-standard"),
    ):
        for line in blob.splitlines():
            path = line.strip()
            if path.startswith(WATCH) and path not in seen:
                seen.append(path)
    return seen


def request_id() -> str:
    branch = git("rev-parse", "--abbrev-ref", "HEAD").strip()
    root = ROOT / "requests"
    if branch.startswith("sdd/factory-") and root.is_dir():
        key = branch[len("sdd/factory-") :]
        matches = sorted(root.glob(f"{key}-*"))
        if matches:
            return matches[0].name
    if root.is_dir():
        folders = [path for path in root.iterdir() if path.is_dir() and not path.name.startswith("_")]
        if folders:
            return max(folders, key=lambda path: path.stat().st_mtime).name
    return "<id>"


def main() -> int:
    sys.stdin.read()
    paths = changed()
    if not paths:
        json.dump({}, sys.stdout)
        return 0
    stamp = float(STAMP.read_text().strip()) if STAMP.exists() else 0.0
    newest = max((ROOT / path).stat().st_mtime for path in paths if (ROOT / path).exists())
    if stamp >= newest:
        json.dump({}, sys.stdout)
        return 0
    message = (
        "triage/ or tests/ changed and scripts/gate.py has not run since. "
        f"Run python scripts/gate.py {request_id()} before finishing. "
        "The pull request base is sdd/factory, never main. "
        f"Changed: {', '.join(paths)}"
    )
    json.dump({"followup_message": message}, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
