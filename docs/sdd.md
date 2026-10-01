# Spec-driven factory

`main` is the demo and stays as it is. Never check out `main`, commit to it, push to it, merge into it, rebase it, or reset it. Never `git pull` on it. Never open a pull request against it.

All work is on `sdd/factory`, cut from `origin/main`. Request branches are `sdd/factory-<key>`. Every pull request has base `sdd/factory`. A person merges. Nothing in this flow merges, and nothing goes to `main`.

## Phases

Each phase writes one file. That file is the only input to the next phase. The checks are code.

<a href="{{ '/assets/diagrams/sdd-phases.svg' | relative_url }}"><img src="{{ '/assets/diagrams/sdd-phases.svg' | relative_url }}" alt="Factory phases: spec, plan, change, review, pr, with validate_request and gate.py checks between them" width="100%"></a>

`scripts/validate_request.py` checks the folder, the seam, and the diff. `scripts/gate.py` runs pytest and `evals/run.py --gate`, then writes `04-validation/gate.json` and `report.md`. CI on pull requests into `sdd/factory` runs both again.

## Manual and autonomous

Manual mode starts with `request-to-spec` and stops after each phase until you say "approved".

Autonomous mode starts with `create-spec` or `deliver-this`. `01-spec/autonomous.json` is present. Phases 01 through 06 run without stopping. Validation and review still run. The flow stops at the pull request. It does not merge.

## Local and cloud

Local: Cursor on this machine. Say "deliver this: <request>" or "request to spec RP-00x".

Cloud: `run-in-cloud` starts a Cursor cloud agent from ref `sdd/factory`. The prompt is "Run the SDD flow for requests/<id>, autonomous mode, stop at 06-pr. PR base is sdd/factory, never main." The same rules, skills, and hooks are in the repo, so the cloud agent uses them too. `factory-status` shows the pull request. This needs a Cursor plan and the repo connected in Cursor settings. Local is the default.

## Seams

- `guard`: `should_skip` at the top of `triage/reason.py`, before any model call.
- `gate`: the confidence branch in `triage/reason.py`.
- `contract`, in this order: `docs/contracts.md`, `triage/contract.py`, `triage/prompts.py` only if the model is asked for the field, `db/schema.sql`, the same `ALTER` in `db/migrate.sql`, the UPSERT in `triage/store.py`, `web.py`.
- `eval`: `evals/`, `scripts/`, and `tests/` only.
- `STOP`: none of these. The phase ends and says the design is wrong.

## Why a harness, and the tradeoffs

**What exists on main today:** you ask an agent in chat, it edits files, and you judge the result yourself. There's no record of why a change was made, which rule it followed, or whether security recall moved. The removed branch tried to fix that with a Python program that scripted agent binaries. It was hard to run, tied to one tool, and never completed a run.

**What the harness changes:** the agent still writes the code. What changes is how its work is checked.

| Problem | Chat only (main) | SDD harness (sdd/factory) |
|---|---|---|
| "Did it break security detection?" | You re-read the diff | gate.py compares against evals/baseline.json and fails the PR |
| "Why was this changed?" | Lost in chat history | requests/RP-xxx/01-spec → 06-pr, committed with the code |
| Scope creep into Connect, prompts or the schema | Hope | validate_request.py rejects files not in the plan and paths outside the seam |
| House rules (`unclear` only from the worker, 4 label sources) | Prose the agent may ignore | Code: tests plus hooks |
| Laptop vs cloud agent | Different behaviour | Same rules, skills, hooks and files; CI re-checks both |
| Reviewing | Read a chat transcript | Read 7 short files |

**Why this repo suits a harness:**

1. **There's a number that can judge the agent:** security recall on labelled fixtures, with no live model.
2. **Changes come in only a few shapes** (the seams), so a spec can be forced to name one and the plan can be checked by code.
3. **Changes are small, frequent and alike,** so a fixed procedure pays for itself.
4. **The request folders are evidence a reviewer or panel can read.**

**Tradeoffs:**

| Cost | Why it matters | Mitigation |
|---|---|---|
| Ceremony: 7 files for a one-line fix | Slower for trivial edits | Autonomous mode; a hotfix path may skip 02, never 04 |
| Rigid formats | A small or rushed model fails them | Validators return specific errors, and hooks feed them back |
| Only as good as the evals | 12 labelled fixtures is a small eval | evals/factory golden and broken sets; grow labels.jsonl |
| Cloud agents cost money and are harder to debug | Earlier cloud runs failed with no message | Local is the default, cloud is opt-in, and the same CI gate runs either way |
| Harness code to maintain | Checks can drift from AGENTS.md | Rules point to AGENTS.md; the checks are tested in evals/factory |
| Tied to Cursor (rules, hooks, subagent) | Other agents ignore .cursor/ | gate.py and CI enforce the rules for any agent; AGENTS.md is the neutral entry point |
| The product doesn't become more agentic | The harness governs how code is built; the runtime stays a workflow | Intentional: triage must answer every PR |
