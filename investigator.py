"""Second consumer for pr.investigate. Started only with the compose profile.

Reads a row the worker already classified, runs the bounded tool loop, and
writes the trace onto that row. It does not change the category. Tool failure
stores status=failed and leaves the workflow label where it was.
"""

from __future__ import annotations

import json
import os
import signal
import sys
import time

from confluent_kafka import Consumer, KafkaError, Producer

from triage import store
from triage.agent import run_agent
from triage.investigate import investigation_from
from triage.llm import get_client

BROKERS = os.environ.get("REDPANDA_BROKERS", "redpanda:9092")
IN_TOPIC = os.environ.get("INVESTIGATE_TOPIC", "pr.investigate")
OUT_TOPIC = os.environ.get("INVESTIGATED_TOPIC", "pr.investigated")

_running = True


def _stop(signum, frame):
    global _running
    _running = False


def main() -> int:
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    client = get_client()
    conn = store.connect()
    producer = Producer({"bootstrap.servers": BROKERS})
    catalog = {}
    catalog_path = os.environ.get("TOOL_CATALOG", "fixtures/tool_catalog.json")
    if os.path.exists(catalog_path):
        with open(catalog_path) as handle:
            catalog = json.load(handle)

    consumer = Consumer({
        "bootstrap.servers": BROKERS,
        "group.id": "pr-investigate-worker",
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
    })
    consumer.subscribe([IN_TOPIC])

    waited = 0
    while _running and not client.available():
        if waited % 60 == 0:
            print(f"investigator waiting for {client.name}", file=sys.stderr, flush=True)
        time.sleep(5)
        waited += 5
    if not _running:
        return 0

    print(f"investigator up: {IN_TOPIC} -> {OUT_TOPIC}", flush=True)
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
            body = json.loads(raw)
            record = {key: value for key, value in body.items() if key != "triage"}
            triage = body.get("triage") or {}
            outcome = run_agent(
                record,
                client,
                current_category=triage.get("category"),
                catalog=catalog,
            )
            payload = investigation_from(outcome)
            store.save_investigation(conn, record["pr_url"], payload)
            producer.produce(
                OUT_TOPIC,
                json.dumps({"pr_url": record["pr_url"], "investigation": payload}).encode(),
                key=(record.get("pr_url") or "").encode(),
            )
            print(f"investigation {payload['status']} {record.get('repo')}", flush=True)
        except Exception as exc:  # noqa: BLE001 - one bad message must not stop the loop
            print(f"investigation failed open: {exc!r}", file=sys.stderr, flush=True)
            try:
                body = json.loads(raw)
                store.save_investigation(conn, body["pr_url"], {
                    "status": "failed",
                    "reason": str(exc)[:300],
                    "trace": [],
                })
            except Exception:
                pass

        producer.poll(0)
        consumer.commit(msg)

    producer.flush(5)
    consumer.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
