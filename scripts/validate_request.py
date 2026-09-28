#!/usr/bin/env python3
"""Check a request folder. Exit non-zero and list every error.

`main` is the demo. This script rejects a checkout of `main` and a pull
request whose base is not `sdd/factory`.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
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
SEAMS = {"guard", "gate", "contract", "eval", "STOP"}
AC_RE = re.compile(
    r"^- AC-(\d+): .+ \| proof: (tests/\S+\.py::\S+|gate:[A-Za-z0-9_]+)\s*$"
)
CONTRACT_ORDER = (
    "docs/contracts.md",
    "triage/contract.py",
    "triage/prompts.py",
    "db/schema.sql",
    "db/migrate.sql",
    "triage/store.py",
    "web.py",
)
CONTRACT_REQUIRED = (
    "docs/contracts.md",
    "triage/contract.py",
    "db/schema.sql",
    "db/migrate.sql",
    "triage/store.py",
    "web.py",
)


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def phase_index(name: str) -> int:
    if name not in PHASES:
        raise ValueError(name)
    return PHASES.index(name)


def section(text: str, heading: str) -> str:
    """Body under one ## heading, up to the next ## heading."""
    marker = f"## {heading}"
    start = text.find(marker)
    if start < 0:
        return ""
    rest = text[start + len(marker) :]
    nxt = re.search(r"^## ", rest, re.M)
    body = rest[: nxt.start()] if nxt else rest
    return body.strip()


def parse_spec(text: str) -> dict:
    lines = text.splitlines()
    title = lines[0].strip() if lines else ""
    ident = _field(text, "id")
    seam = _field(text, "seam")
    status = _field(text, "status")
    acs = []
    for line in section(text, "Acceptance").splitlines():
        match = AC_RE.match(line.strip())
        if match:
            acs.append({"id": f"AC-{match.group(1)}", "proof": match.group(2), "line": line.strip()})
    return {
        "title": title,
        "id": ident,
        "seam": seam,
        "status": status,
        "goal": section(text, "Goal"),
        "acs": acs,
        "has_goal": "## Goal" in text,
        "has_acceptance": "## Acceptance" in text,
        "has_out": "## Out of scope" in text,
    }


def _field(text: str, name: str) -> str:
    match = re.search(rf"^{name}:\s*(\S+)\s*$", text, re.M)
    return match.group(1) if match else ""


def parse_plan(text: str) -> dict:
    spec_line = _field(text, "spec")
    files = _bullets(section(text, "Files"))
    mapping = {}
    for line in section(text, "Map").splitlines():
        match = re.match(r"^- AC-(\d+):\s*(.+)\s*$", line.strip())
        if match:
            paths = [part.strip() for part in match.group(2).split(",") if part.strip()]
            mapping[f"AC-{match.group(1)}"] = paths
    return {
        "spec": spec_line,
        "files": files,
        "map": mapping,
        "has_files": "## Files" in text,
        "has_map": "## Map" in text,
        "has_fixtures": "## Fixtures" in text,
        "fixtures": section(text, "Fixtures"),
    }


def _bullets(body: str) -> list[str]:
    paths = []
    for line in body.splitlines():
        match = re.match(r"^- (\S+)\s*$", line.strip())
        if match:
            paths.append(match.group(1))
    return paths


def fits_seam(seam: str, path: str) -> bool:
    if seam == "STOP":
        return False
    if seam == "eval":
        return path.startswith(("evals/", "scripts/", "tests/")) and not path.startswith("triage/")
    if seam in {"guard", "gate"}:
        return path == "triage/reason.py" or path.startswith("tests/")
    if seam == "contract":
        return path in CONTRACT_ORDER or path.startswith("tests/")
    return False


def contract_errors(files: list[str]) -> list[str]:
    errors = []
    present = [path for path in files if path in CONTRACT_ORDER or path.startswith("tests/")]
    ordered = [path for path in present if path in CONTRACT_ORDER]
    canonical = [path for path in CONTRACT_ORDER if path in ordered]
    if ordered != canonical:
        errors.append(
            "contract files are out of order: "
            + ", ".join(CONTRACT_ORDER)
        )
    for path in CONTRACT_REQUIRED:
        if path not in files:
            errors.append(f"contract file missing: {path}")
    if "triage/prompts.py" in files:
        names = [path for path in files if path in CONTRACT_ORDER]
        if names != [path for path in CONTRACT_ORDER if path in names]:
            errors.append("triage/prompts.py must sit between triage/contract.py and db/schema.sql")
    return errors


