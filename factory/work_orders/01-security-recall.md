# Security recall

## Goal

Report per-class recall for `security` from `evals/run.py`, and record the current
number in `evals/baseline.json` so `scripts/gate.py` can fail a later drop.

## Acceptance

- `evals/run.py` prints security recall next to the full and ablated rows.
- `python evals/run.py --gate` prints a line `GATE_JSON {...}` with `accuracy_full`,
  `accuracy_ablated`, `security_recall`, and `floor_false_raises`.
- `--gate` does not call a live model. It scores `fixtures/triaged.json` against
  `evals/labels.jsonl`.
- `evals/baseline.json` stores that recorded security recall (1 of 4).
- `python scripts/gate.py` exits 0.

## Likely files

- `evals/run.py`
- `evals/baseline.json`
