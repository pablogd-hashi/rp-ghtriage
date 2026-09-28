---
name: request-to-spec
description: Write 01-spec and stop for approval. Manual mode. Base is sdd/factory, never main.
disable-model-invocation: true
---

# Request to spec

`main` is the demo. Never check it out or open a pull request against it. The branch is `sdd/factory-<key>`. The pull request base is `sdd/factory`.

1. Read the pasted request or the GitHub issue URL.
2. Copy `requests/_template/` to `requests/<id>/`.
3. Fill `01-spec/spec.md`. Set `status: draft`. Do not write `autonomous.json`.
4. Stop until the user says "approved".

Validate: `python3 scripts/validate_request.py <id> 01-spec`

Next: spec-to-plan
