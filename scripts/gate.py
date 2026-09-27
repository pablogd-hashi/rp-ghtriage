#!/usr/bin/env python3
"""Deterministic gate. Pytest, then the eval's --gate path. Writes gate.json.

No live model. evals/run.py --gate scores the recorded fixtures. Until that
flag exists, the accuracy fields are null and only the tests can fail the run.
Once evals/baseline.json exists, a drop in security_recall fails the run.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
GATE_PATH = ROOT / "gate.json"
STAMP = ROOT / ".cursor" / "hooks" / "last-gate"
KEYS = (
    "tests",
    "accuracy_full",
    "accuracy_ablated",
    "security_recall",
    "floor_false_raises",
)


def _run(cmd: list[str], env: dict | None = None) -> subprocess.CompletedProcess:
    merged = os.environ.copy()
    merged["LLM_PROVIDER"] = "fake"
    if env:
        merged.update(env)
    return subprocess.run(
        cmd,
        cwd=ROOT,
        env=merged,
        text=True,
        capture_output=True,
    )


def run_pytest() -> tuple[bool, str]:
    proc = _run([sys.executable, "-m", "pytest", "tests/", "-q"])
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, output


def run_eval() -> tuple[dict, str]:
    """Prefer the deterministic --gate path. Missing flag means Phase A."""
    proc = _run([sys.executable, "evals/run.py", "--gate"])
    output = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0 and "unrecognized arguments: --gate" in output:
        return {}, output
    metrics = {}
    for line in output.splitlines():
        if line.startswith("GATE_JSON "):
            metrics = json.loads(line[len("GATE_JSON ") :])
            break
    if proc.returncode != 0 and not metrics:
        metrics["eval_error"] = output[-2000:]
    return metrics, output


def _baseline() -> dict | None:
    path = ROOT / "evals" / "baseline.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _below(current, floor) -> bool:
    if current is None or floor is None:
        return False
    return float(current) < float(floor)


def _above(current, cap) -> bool:
    if current is None or cap is None:
        return False
    return float(current) > float(cap)


def main() -> int:
    tests_ok, test_output = run_pytest()
    metrics, eval_output = run_eval()
    report = {
        "tests": "passed" if tests_ok else "failed",
        "accuracy_full": metrics.get("accuracy_full"),
        "accuracy_ablated": metrics.get("accuracy_ablated"),
        "security_recall": metrics.get("security_recall"),
        "floor_false_raises": metrics.get("floor_false_raises"),
    }
    # Extra fields the gate enforces once the floor exists. The five keys above
    # are the contract; these two say whether the floor itself regressed.
    if "floor_security_recall" in metrics:
        report["floor_security_recall"] = metrics["floor_security_recall"]

    GATE_PATH.write_text(json.dumps(report, indent=2) + "\n")
    STAMP.parent.mkdir(parents=True, exist_ok=True)
    STAMP.write_text(str(time.time()) + "\n")

    print(test_output)
    if eval_output.strip():
        print(eval_output)
    print(json.dumps(report, indent=2))

    failed = not tests_ok
    baseline = _baseline()
    if baseline:
        if _below(report.get("security_recall"), baseline.get("security_recall")):
            print("security_recall dropped below evals/baseline.json", file=sys.stderr)
            failed = True
        if _below(report.get("floor_security_recall"), baseline.get("floor_security_recall")):
            print("floor_security_recall dropped below evals/baseline.json", file=sys.stderr)
            failed = True
        if _above(report.get("floor_false_raises"), baseline.get("floor_false_raises")):
            print("floor_false_raises above evals/baseline.json", file=sys.stderr)
            failed = True
    if metrics.get("eval_error"):
        failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
