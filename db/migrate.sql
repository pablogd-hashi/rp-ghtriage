-- Re-runnable. Applied on a fresh volume (docker-entrypoint-initdb.d/02-migrate.sql)
-- AND on a running volume by `task migrate`.
--
-- schema.sql only runs when the Postgres data directory is empty. A
-- `docker compose up` that already has a volume will NOT pick up a new column
-- you added there. That is the trap in the surprise-diff hour: you add
-- `severity` to schema.sql, restart, and the column is still missing.
--
-- Recipe for a new column:
--   1. Add it to schema.sql (so the next `task down` + up is correct)
--   2. Add the same ALTER below (so the running demo is correct)
--   3. `task migrate`
--
-- Every statement here must be safe to run twice. Use IF NOT EXISTS.

-- Confirm 01-schema.sql already created the table. Fails loudly if this
-- file is applied against an empty database by mistake.
SELECT 1 FROM pr_triage LIMIT 0;

-- Example (uncomment and rename when the extension asks for a new field):
-- ALTER TABLE pr_triage ADD COLUMN IF NOT EXISTS severity TEXT;
