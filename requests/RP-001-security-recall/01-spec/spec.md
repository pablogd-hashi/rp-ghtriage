# Security recall

id: RP-001-security-recall
seam: eval

## Goal

Report security recall from evals/run.py, print GATE_JSON from --gate with no live model, and store today's recorded recall in evals/baseline.json so a later change cannot lower it.

## Acceptance

- AC-1: the full and ablated table prints security recall | proof: tests/test_eval_gate.py::test_security_recall_printed
- AC-2: --gate prints GATE_JSON and does not call a live model | proof: tests/test_eval_gate.py::test_gate_json_no_model
- AC-3: baseline holds the recorded security recall | proof: gate:security_recall

## Out of scope

- triage changes
- a live model
- the security floor

status: approved
