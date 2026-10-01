"""Does the fetched content actually change the answer?

Runs the same reasoning loop over the same fixtures twice, once with patch content,
once without, and prints the two side by side. See evals/README.md for why.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from triage.llm import get_client            # noqa: E402
from triage.reason import DEFAULT_THRESHOLD, triage   # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
THRESHOLD = float(os.environ.get("CONFIDENCE_THRESHOLD", DEFAULT_THRESHOLD))


def load():
    records = {r["event_id"]: r for r in json.loads((ROOT / "fixtures/enriched.json").read_text())}
    labels = [json.loads(l) for l in (ROOT / "evals/labels.jsonl").read_text().splitlines() if l.strip()]
    return records, labels


def security_recall(labels, predicted: dict[str, str]) -> tuple[int, int]:
    """Of the fixtures labelled security, how many this run also called security."""
    subset = [item for item in labels if item["label"] == "security"]
    hits = sum(1 for item in subset if predicted.get(item["event_id"]) == "security")
    return hits, len(subset)


def run(records, labels, client, include_patches: bool):
    hits, fallbacks, skips, calls = 0, 0, 0, 0
    misses = []
    predicted = {}

    for item in labels:
        record = records[item["event_id"]]
        result = triage(record, client, THRESHOLD, include_patches=include_patches)
        calls += result.llm_calls
        predicted[item["event_id"]] = result.category.value

        if result.label_source.value == "fallback":
            fallbacks += 1
        if result.label_source.value == "skipped":
            skips += 1

        if result.category.value == item["label"]:
            hits += 1
        else:
            misses.append((item["event_id"], item["label"], result.category.value,
                           record.get("title", "")))

    sec_hits, sec_total = security_recall(labels, predicted)
    return {
        "hits": hits, "total": len(labels), "fallbacks": fallbacks,
        "skips": skips, "calls": calls, "misses": misses,
        "security_hits": sec_hits, "security_total": sec_total,
    }


def recorded_predictions() -> dict[str, dict]:
    """Saved rows keyed by fixture id. No model call."""
    enriched = json.loads((ROOT / "fixtures/enriched.json").read_text())
    triaged = json.loads((ROOT / "fixtures/triaged.json").read_text())
    by_title = {row["title"]: row for row in triaged}
    return {rec["event_id"]: by_title[rec["title"]] for rec in enriched}


def gate_metrics(labels) -> dict:
    """Numbers scripts/gate.py reads. Recorded rows only, so there is no live model."""
    predicted_rows = recorded_predictions()
    predicted = {eid: row["category"] for eid, row in predicted_rows.items()}
    hits = sum(1 for item in labels if predicted.get(item["event_id"]) == item["label"])
    sec_hits, sec_total = security_recall(labels, predicted)
    total = len(labels)
    return {
        "accuracy_full": round(hits / total, 4) if total else None,
        "security_recall": round(sec_hits / sec_total, 4) if sec_total else None,
        "security_hits": sec_hits,
        "security_total": sec_total,
        "hits": hits,
        "total": total,
    }


def print_summary(full: dict, ablated: dict) -> None:
    print(f"{'run':<10}{'correct':>10}{'sec recall':>12}{'fallbacks':>12}{'skipped':>10}{'llm calls':>12}")
    print("-" * 66)
    for name, row in (("full", full), ("ablated", ablated)):
        print(
            f"{name:<10}{row['hits']:>5}/{row['total']:<4}"
            f"{row['security_hits']:>6}/{row['security_total']:<5}"
            f"{row['fallbacks']:>12}{row['skips']:>10}{row['calls']:>12}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate", action="store_true")
    args = parser.parse_args(argv)
    records, labels = load()
    if args.gate:
        metrics = gate_metrics(labels)
        print(
            f"recorded security recall: {metrics['security_hits']}/{metrics['security_total']}"
        )
        print("GATE_JSON " + json.dumps({
            "accuracy_full": metrics["accuracy_full"],
            "security_recall": metrics["security_recall"],
        }))
        return 0

    client = get_client()
    print(f"model: {client.name}   threshold: {THRESHOLD}   fixtures: {len(labels)}\n")

    print("running FULL (with patch content)...", flush=True)
    full = run(records, labels, client, include_patches=True)
    print("running ABLATED (title + metadata only)...\n", flush=True)
    ablated = run(records, labels, client, include_patches=False)

    print_summary(full, ablated)

    delta = full["hits"] - ablated["hits"]
    print(f"\ndifference: {delta:+d} correct when the model can read the diff")

    if ablated["misses"]:
        print("\nwhat the ablated run got wrong (i.e. what a metadata-only feed costs you):")
        for eid, expected, got, title in ablated["misses"]:
            print(f"  {eid}  \"{title[:32]}\"  expected {expected:<16} got {got}")

    if full["misses"]:
        print("\nwhat the full run still got wrong:")
        for eid, expected, got, title in full["misses"]:
            print(f"  {eid}  \"{title[:32]}\"  expected {expected:<16} got {got}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
