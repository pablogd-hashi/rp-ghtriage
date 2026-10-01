---
title: Monitoring
layout: default
nav_order: 4
---

# Monitoring

`docker compose up` also starts Prometheus on <http://localhost:9090> and Grafana on
<http://localhost:3000>, with no login on either.

The question this answers is what I would watch and what I would page someone about, and
the short version is two alerts, two dashboards, and the broker's own health metrics
taken from Redpanda's published dashboard rather than built from scratch.

## What is watched, and why

| Signal | Source | Why it matters |
|---|---|---|
| Consumer lag on `pr-triage-worker` | Redpanda metrics | The model is slower than Connect, or the worker is down. The backlog grows |
| Depth of `pr.dlq` | Redpanda metrics | Records are being rejected by enrichment or by the worker |
| Share of PRs by `label_source` | Postgres | A rising `fallback` share means the model is degrading or unreachable |
| Time per PR, p95, by `label_source` | Postgres | The number that decides how many workers you need |
| Why it fell back | Postgres | Tells a model host problem apart from a prompt problem |
| Under-replicated partitions, leader changes, disk | Redpanda metrics | Broker health, and the first three things to watch on a real cluster |

## The two alerts

Both live in
[monitoring/alerts.yml](https://github.com/pablogd-hashi/rp-ghtriage/blob/main/monitoring/alerts.yml),
and both are single metrics with no recording rules behind them.

**Lag above 20, sustained for 5 minutes.** The worker gets through roughly 39 pull
requests an hour, so 20 is about half an hour of backlog, and the five minutes rules out
a burst from a single poll that would drain on its own.

**Any new record on `pr.dlq` within 15 minutes.** Nothing consumes that lane, so its
depth only ever goes up, which means alerting on the absolute value would page forever
once it was non-zero. What matters is new failures arriving, not old ones sitting there.

To watch them fire:

```bash
docker compose stop worker        # lag climbs; the alert fires after 5 minutes
docker compose start worker

echo '{"test":1}' | docker compose exec -T redpanda rpk topic produce pr.dlq
```

## The two dashboards

**`PR Triage`** is built for one question: is triage keeping up, and are the answers
healthy. It reads in rows, top to bottom.

- **Now.** Seven numbers: PRs triaged, fallback share, retry share, p95 time per PR,
  time since the last row, worker lag, and new DLQ records. The last two use the same
  expressions as the two alerts, so the dashboard shows what pages you.
- **Pipeline.** Lag and DLQ over time, with the alert thresholds drawn on, next to the
  fallback share. Lag climbing while time per PR stays flat means the worker is down or
  waiting, not slow.
- **Model.** How each PR got its label, as a share of each hour, with fixed colours:
  red for `fallback`, amber for `model_retry`. Next to it, time per PR at p95, one line
  per `label_source`.
- **Answers.** The confidence of kept answers against the 0.65 gate, the category mix,
  the delay from PR opened to triaged, and how often the details call comes back empty.
- **Fallbacks.** Fallbacks grouped by what went wrong, and the latest 50 with their
  reason and a link to the PR.

A `model` picker at the top filters every Postgres panel, so two models can be compared.

Three choices are worth explaining:

- **Share, not counts.** GitHub polls come in bursts, so a count goes up and down with
  volume. The share doesn't. Ratio panels leave out buckets with fewer than five PRs,
  because one fallback out of two rows would read as 50%.
- **Time per PR, not per call.** The earlier panel divided `latency_ms` by `llm_calls`.
  That averaged three different calls (classify, retry, details) and hid what a retry
  costs. Workers needed is roughly PRs per second times time per PR, so time per PR is
  the number that matters.
- **The details call gets its own panel.** It is best-effort and fails silently by
  design, so nothing else on the stack would show it breaking.

One limit applies to every Postgres panel. The upsert resets `triaged_at` when a PR is
reprocessed, so a row only counts in the hour of its last write. A fallback that a later
run fixed disappears from the history. Fixing that needs an append-only events table,
or a counter the worker exports. Both are schema or code changes, so they're left out
of this one.

**`Redpanda Ops Dashboard`** is the one Redpanda publishes in
[redpanda-data/observability](https://github.com/redpanda-data/observability), used
without a single edit. Its checksum matches upstream, which is deliberate, as a
hand-built copy would stop tracking Redpanda's metric names the moment they changed.

Worth saying out loud rather than letting someone discover it: this is a single-node
stack running `--mode dev-container` with one replica, so the under-replicated panel
reads zero forever and leader changes reads one and then stays flat. Both panels are
correct and both are inert here. Disk is the only one of the three that actually moves.
They stay on the dashboard because they are the first three things you would watch on a
real cluster and they cost nothing to keep.

## Why not OpenTelemetry

Redpanda already exposes Prometheus metrics natively on port 9644, which is published in
the compose file anyway, so Prometheus scrapes it directly. The application signals are
already columns sitting in Postgres, and Grafana reads Postgres. A collector would only
be a third container translating a format Prometheus reads natively.

OTel earns its place when you want a trace per pull request across Connect, the queue,
the worker and the model, to see where those 90 seconds actually go. That's a real next
step and it's the condition that would flip this decision, but it wasn't the question
being asked and it would roughly double the size of the change.

## One thing found while testing it

Redpanda's built-in `redpanda_kafka_consumer_group_lag_sum` reads zero when the consumer
group has no live member, which is precisely the case where the worker is dead, and a
dead worker is the thing you most want the alert to catch. So the lag alert derives lag
from the two raw gauges instead, high watermark minus committed offset, as those survive
an empty group.

Verified by stopping the worker: the built-in gauge stayed at 0 while the derived value
read 28, matching what `rpk group describe` reported. The alert now fires for a dead
worker as well as for a slow one.

This also requires `enable_consumer_group_metrics` on the cluster, which the
`topics-init` block sets, because without it neither gauge exists at all and the lag
alert has no data to work from.
