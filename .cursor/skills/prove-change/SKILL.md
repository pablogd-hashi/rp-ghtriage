---
name: prove-change
description: Proves a triage change did not drop security recall. Use after editing triage or tests, and before claiming a change is done.
---

# Prove a change

Run `python scripts/gate.py` from the repo root.

Read `gate.json`. It has `tests`, `accuracy_full`, `accuracy_ablated`,
`security_recall`, and `floor_false_raises`.

The change is not done when tests failed, when `security_recall` is below
`evals/baseline.json`, or when `floor_false_raises` is above the baseline
allowance. Say the numbers in the pull request.
