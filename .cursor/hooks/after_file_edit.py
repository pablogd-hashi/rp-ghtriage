#!/usr/bin/env python3
"""After an edit under requests/, return validate_request.py errors.

`main` is the demo. Request folders are not edited on `main`. The pull
request base is `sdd/factory`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PHASES = {
    "01-spec",
    "02-plan",
    "03-change",
    "04-validation",
    "05-review",
    "06-pr",
    "07-ticket-update",
}


def main() -> int:
    raw = sys.stdin.read() or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {}
    file_path = data.get("file_path") or data.get("path") or ""
    path = Path(file_path)
    try:
        rel = path.resolve().relative_to(ROOT)
    except ValueError:
        rel = Path(file_path)
    parts = rel.parts
    if len(parts) < 3 or parts[0] != "requests" or parts[1] == "_template":
        json.dump({}, sys.stdout)
        return 0
    phase = parts[2] if parts[2] in PHASES else ""
    cmd = [sys.executable, str(ROOT / "scripts" / "validate_request.py"), parts[1]]
    if phase:
        cmd.append(phase)
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    text = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        json.dump({"additional_context": text}, sys.stdout)
    else:
        json.dump({}, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
