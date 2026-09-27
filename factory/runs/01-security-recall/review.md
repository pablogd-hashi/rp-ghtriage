# 01 security recall

Executed in the Cursor session on 2026-09-27. `cursor-agent` is not on PATH, so `factory/run.py` was not the process that edited the files. The role prompts were followed here.

## Plan

Add per-class security recall to `evals/run.py` and store the recorded number in `evals/baseline.json`. `--gate` scores `fixtures/triaged.json` and does not call a model.

## Review

APPROVE. `label_source` untouched. Gate: tests passed, security_recall 0.25, which is 1 of 4.
