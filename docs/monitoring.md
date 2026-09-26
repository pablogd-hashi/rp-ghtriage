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
| Rows by `label_source`, per hour | Postgres | A rising `fallback` share means the model is degrading or unreachable |
| Model latency per call, p50 and p95 | Postgres | The number that decides how many workers you need |
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

**`PR Triage`** holds the two application panels, both built from SQL against the
`pr_triage` table rather than from any metric the worker emits. One shows rows by
`label_source` per hour, so a rising `fallback` share is visible as it happens, and the
other shows model latency per call at p50 and p95, dividing `latency_ms` by `llm_calls`
since a row covers two or three calls.

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
