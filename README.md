# PR Triage

Watches new pull requests on the GitHub public firehose, fetches the code that actually
changed, and sorts each one using LLM into different buckets`security`, `feature`, `refactor`, `docs` or
`dependency-bump`. In addition, it will add a risk note a human review and act upon.

## Why this source

The GitHub events feed hands you this for a new pull request:

```json
"pull_request": { "id": …, "number": 412, "url": "…", "base": {…}, "head": {…} }
```

That object carries no title, no description and no diff, so there is nothing in the
feed for a rule to match against. Everything the model reads is fetched by the pipeline
in a second and third call, which makes the enrichment step load-bearing rather than an
optimisation.

## Prerequisites

**Docker with Compose v2.** That is the only hard requirement. Everything else runs
inside containers, so there is no Python, Postgres or Ollama to install locally.

```bash
docker --version
docker compose version    # must be v2, not the old docker-compose binary
```

Built and tested on Docker 24.0.5 with Compose v2.20.

Compose v2 is the part that matters. The stack uses `depends_on: condition:` to order
startup, and `--wait` to block until health checks pass. The old `docker-compose` binary
ignores both, so services race each other and the worker starts before its topics exist.

**About 8GB free disk.** Roughly 6GB of images plus a 1.9GB model.

**No API keys, no accounts.** A GitHub token is optional and worth adding
([why](#get-a-github-token)), but the stack runs without one.

### Task is optional

Some commands below are written as `task something`. [Task](https://taskfile.dev) is a
small command runner, like `make` with YAML. It is a nice to have but not a dependency.

```bash
brew install go-task    # macOS
```

If you would rather not install it, every verb maps to a plain command:

| Task | Without Task |
|---|---|
| `task setup` | `cp .env.example .env` |
| `task up` | `docker compose up -d --wait` |
| `task down` | `docker compose down -v` |
| `task logs` | `docker compose logs -f` |
| `task test` | `docker compose run --rm --no-deps -e LLM_PROVIDER=fake worker python -m pytest tests/ -q` |
| `task seed` | `docker compose run --rm --no-deps worker python scripts/seed.py` |
| `task seed:offline` | `docker compose run --rm --no-deps worker python scripts/seed_offline.py --force` |
| `task eval` | `docker compose run --rm --no-deps worker python evals/run.py` |
| `task topics` | `docker compose exec redpanda rpk topic list --brokers redpanda:9092` |
| `task psql` | `docker compose exec postgres psql -U triage -d triage` |

`task --list` shows the rest.

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
[!Note]
**If the model download fails** (see below), the recorded rows are already on screen.
You do not need `task seed:offline` unless you wiped the database.

### If model download fails

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

The recorded rows stay on screen either way. There are three ways to get live classification:

```bash
task seed:offline    # the recorded results, no model needed
```

```bash
# or use an Ollama already running on your machine
echo "OLLAMA_HOST=http://host.docker.internal:11434" >> .env
echo "OLLAMA_MODEL=qwen2:7b" >> .env      # or whatever `ollama list` shows
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

A classic PAT with no scopes it's more than enough as the system only reads public
data.

```bash
echo "GITHUB_TOKEN=ghp_xxx" >> .env
docker compose up -d connect
```

### Use a hosted model instead

```bash
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-…
```

## Commands

```bash
task setup                   # create .env from .env.example if missing
task up                      # start everything and wait until it is ready
task down                    # stop everything and wipe the volumes
task logs                    # tail every service

task test                    # 46 tests. No model, no network, no GitHub needed
task eval                    # score the classifier twice, with and without the diff
task seed                    # reclassify the saved PRs with the current model
task seed:offline            # put the recorded results back, no model needed

task topics                  # list topics
task consume -- pr.enriched  # print one record as Connect produced it
task psql                    # database shell
task rate                    # GitHub quota remaining
task migrate                 # apply db/migrate.sql to a running database

task example -- 03-branch    # run one of the standalone Connect examples
task demo:fallback           # force the fallback path, see below
```

`task --list` shows all of them.

`task demo:fallback` runs the batch path (`scripts/seed.py`) against a model name that
does not exist, so every record takes the retry and then the fallback. It is the one place
that deliberately produces `unclear` / `fallback` rows, and it exists to make that path
visible. It overwrites the recorded rows, so `task seed:offline` puts them back. The long-running worker behaves differently on purpose: it waits for a model
rather than consuming without one, for the reason given above.

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
| `docs/architecture.md` | Diagrams, decision log, known limitations |
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
## What surprised me
The Github event feeds payload provides literally nothing, and it's incredible sparse. If we take 52 sample eventsm *payload.pull_request* contains exactly 5 keys:
* base
* head
* id
* number
* url

Without having a title, body or diff, the pipeline goes completely blind. The design decision here was to add the enrichment step within the RedPanda Connect configuration ( more below in the tradeoff section),
to drop the "junk" events earlier ( instead of relying in the Python worker to do it). 

By looking at a sample of 220 events:
* 44  are *PullRequestEvent*
* 20  of those 44 have *action = opened* (14 merged, 10 labelled)
* 2  of those 20 are *bots*
* 18  are selected        
 
This represents a roughly 92% drop of events before any enrichment fetch or LLM reasoning call is produced, aggressively protecting the compute and API budge. 

## Tradeoffs

### Enrichment in the Connect config vs. in the Python worker
The decision to put enrichment step in the Connect configuration is definitely a trade off between compute cost and keeping the complex data gathering logic out of the application.
Although Connect has routing rules for failures, if the Connect fetch fails (e.g., the code diff is too large and times out), the messages keep flowing. Connect then passes the payload alone
completely intact to the worker, but it's missing the files and patches. In another words, the pipeline is hiding its own failures as you are asking
LLM to judge security risks on an event title alone, because the diff fetch was too large and failed. 

#### Alternative

The alternative would be to perform all API fetches and bot filtering directly in the Python application code. I would flip to application-side if we were running a highly sensitive production environment where silent enrichment failures can't be tolerated; 
If we flip it to the Python logic, there's a broader spectrum of catches we can perform:HTTP timeouts, trigger targeted retries with cleaner error handling, and explicitly mark those records as failures.

### One LLM call vs. a multi-step reasoning

I made the decision to use a multi-step reasoning loop (using a first call to classify and score confidence, a conditional confidence gate, a stricter retry prompt, and a second details call) rather than a single comprehensive prompt. 
The aim here is to only trigger the expensive, detailed analysis call on high-confidence classifications, and we can target the second call’s prompt strictly to the specific files identified as evidence in the first step. 
The alternative would be to request the category, confidence, and risk note in one single JSON payload. 


#### Alternative
I would flip it to a single-call if there's a transition from local models (like qwen2.5:3b) to a premium tier capable hosted model like Anthropic's Claude or openAI. 
Large hosted models handle complex JSON schemas seamlessly, making retry loops redundant. Also the network latency of sequential API round-trips to an external provider dominates our execution time, making a single comprehensive call faster and cheaper.


## Where this breaks in production

The GitHub anonymous rate limit of 60 requests per hour is one of the first limiting factors to scale this in production. 
The way this codebase pipeline works is by pulling the public event feed every minute to respect Github headers. By simple math, polling once a minute is a 60 calls an hour so that list call alone consumes the entire budget without even processing a single PR's file.

Once the rate limit is reached, the system goes down in completely silence. The reason being, when the list call and enrichment fetches fail simultaneously, no new events ever enter the pipeline, leaving the deadqueue list
completely empty. As of today, by design nothing gets too far enough into the application logic to fail a violation check, so it silently stalls.


## Why this matters
There has not been in history such a massive volume of PR's being generated daily, since the AI era came to be. But companies (highly regulated specially but not limited to), still run by legacy process for reviewing and approving changes.
This system has been design to act as an automated guardrail sitting in the development pipeline ( orchestrated via [connect/ingest.yaml](/https://github.com/pablogd-hashi/rp-ghtriage/blob/main/connect/ingest.yaml) and [worker.py](https://github.com/pablogd-hashi/rp-ghtriage/blob/main/worker.py)),to triage and classify pull request with the goal of empowering security, engineering, and platform teams to move their focus to harness and validation, 
leaving the heavy lifting of filtering which changes are worth reviewing and which one discard. 

Most times than not, changes are not about the technology implemented, but on removing blockers on how people use the tools, and how process evolve and mature to operate at scale within ever changing operating models. While demonstrated here on a public GitHub stream, this pipeline is a direct stand-in for an enterprise compliance running on private and public codebases.