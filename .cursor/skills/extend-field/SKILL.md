---
name: extend-field
description: Threads a new field end to end through contracts, the Python contract, the prompt, the database, and the web page. Use when adding a column or a response field to PR triage.
---

# Extend a field

Follow the Contract seam in AGENTS.md. Do the steps in order. Each step should
fail loudly until the next one is done.

1. Describe the field in `docs/contracts.md`. Decide the type and who is allowed
   to write it.
2. Add it to the Pydantic model in `triage/contract.py`.
3. Touch `triage/prompts.py` only when the model is asked for the field. If the
   worker sets it, say so in a comment and do not add it to either prompt.
4. Add the column to `db/schema.sql`, the same `ALTER TABLE ... IF NOT EXISTS`
   to `db/migrate.sql`, and the UPSERT in `triage/store.py`.
5. Show it in `web.py`.

Change `connect/ingest.yaml` only when the value comes from GitHub rather than
from the worker. `schema.sql` does not alter a database that already has data.
`db/migrate.sql` does.
