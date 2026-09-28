---
name: run-local-demo
description: Run RP-001 end to end on this machine. Base is sdd/factory, never main.
disable-model-invocation: true
---

# Run local demo

`main` is the demo branch and is not this demo. Do not check it out. RP-001's pull request base is `sdd/factory`.

On branch `sdd/factory-RP-001`, run `task demo`. That validates `requests/RP-001-security-recall` and runs `scripts/gate.py`. Do not merge the pull request.

Validate: `python3 scripts/validate_request.py RP-001-security-recall`

Next: factory-status
