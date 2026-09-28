# Path outside the seam

id: path-outside-seam
seam: eval

## Goal

An eval request must not list a triage file.

## Acceptance

- AC-1: the plan stays inside evals scripts and tests | proof: tests/test_ok.py::test_ac1

## Out of scope

- triage/reason.py

status: approved
