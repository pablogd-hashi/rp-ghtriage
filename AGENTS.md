# AGENTS.md

This file is the only source of truth for how an agent may change this repo.
Rules under `.cursor/rules/` point here. They do not restate these rules.

## House rules

Plain sync Python. No new frameworks. LangChain and CrewAI are out.

Function names match the seams: guard (`should_skip`), gate (the confidence
branch in `triage/reason.py`), contract (`triage/contract.py` and
`docs/contracts.md`).

Every branch of the reasoning loop has a `FakeLLM` fixture. Repair formatting,
never meaning. `unclear` is written only by the worker, never by the model.
No classification in Connect. `label_source` stays exactly these four values:
`model`, `model_retry`, `fallback`, `skipped`.

If a decision can be an `if`, it is an `if` in code, not a sentence in a prompt.

## Seams

A change is one of three things. If it is none of them, stop and say the design
is wrong before writing code.

**Guard.** Top of `triage/reason.py`, `should_skip`, before any model call.
Skip more work here. The row lands as `skipped`.

**Gate.** The confidence branch in `triage/reason.py`, after the parse.
Route here: retry, second call, fallback. A raise-only security floor lives
next to the guard, not inside the prompt.

**Contract.** A new field, in this order:

1. `docs/contracts.md`
2. `triage/contract.py`
3. `triage/prompts.py` — only if the model is asked for the field. A field the
   worker sets is not added to a prompt.
4. `db/schema.sql`, the same `ALTER` in `db/migrate.sql`, and the UPSERT in
   `triage/store.py`
5. `web.py`

Connect changes only when the field comes from GitHub.

## Proof

A change to `triage/` or `tests/` is not done until `python scripts/gate.py`
exits 0. The gate writes `gate.json`. Security recall must not drop below
`evals/baseline.json` once that file exists.

## What stays human

Merging a factory pull request. The factory opens the pull request and stops.
Pushes to `main` are refused. `docker compose down -v` is refused unless a
person asks for it in the prompt.
