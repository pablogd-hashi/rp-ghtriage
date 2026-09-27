---
name: security-floor
description: Adds a raise-only security floor next to should_skip. Use when a pull request must be labelled security because of a code pattern or a disagreement between the label and the risk note.
---

# Security floor

Follow AGENTS.md. The floor is an `if` in `triage/reason.py`, next to
`should_skip`. It may set the category to `security`. It must not lower a label.
It must not add a fifth `label_source`.

1. Put the pattern match in code, not in a prompt.
2. Add a `FakeLLM` fixture for the branch. The assertion is that the floor
   decided the raise. The model reply may disagree, and the stored category is
   still `security`.
3. Include a negative fixture the floor must leave alone (a dependency version
   bump that only changes version numbers).
4. Record `floor_raised` via the extend-field skill. The model is not asked for
   that field.
5. Run `python scripts/gate.py`. A false raise fails the gate.
