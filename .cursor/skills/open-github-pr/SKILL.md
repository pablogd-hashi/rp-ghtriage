---
name: open-github-pr
description: Open a pull request with base sdd/factory. Refuses main. Never merges.
disable-model-invocation: true
---

# Open GitHub PR

`main` is the demo. Never check it out, push it, or open a pull request against it. The branch is `sdd/factory-<key>` (`sdd/factory-RP-001` for RP-001). The base is `sdd/factory`. Never run `gh pr merge`.

1. Commit the request folder and the planned files on `sdd/factory-<key>`.
2. `git push -u origin HEAD:sdd/factory-<key>`
3. `gh pr create --base sdd/factory --head sdd/factory-<key>`. If the command does not contain `--base sdd/factory`, stop. If the base would be `main`, stop.
4. Write `06-pr/pr.md` with `base: sdd/factory`, the `url:`, and the body. Put `gate.json` in the body.

Validate: `python3 scripts/validate_request.py <id> 06-pr`

Next: ticket-update
