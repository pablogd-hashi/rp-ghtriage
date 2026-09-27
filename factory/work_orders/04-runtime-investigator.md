# Runtime investigator

## Goal

An investigator that stays off unless `AGENT_INVESTIGATE=1`. With the flag off,
`docker compose up` does not start it and the worker does not publish to it.
`main`'s demo behavior stays the same.

## Acceptance

- Worker publishes a row to `pr.investigate` only when the flag is on and the
  row is `security`, `floor_raised`, or the note disagrees with the label.
- A second consumer runs `triage.agent`, upserts an `investigation` JSON column,
  and produces `pr.investigated`.
- Tools stay read-only. A tool failure keeps the workflow category and writes
  `investigation.status = failed`.
- `docker-compose.yml` creates the two topics and defines the service. The
  service is behind the compose profile `investigate`, so a plain
  `docker compose up` does not start it.
- `label_source` is unchanged.
- `python scripts/gate.py` exits 0.

## Likely files

- `worker.py`
- `investigator.py`
- `triage/store.py`
- `db/schema.sql`
- `db/migrate.sql`
- `docker-compose.yml`
- `.env.example`
- `docs/contracts.md`
