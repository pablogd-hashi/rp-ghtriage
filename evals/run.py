"""Does the fetched content actually change the answer?

Runs the same reasoning loop over the same fixtures twice — once with patch content,
once without — and prints the two side by side. See evals/README.md for why.
"""

from __future__ import annotations

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


def run(records, labels, client, include_patches: bool):
    hits, fallbacks, skips, calls = 0, 0, 0, 0
    misses = []

    for item in labels:
        record = records[item["event_id"]]
        result = triage(record, client, THRESHOLD, include_patches=include_patches)
        calls += result.llm_calls

        if result.label_source.value == "fallback":
            fallbacks += 1
        if result.label_source.value == "skipped":
            skips += 1

        if result.category.value == item["label"]:
            hits += 1
        else:
            misses.append((item["event_id"], item["label"], result.category.value,
                           record.get("title", "")))

    return {
        "hits": hits, "total": len(labels), "fallbacks": fallbacks,
        "skips": skips, "calls": calls, "misses": misses,
    }


def main() -> int:
    records, labels = load()
    client = get_client()
    print(f"model: {client.name}   threshold: {THRESHOLD}   fixtures: {len(labels)}\n")

    print("running FULL (with patch content)...", flush=True)
    full = run(records, labels, client, include_patches=True)
    print("running ABLATED (title + metadata only)...\n", flush=True)
    ablated = run(records, labels, client, include_patches=False)

    print(f"{'run':<10}{'correct':>10}{'fallbacks':>12}{'skipped':>10}{'llm calls':>12}")
    print("-" * 54)
    for name, r in (("full", full), ("ablated", ablated)):
        print(f"{name:<10}{r['hits']:>5}/{r['total']:<4}{r['fallbacks']:>12}"
              f"{r['skips']:>10}{r['calls']:>12}")

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
