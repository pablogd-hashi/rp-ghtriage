---
name: implement-change
description: Edit the planned files and write 03-change. Base is sdd/factory, never main.
disable-model-invocation: true
---

# Implement change

`main` is the demo. Never check it out or open a pull request against it. The branch is `sdd/factory-<key>`. The pull request base is `sdd/factory`.

Read only `requests/<id>/02-plan/plan.md`. Edit the files it lists. Write `03-change/change.md` with `## Edited` and `## Why`. The code stays in the repo, not in the markdown.

Do not edit `AGENTS.md` or `.cursor/`. Do not edit `evals/baseline.json` when it already exists on `sdd/factory`.

In manual mode, stop until the user says "approved".

Validate: `python3 scripts/validate_request.py <id> 03-change`

Next: validate-change
