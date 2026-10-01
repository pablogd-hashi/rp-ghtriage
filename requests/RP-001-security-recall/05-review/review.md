APPROVE

- AC-1: `evals/run.py` prints a `sec recall` column for the full and ablated rows. `tests/test_eval_gate.py::test_security_recall_printed` passed.
- AC-2: `--gate` prints `GATE_JSON` and returns before `get_client`. `tests/test_eval_gate.py::test_gate_json_no_model` passed with the client patched to raise.
- AC-3: `evals/baseline.json` stores `security_recall` 0.25, the recorded 1 of 4. `gate:security_recall` passed.
