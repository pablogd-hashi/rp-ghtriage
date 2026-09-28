---
name: validate-change
description: Run gate.py and write 04-validation. Base is sdd/factory, never main.
disable-model-invocation: true
---

# Validate change

`main` is the demo. Never check it out or open a pull request against it. The branch is `sdd/factory-<key>`. The pull request base is `sdd/factory`.

Read only `requests/<id>/03-change/change.md`. Run:

`docker compose build worker`

`docker compose run --rm --no-deps -e LLM_PROVIDER=fake worker python scripts/gate.py <id>`

`scripts/gate.py` writes `04-validation/gate.json` and `report.md`. Do not hand-write those files. If the gate fails, go back to implement-change. Do not skip this phase.

Validate: `python3 scripts/validate_request.py <id> 04-validation`

Next: review-change
