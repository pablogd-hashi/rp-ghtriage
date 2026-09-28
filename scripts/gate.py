#!/usr/bin/env python3
"""Run pytest and the recorded eval, then write 04-validation for one request.

`main` is the demo. Gate results land on the request branch. The pull request
base is `sdd/factory`.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import validate_request  # noqa: E402

STAMP = ROOT / ".cursor" / "hooks" / "last-gate"


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["LLM_PROVIDER"] = "fake"
    return subprocess.run(cmd, cwd=cwd, env=env, text=True, capture_output=True)


def hollow(path: Path, fn_name: str) -> bool:
    tree = ast.parse(path.read_text())
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == fn_name:
            body = [
                stmt
                for stmt in node.body
                if not (
                    isinstance(stmt, ast.Expr)
                    and isinstance(stmt.value, ast.Constant)
                    and isinstance(stmt.value.value, str)
                )
            ]
            if not body or (len(body) == 1 and isinstance(body[0], ast.Pass)):
                return True
            if len(body) == 1 and isinstance(body[0], ast.Assert):
                test = body[0].test
                if isinstance(test, ast.Constant) and test.value is True:
                    return True
            return False
    return True


def resolve_test(request_dir: Path, proof: str) -> tuple[Path | None, Path, str]:
    file_part, _, _fn = proof.partition("::")
    local = request_dir / file_part
    repo = ROOT / file_part
    if local.is_file():
        return local, request_dir, proof
    if repo.is_file():
        return repo, ROOT, proof
    return None, ROOT, proof


def run_pytest(cwd: Path, node: str | None) -> tuple[bool, str]:
    cmd = [sys.executable, "-m", "pytest", "-q"]
    if node:
        cmd.append(node)
    else:
        cmd.append("tests/")
    proc = _run(cmd, cwd)
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, output


def run_eval() -> tuple[dict, str]:
    proc = _run([sys.executable, "evals/run.py", "--gate"], ROOT)
    output = (proc.stdout or "") + (proc.stderr or "")
    metrics: dict = {}
    for line in output.splitlines():
        if line.startswith("GATE_JSON "):
            metrics = json.loads(line[len("GATE_JSON ") :])
            break
    if proc.returncode != 0 and not metrics:
        metrics["eval_error"] = output[-2000:]
    return metrics, output


def load_baseline(request_dir: Path, fixture: bool) -> dict | None:
    if fixture and (request_dir / "baseline.json").is_file():
        return json.loads((request_dir / "baseline.json").read_text())
    path = ROOT / "evals" / "baseline.json"
    if path.is_file():
        return json.loads(path.read_text())
    return None


def load_metrics(request_dir: Path, fixture: bool) -> tuple[dict, str]:
    stub = request_dir / "stub_metrics.json"
    if fixture and stub.is_file():
        return json.loads(stub.read_text()), "stub_metrics.json"
    return run_eval()


def write_outputs(request_dir: Path, report: dict, lines: list[str]) -> None:
    out = request_dir / "04-validation"
    out.mkdir(parents=True, exist_ok=True)
    (out / "gate.json").write_text(json.dumps(report, indent=2) + "\n")
    (out / "report.md").write_text("\n".join(lines) + "\n")


def gate(request_dir: Path, fixture: bool) -> int:
    spec_path = request_dir / "01-spec" / "spec.md"
    if not spec_path.is_file():
        print("missing 01-spec/spec.md")
        return 1
    spec = validate_request.parse_spec(spec_path.read_text())
    failures: list[str] = []
    acceptance = []
    test_output = ""

    if not fixture:
        suite_ok, test_output = run_pytest(ROOT, None)
        if not suite_ok:
            failures.append("pytest failed")

    for ac in spec["acs"]:
        proof = ac["proof"]
        result = "passed"
        if proof.startswith("tests/"):
            file_path, cwd, node = resolve_test(request_dir, proof)
            fn_name = proof.split("::", 1)[-1]
            if file_path is None:
                result = "missing"
                failures.append(f"{ac['id']} test is missing: {proof}")
            elif hollow(file_path, fn_name):
                result = "hollow"
                failures.append(f"{ac['id']} hollow test: {proof}")
            else:
                ok, output = run_pytest(cwd, node)
                test_output += output
                if not ok:
                    result = "failed"
                    failures.append(f"{ac['id']} test failed: {proof}")
        elif proof.startswith("gate:"):
            result = "pending"
        acceptance.append({"id": ac["id"], "proof": proof, "result": result})

    metrics, eval_output = load_metrics(request_dir, fixture)
    baseline = load_baseline(request_dir, fixture)
    if metrics.get("eval_error"):
        failures.append("eval failed")
    if baseline:
        for key, floor in baseline.items():
            current = metrics.get(key)
            if current is None:
                failures.append(f"missing gate metric: {key}")
            elif key == "security_recall" and float(current) < float(floor):
                failures.append("security_recall dropped below evals/baseline.json")
    for item in acceptance:
        if item["proof"].startswith("gate:"):
            key = item["proof"].split(":", 1)[1]
            current = metrics.get(key)
            if current is None:
                item["result"] = "failed"
                if f"missing gate metric: {key}" not in failures:
                    failures.append(f"missing gate metric: {key}")
            else:
                item["result"] = "passed"

    tests_state = "failed" if any(
        item["result"] in {"failed", "missing", "hollow"} for item in acceptance
    ) or "pytest failed" in failures else "passed"
    report = {
        "tests": tests_state,
        "security_recall": metrics.get("security_recall"),
        "accuracy_full": metrics.get("accuracy_full"),
        "acceptance": acceptance,
    }
    for key, value in metrics.items():
        if key not in report and key != "eval_error":
            report[key] = value

    lines = [
        f"# Validation {spec.get('id') or request_dir.name}",
        "",
        f"tests: {tests_state}",
        f"security_recall: {report.get('security_recall')}",
        "",
        "## Acceptance",
    ]
    for item in acceptance:
        lines.append(f"- {item['id']}: {item['proof']} {item['result']}")
    if failures:
        lines.extend(["", "## Failures"])
        lines.extend(f"- {item}" for item in failures)
    write_outputs(request_dir, report, lines)

    if not fixture:
        STAMP.parent.mkdir(parents=True, exist_ok=True)
        STAMP.write_text(str(time.time()) + "\n")

    if test_output.strip():
        print(test_output)
    if eval_output.strip() and eval_output != "stub_metrics.json":
        print(eval_output)
    print(json.dumps(report, indent=2))
    for item in failures:
        print(item)
    return 1 if failures or tests_state == "failed" else 0


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("request_id", nargs="?")
    parser.add_argument("--root")
    args = parser.parse_args(argv)
    if args.root:
        request_dir = Path(args.root).resolve()
        fixture = True
    elif args.request_id:
        request_dir = validate_request.find_live(args.request_id)
        fixture = "evals/factory" in str(request_dir)
    else:
        print("usage: gate.py <id>", file=sys.stderr)
        return 2
    if not request_dir.is_dir():
        print(f"no request folder {request_dir}", file=sys.stderr)
        return 2
    return gate(request_dir, fixture)


if __name__ == "__main__":
    sys.exit(main())
