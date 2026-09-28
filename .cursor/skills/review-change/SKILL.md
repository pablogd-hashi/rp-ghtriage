---
name: review-change
description: Run the readonly reviewer and write 05-review. Base is sdd/factory, never main.
disable-model-invocation: true
---

# Review change

`main` is the demo. Never check it out or open a pull request against it. The branch is `sdd/factory-<key>`. The pull request base is `sdd/factory`. Never merge.

Read `04-validation/gate.json`. Run the reviewer subagent (`.cursor/agents/reviewer.md`). Write its text to `05-review/review.md`. The first line is exactly `APPROVE` or `CHANGES`.

On `CHANGES`, go back to implement-change. On `APPROVE`, continue. Do not skip review in autonomous mode.

Validate: `python3 scripts/validate_request.py <id> 05-review`

Next: open-github-pr
