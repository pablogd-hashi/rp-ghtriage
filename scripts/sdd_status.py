#!/usr/bin/env python3
"""Print each request's phase, gate result, and pull request.

`main` is the demo and is not a request branch. The pull request base is
`sdd/factory`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PHASES = (
    "01-spec",
    "02-plan",
    "03-change",
    "04-validation",
    "05-review",
    "06-pr",
    "07-ticket-update",
)


def phase_of(folder: Path) -> str:
    found = [name for name in PHASES if (folder / name).is_dir()]
    return found[-1] if found else "-"


def gate_of(folder: Path) -> str:
    path = folder / "04-validation" / "gate.json"
    if not path.is_file():
        return "-"
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return "invalid"
    return str(data.get("tests") or "-")


def pr_of(folder: Path) -> str:
    path = folder / "06-pr" / "pr.md"
    if not path.is_file():
        return "-"
    text = path.read_text()
    match = re.search(r"^url:\s*(\S+)\s*$", text, re.M)
    return match.group(1) if match else "-"


def main() -> int:
    root = ROOT / "requests"
    rows = []
    if root.is_dir():
        for folder in sorted(root.iterdir()):
            if not folder.is_dir() or folder.name.startswith("_"):
                continue
            rows.append((folder.name, phase_of(folder), gate_of(folder), pr_of(folder)))
    print(f"{'request':<32}{'phase':<22}{'gate':<10}pr")
    if not rows:
        print(f"{'(none)':<32}{'-':<22}{'-':<10}-")
        return 0
    for name, phase, gate, url in rows:
        print(f"{name:<32}{phase:<22}{gate:<10}{url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
