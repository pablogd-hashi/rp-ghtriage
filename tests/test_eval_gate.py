"""Security recall on the recorded fixtures. No live model."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_security_recall_printed(capsys):
    sys.path.insert(0, str(ROOT))
    from evals.run import print_summary

    row = {
        "hits": 9,
        "total": 12,
        "security_hits": 1,
        "security_total": 4,
        "fallbacks": 0,
        "skips": 1,
        "calls": 0,
    }
    print_summary(row, row)
    out = capsys.readouterr().out
    assert "sec recall" in out
    assert "1/4" in out


def test_gate_json_no_model(monkeypatch):
    sys.path.insert(0, str(ROOT))
    import evals.run as run_mod

    def boom():
        raise AssertionError("live client")

    monkeypatch.setattr(run_mod, "get_client", boom)
    assert run_mod.main(["--gate"]) == 0
    proc = subprocess.run(
        [sys.executable, "evals/run.py", "--gate"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    assert "model:" not in proc.stdout
    line = next(item for item in proc.stdout.splitlines() if item.startswith("GATE_JSON "))
    metrics = json.loads(line[len("GATE_JSON ") :])
    assert metrics["security_recall"] == 0.25
    assert metrics["accuracy_full"] == 0.75
    baseline = json.loads((ROOT / "evals" / "baseline.json").read_text())
    assert baseline["security_recall"] == metrics["security_recall"]
