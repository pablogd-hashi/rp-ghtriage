---
title: The evaluation
layout: default
nav_order: 6
---

# The evaluation

The obvious objection to this entire design is that piping metadata into a model to get a
label is a regex wearing a costume, because deleting the model leaves a rule doing the
same job. So rather than argue about it, the eval tests exactly that.

## What it measures

The same reasoning loop runs twice over the same twelve fixtures:

| Run | The model sees | Standing in for |
|---|---|---|
| `full` | title, body, filenames **and patch content** | what the pipeline actually fetches |
| `ablated` | title, body, filenames, **no patches** | what a metadata-only feed would give you |

If `full` beats `ablated`, the enrichment is doing work and the difference says how much.
Four of the twelve fixtures (`f001`, `f003`, `f006`, `f012`) carry titles that actively
mislead, as in "bump deps" that disables JWT expiry checks and "fix typo" that opens CORS
to `*`, and those are the cases a title-only rule gets wrong, sitting in there on purpose.

```bash
task eval
```

## The result, and what it honestly shows

`full` scores 9 out of 12 and `ablated` scores 8, so the difference is one label.

That number is worth being straight about rather than dressing up. It does **not** show
the enrichment is decorative. What it shows is that the pipeline delivers the diff
correctly while a 3B model running on a laptop can't always use it, and the three misses
prove the point: on all of them the model's second answer, the risk note, correctly named
the security problem while the label above it said `refactor` or `dependency-bump`.

So the eval is measuring the model rather than the plumbing. Re-running it against a
hosted model is the obvious next experiment and I'd expect the gap to widen, because the
ablated run should stay roughly where it is while the full run improves.

## The labels are the actual artefact

`labels.jsonl` is the only place in the repo that says what a *correct* answer is, which
means the judgement in it has to be mine rather than a model's.

Nine of the twelve are uncontroversial. Three were genuinely arguable and I settled them:

| id | My call | The reading I rejected |
|---|---|---|
| `f003` | `security` | that it's a cleanup which happens to close a SQL injection |
| `f009` | `refactor` | that a 40% speedup is user-visible enough to count as a feature |
| `f010` | `dependency-bump` | that an `x/crypto` bump spanning CVEs is really security |

The `why` field on each line carries the reasoning behind it.

## What would make it better

The twelve fixtures were written by hand to make a point and the labels were written by
the same hand, which is fine for a demo and isn't a real test. The next version should
use real pull requests captured off the live pipeline with
`task consume -- pr.enriched`, labelled after the fact, so the eval runs on actual
traffic rather than on examples built to prove something.

It should also report per-class recall for `security` specifically, because for this
system the number that matters isn't overall accuracy, it's how many real security
changes it missed.

Source:
[evals/](https://github.com/pablogd-hashi/rp-ghtriage/tree/main/evals).
