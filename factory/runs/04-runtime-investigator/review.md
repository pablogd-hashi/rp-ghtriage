# 04 runtime investigator

Executed in the Cursor session on 2026-09-27. `cursor-agent` is not on PATH.

## Plan

`AGENT_INVESTIGATE` defaults to 0. The worker publishes security, floor-raised, or disagreeing rows to `pr.investigate` only when the flag is on. `investigator.py` runs the tool loop, writes `investigation` JSON, produces `pr.investigated`. The compose service is profile `investigate`, so `docker compose up` does not start it.

A failed tool loop stores `status=failed` and does not change the category.

## Review

APPROVE. Flag-off path does not publish. `label_source` unchanged. Gate still green. Compose config parses.
