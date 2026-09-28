---
name: ticket-update
description: Post the pull request URL back to the GitHub issue. Optional. Base is sdd/factory, never main.
disable-model-invocation: true
---

# Ticket update

`main` is the demo. Never check it out or open a pull request against it. The pull request base is `sdd/factory`. Do not merge.

Skip this phase when the spec has no issue URL. Otherwise comment on that issue with the pull request URL and write `07-ticket-update/update.md`.

Validate: `python3 scripts/validate_request.py <id> 07-ticket-update`

Next: stop
