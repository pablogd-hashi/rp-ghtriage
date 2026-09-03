# PR Triage

Watches new pull requests on the GitHub public firehose, **fetches the code that actually
changed**, and sorts each one into `security`, `feature`, `refactor`, `docs` or
`dependency-bump`, with a risk note a human can act on.

## Why this source

The GitHub events feed hands you this for a new pull request:

```json
"pull_request": { "id": …, "number": 412, "url": "…", "base": {…}, "head": {…} }
```

That object carries no title, no description and no diff, so there is nothing in the
feed for a rule to match against. Everything the model reads is fetched by the pipeline
in a second and third call, which makes the enrichment step load-bearing rather than an
optimisation.

## Run it

```bash
cp .env.example .env
docker compose up
```

> [!TIP]
> If you use [Task](https://github.com/go-task/task), `task setup` creates `.env` from
> `.env.example` if it is missing, and leaves an existing one alone. Then:
>
> ```
> task setup
> task up
> ```
>
> `task --list` shows the rest.

Open <http://localhost:8000>. The table is filled on boot from recorded results
(`fixtures/triaged.json`) so you do not wait on a live pull request. The `How` column
says `model` because they are a recording of an earlier run against a live model.

First run also downloads a ~2GB model, so give the worker a few minutes. No API keys or
accounts are needed.

To re-run the **live** reasoning loop over the same saved PRs (so every row is from
*this* boot's model):

```bash
task seed
```

**If the model download fails** (see below), the recorded rows are already on screen.
You do not need `task seed:offline` unless you wiped the database.

### If the model will not download

`ollama pull` fetches from a CDN that can be slow or unreachable from inside Docker; it
timed out on the machine this was built on. The pull is allowed to fail so that the rest
of the stack still starts.

> [!NOTE]
> The worker checks it can reach the model before it consumes anything, and waits if it
> cannot, logging once a minute. Nothing is read off `pr.enriched` while it waits, so the
> backlog is preserved and drains when a model appears. Consumer lag is the symptom:
> `docker compose exec redpanda rpk group describe pr-triage-worker`.
>
> This is on purpose. Classifying without a model would write `fallback` rows and commit
> the offsets, and since GitHub does not re-emit a `PullRequestEvent`, those pull requests
> would never be classified again.

The recorded rows stay on screen either way. Three ways to get live classification,
cheapest first:

```bash
task seed:offline # recorded results, no model
```
```bash
# or use an Ollama already running on your machine
echo "OLLAMA_HOST=http://host.docker.internal:11434" >> .env
echo "OLLAMA_MODEL=qwen2:7b" >> .env # or whatever `ollama list` shows
```
```bash
# or a hosted model
echo "LLM_PROVIDER=anthropic" >> .env
echo "ANTHROPIC_API_KEY=sk-ant-…" >> .env
```

### Get a GitHub token

> [!IMPORTANT]
> Without a token the pipeline runs for about half an hour per hour and then stalls.
> A classic PAT with **no scopes ticked** is enough: it only reads public data.

Anonymous GitHub allows 60 requests per hour. Polling once a minute uses all 60 on the
list call alone, before any enrichment, and each surviving pull request costs two more
requests on top.

Measured on this pipeline without a token:

```
consumed in 3 min: 6 → 2 req/min = 120/hr
anonymous budget: 60/hr
```

At roughly twice the budget it runs for about half an hour and then 403s until the hourly
reset. The list call fails alongside the enrichment calls, so no events enter the pipeline
at all during that window, and the dead-letter topic stays empty because nothing gets far
enough to fail.

A classic PAT with no scopes ticked raises the ceiling to 5,000/hr, and only reads public
data.

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
task test # 44 tests, no model, no network, no GitHub needed
task eval # ablation: does reading the diff beat reading the title?
task seed # re-run the live loop over saved PRs (overwrites recorded rows)
task seed:offline # reload recorded results, no model needed
task migrate # apply db/migrate.sql to a running database
task demo:fallback # point at a missing model, watch every row land as fallback
task consume -- pr.enriched # see what Connect actually produces
task rate # GitHub quota remaining
task down # stop and wipe
```

## How it fits together

```
GitHub /events ──▶ Connect ──▶ topic pr.enriched ──▶ worker ──▶ Postgres ──▶ web
 poll 60s classify :8000
 filter ~92% gate
 dedupe retry
 fetch PR + files fallback
 truncate │
 │ └──▶ topic pr.triaged
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
| `NOTES.md` | Build log of what broke and why |

## The `label_source` column

Every row records **how** its label was reached:

| Value | Meaning |
|---|---|
| `model` | First answer, confident enough to keep |
| `model_retry` | First answer unusable or unsure; a stricter retry worked |
| `fallback` | Both attempts failed, wrote `unclear` rather than guessing |
| `skipped` | Never asked the model (draft PR, or nothing to read) |

> [!NOTE]
> `unclear` from `fallback` and `unclear` from `skipped` look identical in the category
> column and mean opposite things: one is a failed classification, the other is work
> correctly not done. This column is how you tell them apart.

---

## Tradeoffs

<!-- TODO -->

## What surprised me

<!-- TODO -->

## Where this breaks in production

<!-- TODO -->

## Why this matters

<!-- TODO -->
