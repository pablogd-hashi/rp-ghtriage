---
name: run-in-cloud
description: Start a Cursor cloud agent from sdd/factory. The pull request base is sdd/factory, never main.
disable-model-invocation: true
---

# Run in cloud

`main` is the demo. The cloud agent starts from ref `sdd/factory` on branch `sdd/factory-<key>`. Its prompt is: "Run the SDD flow for requests/<id>, autonomous mode, stop at 06-pr. PR base is sdd/factory, never main."

It uses the same rules, skills, and hooks because they are in the repo. The pull request shows up in `factory-status`. This needs a Cursor plan and the repo connected in Cursor settings. Local delivery is the default.

Run `python3 scripts/cloud_agent.py <id>`. Without `CURSOR_API_KEY` the script stops and says so. The script sets `autoCreatePR` false so Cursor does not open a pull request against `main`.

Validate: `python3 scripts/validate_request.py <id>`

Next: factory-status
