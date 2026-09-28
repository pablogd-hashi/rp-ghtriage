---
name: deliver-this
description: Paste a request and run autonomous mode through 06-pr. Base is sdd/factory, never main.
disable-model-invocation: true
---

# Deliver this

`main` is the demo. Never check it out or open a pull request against it. The branch is `sdd/factory-<key>`. The pull request base is `sdd/factory`. Never merge.

The user pasted a request. Write `01-spec/autonomous.json` and run create-spec, spec-to-plan, implement-change, validate-change, review-change, and open-github-pr. Do not stop between phases. Do not skip validation or review. Stop at `06-pr`.

Validate: `python3 scripts/validate_request.py <id> 06-pr`

Next: create-spec
