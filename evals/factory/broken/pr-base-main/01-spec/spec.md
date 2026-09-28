# Pull request base is main

id: pr-base-main
seam: eval

## Goal

A pull request whose base is main must be rejected.

## Acceptance

- AC-1: the fixture test asserts a real condition | proof: tests/test_ok.py::test_ac1

## Out of scope

- merging

status: approved
