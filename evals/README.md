# Ablation eval

## ⚠️ These labels are a STARTING POINT, not mine yet

`labels.jsonl` was drafted by the agent alongside the fixtures. **Read every line and
change anything you disagree with** — especially `f009`, which is genuinely arguable
between `refactor` and `feature`.

This matters because the eval is the only place that defines what a correct answer *is*.
If the judgement in it is not mine, the number it produces measures nothing I can stand
behind. Ten minutes of reading buys the whole claim.

Ideally, replace these fixtures with **real** PRs captured from the live pipeline
(`rpk topic consume pr.enriched`) once a `GITHUB_TOKEN` is in `.env`.

## What it measures

The obvious objection to this whole design:

> "piping metadata into a model to get a label is a regex wearing a costume, because
> deleting the model leaves a rule that does the same job"

So we test exactly that, by running the same reasoning loop twice:

| Run | The model sees | Standing in for |
|---|---|---|
| `full` | title, body, filenames **and patch content** | what our pipeline fetches |
| `ablated` | title, body, filenames — **no patches** | what a metadata-only feed gives you |

If `full` beats `ablated`, the enrichment is doing work, and the number says how much.

Four of the twelve fixtures (`f001`, `f003`, `f006`, `f012`) have titles that actively
mislead — "bump deps" that disables JWT expiry checks, "fix typo" that opens CORS to `*`.
Those are the cases a title-only rule gets wrong, and they are in there on purpose.

## Run it

```bash
task eval
```
