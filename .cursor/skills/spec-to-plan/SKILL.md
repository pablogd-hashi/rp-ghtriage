---
name: spec-to-plan
description: Write 02-plan from the approved spec only. Base is sdd/factory, never main.
disable-model-invocation: true
---

# Spec to plan

`main` is the demo. Never check it out or open a pull request against it. The branch is `sdd/factory-<key>`. The pull request base is `sdd/factory`.

Read only `requests/<id>/01-spec/spec.md`. Write `02-plan/plan.md`.

`## Files` lists paths in seam order. Contract order is `docs/contracts.md`, `triage/contract.py`, `triage/prompts.py` only if the model is asked, then `db/schema.sql`, `db/migrate.sql`, `triage/store.py`, `web.py`. `## Map` names every AC. `## Fixtures` names the FakeLLM case for each new branch.

In manual mode, stop until the user says "approved".

Validate: `python3 scripts/validate_request.py <id> 02-plan`

Next: implement-change