def changed_paths(request_dir: Path, fixture: bool) -> list[str]:
    if fixture:
        listing = request_dir / "changed.txt"
        if not listing.exists():
            return []
        return [line.strip() for line in listing.read_text().splitlines() if line.strip()]
    seen: list[str] = []
    blobs = [
        _git("diff", "--name-only", "sdd/factory...HEAD"),
        _git("diff", "--name-only"),
        _git("diff", "--name-only", "--cached"),
        _git("ls-files", "--others", "--exclude-standard"),
    ]
    for proc in blobs:
        for line in (proc.stdout or "").splitlines():
            path = line.strip()
            if path and path not in seen:
                seen.append(path)
    return seen


def baseline_on_base(fixture: bool, request_dir: Path) -> bool:
    if fixture:
        return (request_dir / "baseline_on_base").exists()
    proc = _git("cat-file", "-e", "sdd/factory:evals/baseline.json")
    return proc.returncode == 0


def current_branch(request_dir: Path, fixture: bool) -> str:
    if fixture:
        listing = request_dir / "branch.txt"
        if not listing.exists():
            return ""
        return listing.read_text().splitlines()[0].strip()
    proc = _git("rev-parse", "--abbrev-ref", "HEAD")
    return (proc.stdout or "").strip()


def request_allowed(path: str, request_dir: Path, spec_id: str) -> bool:
    if spec_id and path.startswith(f"requests/{spec_id}/"):
        return True
    return (request_dir / path).is_file()


def check_spec(spec: dict, folder_name: str, errors: list[str]) -> None:
    if not spec["title"].startswith("# ") or spec["title"] == "#":
        errors.append("spec.md must start with # <title>")
    if not spec["id"]:
        errors.append("spec.md missing id:")
    elif spec["id"] != folder_name:
        errors.append(f"spec id {spec['id']} does not match {folder_name}")
    if spec["seam"] not in SEAMS:
        errors.append("spec.md seam must be guard|gate|contract|eval|STOP")
    if not spec["has_goal"]:
        errors.append("spec.md missing ## Goal")
    elif len(spec["goal"].split()) > 120:
        errors.append("## Goal is over 120 words")
    if not spec["has_acceptance"]:
        errors.append("spec.md missing ## Acceptance")
    if not spec["acs"]:
        errors.append("missing AC")
    if not spec["has_out"]:
        errors.append("spec.md missing ## Out of scope")
    if spec["status"] not in {"draft", "approved"}:
        errors.append("status must be draft|approved")


def check_plan(spec: dict, plan: dict, errors: list[str]) -> None:
    if not plan["spec"]:
        errors.append("plan.md missing spec:")
    if not plan["has_files"] or not plan["has_map"] or not plan["has_fixtures"]:
        errors.append("plan.md needs ## Files, ## Map, and ## Fixtures")
    if spec["seam"] in {"guard", "gate"} and "FakeLLM" not in plan["fixtures"]:
        errors.append("## Fixtures must name the FakeLLM case for each new branch")
    for ac in spec["acs"]:
        if ac["id"] not in plan["map"]:
            errors.append(f"plan does not cover {ac['id']}")
    for ac_id, paths in plan["map"].items():
        if ac_id not in {ac["id"] for ac in spec["acs"]}:
            errors.append(f"plan maps unknown {ac_id}")
        for path in paths:
            if path not in plan["files"]:
                errors.append(f"{path} is in ## Map and not in ## Files")
    if spec["seam"] == "STOP":
        if plan["files"]:
            errors.append("STOP: the design is wrong")
        return
    for path in plan["files"]:
        if not fits_seam(spec["seam"], path):
            errors.append(f"{path}: outside the seam")
    if spec["seam"] == "contract":
        errors.extend(contract_errors(plan["files"]))


def check_diff(spec: dict, plan: dict, paths: list[str], request_dir: Path, fixture: bool, errors: list[str]) -> None:
    protected_baseline = baseline_on_base(fixture, request_dir)
    for path in paths:
        if path == "AGENTS.md" or path.startswith(".cursor/"):
            errors.append(f"protected path: {path}")
        elif path == "evals/baseline.json" and protected_baseline:
            errors.append("protected path: evals/baseline.json")
        elif plan and not request_allowed(path, request_dir, spec.get("id", "")) and path not in plan.get("files", []):
            errors.append(f"{path}: not in the plan")


def check_review(text: str, errors: list[str]) -> None:
    lines = text.splitlines()
    first = lines[0].strip() if lines else ""
    if first not in {"APPROVE", "CHANGES"}:
        errors.append("review.md first line must be APPROVE or CHANGES")
        return
    if first == "CHANGES":
        for line in lines[1:]:
            if line.strip() and not re.match(r"^- \S+: .+$", line.strip()):
                errors.append(f"CHANGES line must be '- path: fix': {line.strip()}")


def check_pr(text: str, errors: list[str]) -> None:
    base = _field(text, "base")
    if base != "sdd/factory":
        shown = base or "(missing)"
        errors.append(f"PR base is {shown}")
        if shown != "sdd/factory":
            errors.append("PR base must be sdd/factory, never main")


