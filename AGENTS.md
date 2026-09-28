# AGENTS.md

`main` is the demo and stays as it is. Never check out `main`, commit to it,
push to it, merge into it, rebase it, or reset it. Never `git pull` on it.
Never open a pull request against it.

All work is on `sdd/factory`, cut from `origin/main`. Request branches are
`sdd/factory-<key>`. Every pull request has base `sdd/factory`. A person merges.
Nothing in this repo merges, and nothing goes to `main`.

## Seams

A change is `guard`, `gate`, `contract`, `eval`, or `STOP`.
`guard` is `should_skip` in `triage/reason.py`, before any model call.
`gate` is the confidence branch in `triage/reason.py`.
`contract` adds a field in the order recorded in `docs/sdd.md`.
`eval` touches `evals/`, `scripts/`, and `tests/` only.
`STOP` means the design is wrong. Write no code.

## House rules

Plain sync Python. No new frameworks. No agent SDKs in the product.
`label_source` is exactly `model`, `model_retry`, `fallback`, `skipped`.
`unclear` is written by the worker only. Repair formatting, never meaning.
If a decision can be an `if`, it is code, not prompt text.

## Proof

`python scripts/gate.py <id>` exits 0 before a change to `triage/` or `tests/`
is done. Security recall must not drop below `evals/baseline.json`.
