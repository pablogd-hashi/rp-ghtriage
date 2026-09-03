# Ablation eval

## The labels

`labels.jsonl` is the only place in this repo that says what a *correct* answer is. The
eval scores the model against it, so the judgement in it has to be mine.

Nine of the twelve are uncontroversial. Three were arguable and I settled them:

| id | call | the reading I rejected |
|---|---|---|
| f003 | `security` | that it is a cleanup which happens to close a SQL injection |
| f009 | `refactor` | that a 40% speedup is user-visible enough to count as a feature |
| f010 | `dependency-bump` | that an `x/crypto` bump spanning CVEs is really security |

The `why` field on each line carries the reasoning.

Next improvement: replace these hand-written fixtures with real PRs captured off the live
pipeline (`task consume -- pr.enriched`), so the eval runs on traffic rather than examples
built to make a point.

## What it measures

The obvious objection to this whole design:

> "piping metadata into a model to get a label is a regex wearing a costume, because
> deleting the model leaves a rule that does the same job"

So we test exactly that, by running the same reasoning loop twice:

| Run | The model sees | Standing in for |
|---|---|---|
| `full` | title, body, filenames **and patch content** | what our pipeline fetches |
| `ablated` | title, body, filenames, **no patches** | what a metadata-only feed gives you |

If `full` beats `ablated`, the enrichment is doing work, and the number says how much.

Four of the twelve fixtures (`f001`, `f003`, `f006`, `f012`) have titles that actively
mislead, "bump deps" that disables JWT expiry checks, "fix typo" that opens CORS to `*`.
Those are the cases a title-only rule gets wrong, and they are in there on purpose.

## Run it

```bash
task eval
```
