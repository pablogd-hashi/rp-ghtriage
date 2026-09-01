# PR Triage

Watches new pull requests on the GitHub public firehose, **fetches the code that actually
changed**, and classifies each one — `security`, `feature`, `refactor`, `docs`,
`dependency-bump` — with a risk note a human can act on.

## Why this source

The GitHub events feed hands you this for a new pull request:

```json
"pull_request": { "id": …, "number": 412, "url": "…", "base": {…}, "head": {…} }
```

No title. No description. No diff. There is nothing here a rule could act on — every word
the model reads has to be fetched by the pipeline first. That is the point: strip the
enrichment out and the system does not degrade to a regex, it stops working.

## Run it

```bash
cp .env.example .env
docker compose up
```

Open <http://localhost:8000>. The table is filled on boot from recorded results
(`fixtures/triaged.json`) so you do not wait on a live pull request. The `How` column
says `model` — these are a recording of a real earlier run, not invented labels.

First run also downloads a ~2GB model, so give the worker a few minutes. Nothing else
is needed — no API keys, no accounts.

To re-run the **live** reasoning loop over the same saved PRs (so every row is from
*this* boot's model):

```bash
task seed
```

**If the model download fails** (see below), the recorded rows are already on screen.
You do not need `task seed:offline` unless you wiped the database.

### If the model will not download

`ollama pull` fetches from a CDN that can be slow or unreachable from inside Docker.
It timed out on the machine this was built on. **The stack still comes up** — the pull
is allowed to fail — but the worker will have no model and every row will land as
`fallback`.

Three ways round it, cheapest first:

```bash
task seed:offline                                  # recorded results, no model
```
```bash
# or use an Ollama already running on your machine
echo "OLLAMA_HOST=http://host.docker.internal:11434" >> .env
echo "OLLAMA_MODEL=qwen2:7b" >> .env               # or whatever `ollama list` shows
```
```bash
# or a hosted model
echo "LLM_PROVIDER=anthropic"     >> .env
echo "ANTHROPIC_API_KEY=sk-ant-…" >> .env
```

### Get a GitHub token (strongly recommended)

**A token is not optional — it is arithmetic.** Anonymous GitHub allows **60 requests
per hour**. Polling once a minute is 60 requests per hour on its own, so the poll alone
is the entire ceiling, before a single enrichment call.

Measured on this pipeline, anonymous:

```
consumed in 3 min: 6   →  2 req/min  =  120/hr
anonymous budget:                        60/hr
```

Twice the budget. It runs for roughly half an hour, then 403s until the hourly reset —
and because the *poll* fails too, no events enter the pipeline at all during that time.
The dead-letter topic stays empty because there is nothing to dead-letter.

A classic PAT with **no scopes ticked** raises the ceiling to 5,000/hr. It only reads
public data.

```bash
echo "GITHUB_TOKEN=ghp_xxx" >> .env
docker compose up -d connect
```

Check what is left at any time with `task rate`.

### Use a hosted model instead

```bash
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-…
```

Faster, cleaner JSON, and the fallback path stops firing so often.

## Commands

```bash
task test           # 44 tests — no model, no network, no GitHub needed
task eval           # ablation: does reading the diff beat reading the title?
task seed           # re-run the live loop over saved PRs (overwrites recorded rows)
task seed:offline   # reload recorded results — no model needed
task migrate        # apply db/migrate.sql to a running database
task demo:fallback  # point at a missing model, watch every row land as fallback
task consume -- pr.enriched   # see what Connect actually produces
task rate           # GitHub quota remaining
task down           # stop and wipe
```

## How it fits together

```
GitHub /events ──▶ Connect ──▶ topic pr.enriched ──▶ worker ──▶ Postgres ──▶ web
                   poll 60s                          classify              :8000
                   filter ~98%                        gate
                   dedupe                             retry
                   fetch PR + files                   fallback
                   truncate                              │
                        │                                └──▶ topic pr.triaged
                        └──▶ topic pr.dlq (enrichment failed)
```

| Path | What it is |
|---|---|
| `connect/ingest.yaml` | Poll, filter, dedupe, enrich, project, route |
| `triage/parse.py` | Turning dirty model output into something trustworthy |
| `triage/reason.py` | The loop: guard → classify → gate → extract → fallback |
| `triage/contract.py` | The shapes everything agrees on |
| `worker.py` / `web.py` | Consume-and-reason; serve |
| `db/schema.sql` | One row per PR (fresh volume) |
| `db/migrate.sql` | Same changes, for a database that is already running |
| `evals/` | The ablation |
| `docs/contracts.md` | What each stage promises the next |
| `NOTES.md` | Everything that broke while building this |

## The `label_source` column

Every row records **how** its label was reached:

| Value | Meaning |
|---|---|
| `model` | First answer, confident enough to keep |
| `model_retry` | First answer unusable or unsure; a stricter retry worked |
| `fallback` | Both attempts failed — wrote `unclear` rather than guessing |
| `skipped` | Never asked the model (draft PR, or nothing to read) |

It is on screen on purpose. When something odd appears, that column explains it instead of
anyone having to guess.

---

## Tradeoffs

<!-- TODO -->

## What surprised me

<!-- TODO -->

## Where this breaks in production

<!-- TODO -->

## Why this matters

<!-- TODO -->

## How this repo was built

<!-- TODO -->
