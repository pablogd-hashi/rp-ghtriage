#!/usr/bin/env python3
"""Run one work order through planner, builder, gate, and reviewer.

    python factory/run.py factory/work_orders/01-security-recall.md

AGENT_CMD is the headless agent. Default: `cursor-agent -p`.
Swap it with `claude -p` when that is the binary on PATH.
The prompt is the final argument. Nothing here merges. A person merges.
"""

from __future__ import annotations

import datetime as dt
import os
import pathlib
import shlex
import subprocess
import sys
import textwrap

ROOT = pathlib.Path(__file__).resolve().parent.parent
MAX_ROUNDS = int(os.environ.get("MAX_ROUNDS", "3"))
BASE = "harness/agent-factory"


def _agent_cmd() -> list[str]:
    return shlex.split(os.environ.get("AGENT_CMD", "cursor-agent -p"))


def call_agent(role: str, prompt: str, cwd: pathlib.Path, log_dir: pathlib.Path, round_n: int) -> str:
    cmd = _agent_cmd()
    prompt_path = log_dir / f"{role}-r{round_n}.prompt.md"
    prompt_path.write_text(prompt)
    proc = subprocess.run(
        cmd + [prompt],
        cwd=cwd,
        text=True,
        capture_output=True,
    )
    out = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    (log_dir / f"{role}-r{round_n}.out.md").write_text(out)
    if proc.returncode != 0:
        raise SystemExit(
            f"{role} exited {proc.returncode}. Command: {cmd[0]}. See {prompt_path.parent}"
        )
    return out


def _git(cwd: pathlib.Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, check=check)


def ensure_worktree(branch: str, path: pathlib.Path) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    _git(ROOT, "worktree", "add", "-b", branch, str(path), BASE)


def commit_worktree(path: pathlib.Path, message: str) -> bool:
    status = _git(path, "status", "--porcelain").stdout.strip()
    if not status:
        return False
    _git(path, "add", "-A")
    _git(path, "commit", "-m", message)
    return True


def open_pr(branch: str, title: str, body: str, log_dir: pathlib.Path) -> str:
    _git(worktree, "push", "-u", "origin", branch)
    proc = subprocess.run(
        [
            "gh", "pr", "create",
            "--base", BASE,
            "--head", branch,
            "--title", title,
            "--body", body,
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    text = (proc.stdout or "") + (proc.stderr or "")
    (log_dir / "pr.txt").write_text(text)
    if proc.returncode != 0:
        raise SystemExit(f"gh pr create failed:\n{text}")
    return proc.stdout.strip()


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python factory/run.py factory/work_orders/<name>.md", file=sys.stderr)
        return 2
    work_order = pathlib.Path(sys.argv[1])
    if not work_order.is_file():
        work_order = ROOT / sys.argv[1]
    if not work_order.is_file():
        print(f"no such work order: {sys.argv[1]}", file=sys.stderr)
        return 2

    order_text = work_order.read_text()
    title = order_text.splitlines()[0].lstrip("# ").strip()
    slug = work_order.stem
    run_id = dt.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + slug
    log_dir = ROOT / "factory" / "runs" / run_id
    log_dir.mkdir(parents=True)
    branch = f"factory/{slug}"
    worktree = ROOT / ".worktrees" / slug

    agents = (ROOT / "AGENTS.md").read_text()
    planner_role = (ROOT / "factory" / "roles" / "planner.md").read_text()
    builder_role = (ROOT / "factory" / "roles" / "builder.md").read_text()
    reviewer_role = (ROOT / "factory" / "roles" / "reviewer.md").read_text()

    plan = call_agent(
        "planner",
        f"{planner_role}\n\n## AGENTS.md\n\n{agents}\n\n## Work order\n\n{order_text}\n",
        ROOT,
        log_dir,
        0,
    )
    (log_dir / "plan.md").write_text(plan)
    ensure_worktree(branch, worktree)

    feedback = ""
    approved = False
    gate_text = ""
    for round_n in range(1, MAX_ROUNDS + 1):
        builder_prompt = textwrap.dedent(f"""
            {builder_role}

            ## AGENTS.md

            {agents}

            ## Work order

            {order_text}

            ## plan.md

            {plan}

            ## Feedback from the previous round

            {feedback or "(none, this is the first round)"}
        """)
        call_agent("builder", builder_prompt, worktree, log_dir, round_n)
        commit_worktree(worktree, f"{slug}: round {round_n}")

        gate = subprocess.run(
            [sys.executable, "scripts/gate.py"],
            cwd=worktree,
            text=True,
            capture_output=True,
        )
        gate_text = (gate.stdout or "") + (gate.stderr or "")
        (log_dir / f"gate-r{round_n}.txt").write_text(gate_text)
        gate_json = worktree / "gate.json"
        if gate_json.exists():
            (log_dir / f"gate-r{round_n}.json").write_text(gate_json.read_text())

        if gate.returncode != 0:
            feedback = "gate.py failed:\n\n" + gate_text[-4000:]
            continue

        diff = _git(worktree, "diff", f"{BASE}...HEAD").stdout
        (log_dir / f"diff-r{round_n}.patch").write_text(diff)
        review = call_agent(
            "reviewer",
            f"{reviewer_role}\n\n## AGENTS.md\n\n{agents}\n\n## Diff\n\n```\n{diff[:50000]}\n```\n\n## gate\n\n{gate_text[-2000:]}\n",
            worktree,
            log_dir,
            round_n,
        )
        (log_dir / f"review-r{round_n}.md").write_text(review)
        first = review.strip().splitlines()[0].strip() if review.strip() else ""
        if first.startswith("APPROVE"):
            approved = True
            break
        feedback = review

    if not approved:
        note = (
            f"Escalated after {MAX_ROUNDS} rounds. A person has to take "
            f"{work_order.name}. Last feedback:\n\n{feedback}\n"
        )
        (log_dir / "ESCALATION.md").write_text(note)
        print(note, file=sys.stderr)
        return 1

    body = textwrap.dedent(f"""
        ## Plan

        {plan}

        ## Gate

        ```json
        {(log_dir / f"gate-r{round_n}.json").read_text() if (log_dir / f"gate-r{round_n}.json").exists() else gate_text[-1500:]}
        ```

        Factory run: `factory/runs/{run_id}`. Not merged. A person merges into `{BASE}`.
    """)
    url = open_pr(branch, title, body, log_dir)
    (log_dir / "pr.url").write_text(url + "\n")
    print(url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
