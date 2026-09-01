"""Reads enriched pull requests off a topic, reasons about them, writes results.

Deliberately a plain for-loop over one message at a time. No threads, no async.
At this volume (a handful of PRs a minute) concurrency would buy nothing and cost
us the ability to read this file top to bottom.
"""

from __future__ import annotations

import json
import os
import signal
import sys

from confluent_kafka import Consumer, KafkaError, Producer

from triage import store
from triage.llm import get_client
from triage.reason import DEFAULT_THRESHOLD, triage

BROKERS = os.environ.get("REDPANDA_BROKERS", "redpanda:9092")
IN_TOPIC = os.environ.get("IN_TOPIC", "pr.enriched")
OUT_TOPIC = os.environ.get("OUT_TOPIC", "pr.triaged")
DLQ_TOPIC = os.environ.get("DLQ_TOPIC", "pr.dlq")
THRESHOLD = float(os.environ.get("CONFIDENCE_THRESHOLD", DEFAULT_THRESHOLD))

_running = True


def _stop(signum, frame):
    global _running
    print("shutting down...", flush=True)
    _running = False


def main() -> int:
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    client = get_client()
    conn = store.connect()
    producer = Producer({"bootstrap.servers": BROKERS})

    consumer = Consumer({
        "bootstrap.servers": BROKERS,
        "group.id": "pr-triage-worker",
        "auto.offset.reset": "earliest",
        # We commit ourselves, AFTER the row is written. If this process dies
        # mid-reason, the message is redelivered and reprocessed — which is safe,
        # because the Postgres write is an UPSERT. Losing a PR is worse than
        # doing one twice.
        "enable.auto.commit": False,
    })
    consumer.subscribe([IN_TOPIC])
    print(f"worker up: {IN_TOPIC} -> postgres + {OUT_TOPIC} (model={client.name}, "
          f"threshold={THRESHOLD})", flush=True)

    while _running:
        msg = consumer.poll(1.0)
        if msg is None:
            continue
        if msg.error():
            if msg.error().code() != KafkaError._PARTITION_EOF:
                print(f"consumer error: {msg.error()}", file=sys.stderr, flush=True)
            continue

        raw = msg.value()
        try:
            record = json.loads(raw)
        except (ValueError, TypeError) as exc:
            # Not even JSON. Nothing to reason about — park it and move on.
            print(f"unparseable message -> dlq: {exc}", file=sys.stderr, flush=True)
            producer.produce(DLQ_TOPIC, raw, headers={"reason": b"worker: not json"})
            consumer.commit(msg)
            continue

        try:
            # Everything that can go wrong inside triage() is already handled in
            # triage() and turned into a fallback row. This except is the last
            # resort for the genuinely unexpected — it must never kill the loop,
            # because one poisonous message would stop the whole pipeline.
            result = triage(record, client, THRESHOLD)
            store.save(conn, record, result)
            producer.produce(
                OUT_TOPIC,
                json.dumps({**record, "triage": result.model_dump(mode="json")}).encode(),
                key=(record.get("pr_url") or "").encode(),
            )
            print(f"{result.category.value:16} {result.confidence:.2f} "
                  f"[{result.label_source.value}] {record.get('repo')}#{record.get('pr_number')}",
                  flush=True)
        except Exception as exc:  # noqa: BLE001 - deliberate catch-all, see above
            print(f"UNEXPECTED, sending to dlq: {exc!r}", file=sys.stderr, flush=True)
            producer.produce(DLQ_TOPIC, raw, headers={"reason": str(exc)[:200].encode()})

        producer.poll(0)
        consumer.commit(msg)   # only now is this message accounted for

    producer.flush(5)
    consumer.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
