#!/usr/bin/env python3
"""On stop, if triage/ or tests/ changed since the last gate, ask for gate.py."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STAMP = ROOT / ".cursor" / "hooks" / "last-gate"
WATCH = ("triage/", "tests/")


def _git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    return proc.stdout or ""


def changed_paths() -> list[str]:
    seen: list[str] = []
    blobs = [
        _git("diff", "--name-only", "HEAD"),
        _git("diff", "--name-only", "--cached"),
        _git("ls-files", "--others", "--exclude-standard"),
    ]
    for blob in blobs:
        for line in blob.splitlines():
            path = line.strip()
            if path.startswith(WATCH) and path not in seen:
                seen.append(path)
    return seen


def main() -> int:
    sys.stdin.read()
    paths = changed_paths()
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
        "Run python scripts/gate.py and read gate.json before finishing. "
        f"Changed: {', '.join(paths)}"
    )
    json.dump({"followup_message": message}, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
