# Missing gate metric

id: missing-metric
seam: eval

## Goal

The gate must reject a run that does not report security recall.

## Acceptance

- AC-1: the proof test asserts a real condition | proof: tests/test_ok.py::test_ac1
- AC-2: security recall is present | proof: gate:security_recall

## Out of scope

- a live model

status: approved
