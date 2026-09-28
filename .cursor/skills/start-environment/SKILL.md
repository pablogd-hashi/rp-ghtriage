---
name: start-environment
description: Start the compose stack and wait until it is ready. Does not touch main.
disable-model-invocation: true
---

# Start environment

`main` is the demo. Do not check it out. This skill does not open a pull request. The factory base is `sdd/factory`.

Run `docker compose up -d --wait`. Do not run `docker compose down -v`.

Validate: `docker compose ps`

Next: factory-status
