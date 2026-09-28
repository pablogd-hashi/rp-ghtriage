# Change

## Edited

- evals/run.py
- evals/baseline.json
- tests/test_eval_gate.py

## Why

The ablation table now prints security recall. --gate scores the recorded rows and prints GATE_JSON without calling a model. baseline.json stores that recall so a later change cannot lower it.