def validate(request_dir: Path, phase: str | None, fixture: bool) -> list[str]:
    errors: list[str] = []
    if request_dir.name == "_template":
        errors.append("_template is not a request")
        return errors

    existing = [name for name in PHASES if (request_dir / name).is_dir()]
    for name in existing:
        idx = phase_index(name)
        for earlier in PHASES[:idx]:
            if earlier not in existing:
                errors.append(f"{name} exists without {earlier}")
    if phase:
        if phase not in PHASES:
            errors.append(f"unknown phase {phase}")
            return errors
        if phase not in existing:
            errors.append(f"missing phase {phase}")

    folder_name = request_dir.name
    id_file = request_dir / "id.txt"
    if id_file.exists():
        folder_name = id_file.read_text().strip()

    spec = {"seam": "", "acs": [], "id": folder_name}
    plan = None
    if "01-spec" in existing:
        spec_path = request_dir / "01-spec" / "spec.md"
        if not spec_path.is_file():
            errors.append("missing 01-spec/spec.md")
        else:
            spec = parse_spec(spec_path.read_text())
            check_spec(spec, folder_name, errors)
            if spec["seam"] == "STOP":
                errors.append("STOP: the design is wrong")

    if "02-plan" in existing:
        plan_path = request_dir / "02-plan" / "plan.md"
        if not plan_path.is_file():
            errors.append("missing 02-plan/plan.md")
        else:
            plan = parse_plan(plan_path.read_text())
            check_plan(spec, plan, errors)

    if "03-change" in existing:
        change = request_dir / "03-change" / "change.md"
        if not change.is_file():
            errors.append("missing 03-change/change.md")
        elif "## Edited" not in change.read_text() or "## Why" not in change.read_text():
            errors.append("change.md needs ## Edited and ## Why")

    if "04-validation" in existing:
        gate_path = request_dir / "04-validation" / "gate.json"
        report_path = request_dir / "04-validation" / "report.md"
        if not gate_path.is_file() or not report_path.is_file():
            errors.append("04-validation needs gate.json and report.md")
        elif gate_path.is_file():
            try:
                parsed = json.loads(gate_path.read_text())
            except json.JSONDecodeError:
                errors.append("gate.json is not JSON")
            else:
                if not isinstance(parsed, dict):
                    errors.append("gate.json must be an object")

    if "05-review" in existing:
        review = request_dir / "05-review" / "review.md"
        if not review.is_file():
            errors.append("missing 05-review/review.md")
        else:
            check_review(review.read_text(), errors)

    if "06-pr" in existing:
        pr = request_dir / "06-pr" / "pr.md"
        if not pr.is_file():
            errors.append("missing 06-pr/pr.md")
        else:
            check_pr(pr.read_text(), errors)

    branch = current_branch(request_dir, fixture)
    if not branch:
        errors.append("current branch is unknown")
    elif branch == "main":
        errors.append("current branch is main")

    if fixture and not (request_dir / "changed.txt").exists() and plan is not None:
        errors.append("fixture missing changed.txt")

    paths = changed_paths(request_dir, fixture)
    if plan is not None or any(
        path == "AGENTS.md" or path.startswith(".cursor/") or path == "evals/baseline.json"
        for path in paths
    ):
        check_diff(spec, plan or {"files": []}, paths, request_dir, fixture, errors)
    return errors


def find_live(request_id: str) -> Path:
    direct = ROOT / "requests" / request_id
    if direct.is_dir():
        return direct
    matches = [
        path
        for path in (ROOT / "evals" / "factory").rglob(request_id)
        if path.is_dir() and (path / "01-spec").is_dir()
    ]
    if len(matches) == 1:
        return matches[0]
    raise SystemExit(f"no request folder for {request_id}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("request_id", nargs="?")
    parser.add_argument("--root")
    parser.add_argument("phase", nargs="?")
    args = parser.parse_args(argv)
    if args.root:
        request_dir = Path(args.root).resolve()
        fixture = True
        phase = args.phase or args.request_id
        if phase and phase not in PHASES:
            phase = args.phase
    else:
        if not args.request_id:
            print("usage: validate_request.py <id> [phase]", file=sys.stderr)
            return 2
        request_dir = find_live(args.request_id)
        fixture = "evals/factory" in str(request_dir)
        phase = args.phase
    if not request_dir.is_dir():
        print(f"no request folder {request_dir}", file=sys.stderr)
        return 2
    errors = validate(request_dir, phase, fixture)
    if errors:
        print(f"{len(errors)} error(s):")
        for item in errors:
            print(f"- {item}")
        return 1
    print(f"ok {request_dir.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
