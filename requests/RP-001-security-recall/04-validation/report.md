# Validation RP-001-security-recall

tests: passed
security_recall: 0.25

## Acceptance
- AC-1: tests/test_eval_gate.py::test_security_recall_printed passed
- AC-2: tests/test_eval_gate.py::test_gate_json_no_model passed
- AC-3: gate:security_recall passed
