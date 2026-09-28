---
name: create-spec
description: Write 01-spec from pasted text or a GitHub issue URL and continue. Autonomous mode. Base is sdd/factory, never main.
disable-model-invocation: true
---

# Create spec

`main` is the demo. Never check it out or open a pull request against it. The branch is `sdd/factory-<key>`. The pull request base is `sdd/factory`.

1. Read the pasted request or the GitHub issue URL. Do not invent acceptance lines.
2. Copy `requests/_template/` to `requests/<id>/`.
3. Fill `01-spec/spec.md`. Set `status: approved`. `seam` is `guard`, `gate`, `contract`, `eval`, or `STOP`.
4. Write `01-spec/autonomous.json` as `{"mode": "autonomous"}`.
5. If `seam` is `STOP`, stop and say the design is wrong.

Validate: `python3 scripts/validate_request.py <id> 01-spec`

Next: spec-to-plan
