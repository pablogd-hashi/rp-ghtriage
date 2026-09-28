#!/usr/bin/env python3
"""Accept the golden request and reject each broken copy.

`main` is the demo. These fixtures never target `main`. The pull request
base in a good folder is `sdd/factory`.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
FACTORY = Path(__file__).resolve().parent
PY = sys.executable

CASES = (
    ("golden/good-eval", "validate", 0, ""),
    ("golden/good-eval", "gate", 0, ""),
    ("broken/missing-ac", "validate", 1, "missing AC"),
    ("broken/path-outside-seam", "validate", 1, "outside the seam"),
    ("broken/hollow-test", "gate", 1, "hollow"),
    ("broken/missing-metric", "gate", 1, "missing gate metric"),
    ("broken/pr-base-main", "validate", 1, "PR base is main"),
)


def run_case(src: Path, kind: str) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / src.name
        shutil.copytree(src, dest)
        script = "validate_request.py" if kind == "validate" else "gate.py"
        return subprocess.run(
            [PY, str(ROOT / "scripts" / script), "--root", str(dest)],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )


def main() -> int:
    failed = 0
    for rel, kind, code, needle in CASES:
        proc = run_case(FACTORY / rel, kind)
        text = (proc.stdout or "") + (proc.stderr or "")
        ok = proc.returncode == code and (not needle or needle in text)
        status = "ok" if ok else "FAIL"
        print(f"{status} {rel} {kind} exit={proc.returncode}")
        if not ok:
            failed += 1
            print(text)
    if failed:
        print(f"{failed} factory eval(s) failed")
        return 1
    print(f"{len(CASES)} factory evals passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
