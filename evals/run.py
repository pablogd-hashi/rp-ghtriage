"""Does the fetched content actually change the answer?

Runs the same reasoning loop over the same fixtures twice, once with patch content,
once without, and prints the two side by side. See evals/README.md for why.
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


def security_recall(labels, predicted: dict[str, str]) -> tuple[int, int]:
    """Of the fixtures labelled security, how many the run also called security."""
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
    """The saved live run, keyed by fixture id. No model call."""
    enriched = json.loads((ROOT / "fixtures/enriched.json").read_text())
    triaged = json.loads((ROOT / "fixtures/triaged.json").read_text())
    by_title = {row["title"]: row for row in triaged}
    return {rec["event_id"]: by_title[rec["title"]] for rec in enriched}


def floor_over_recorded(labels) -> dict:
    """Apply the raise-only floor to the recorded rows. No model call.

    The patterns were written knowing these fixtures, so a perfect score here
    is the rules firing, not a blind measurement of a model.
    """
    from triage.contract import Category, LabelSource, TriageResult
    from triage.reason import apply_floor

    enriched = {rec["event_id"]: rec for rec in json.loads((ROOT / "fixtures/enriched.json").read_text())}
    rows = recorded_predictions()
    false_raises = 0
    sec_hits = sec_total = hits = 0
    for item in labels:
        row = rows[item["event_id"]]
        before = TriageResult(
            category=Category(row["category"]),
            confidence=float(row["confidence"]),
            rationale=row.get("rationale") or "",
            affected_area=row.get("affected_area"),
            risk_note=row.get("risk_note"),
            evidence_files=row.get("evidence") or [],
            label_source=LabelSource(row["label_source"]),
        )
        after = apply_floor(before, enriched[item["event_id"]])
        if after.category.value == item["label"]:
            hits += 1
        if item["label"] == "security":
            sec_total += 1
            if after.category is Category.security:
                sec_hits += 1
        changed_to_security = (
            before.category is not Category.security and after.category is Category.security
        )
        if item["label"] != "security" and changed_to_security:
            false_raises += 1
    total = len(labels)
    return {
        "hits": hits,
        "total": total,
        "security_hits": sec_hits,
        "security_total": sec_total,
        "floor_false_raises": false_raises,
        "floor_security_recall": round(sec_hits / sec_total, 4) if sec_total else None,
    }


def gate_metrics(labels) -> dict:
    """Numbers scripts/gate.py reads. Recorded rows only, so CI does not need a model."""
    predicted_rows = recorded_predictions()
    predicted = {eid: row["category"] for eid, row in predicted_rows.items()}
    hits = sum(1 for item in labels if predicted.get(item["event_id"]) == item["label"])
    sec_hits, sec_total = security_recall(labels, predicted)
    total = len(labels)
    floor = floor_over_recorded(labels)
    return {
        "accuracy_full": round(hits / total, 4) if total else None,
        "accuracy_ablated": None,
        "security_recall": round(sec_hits / sec_total, 4) if sec_total else None,
        "floor_false_raises": floor["floor_false_raises"],
        "floor_security_recall": floor["floor_security_recall"],
        "security_hits": sec_hits,
        "security_total": sec_total,
        "hits": hits,
        "total": total,
        "floor_hits": floor["hits"],
        "floor_security_hits": floor["security_hits"],
        "floor_security_total": floor["security_total"],
    }


def main() -> int:
    records, labels = load()
    if "--gate" in sys.argv:
        metrics = gate_metrics(labels)
        print(
            f"recorded security recall: {metrics['security_hits']}/{metrics['security_total']}"
        )
        print(
            f"floor: {metrics['floor_hits']}/{metrics['total']}  "
            f"security {metrics['floor_security_hits']}/{metrics['floor_security_total']}  "
            f"false raises {metrics['floor_false_raises']}"
        )
        print("GATE_JSON " + json.dumps({
            "accuracy_full": metrics["accuracy_full"],
            "accuracy_ablated": metrics["accuracy_ablated"],
            "security_recall": metrics["security_recall"],
            "floor_false_raises": metrics["floor_false_raises"],
            "floor_security_recall": metrics["floor_security_recall"],
        }))
        return 0

    client = get_client()
    print(f"model: {client.name}   threshold: {THRESHOLD}   fixtures: {len(labels)}\n")

    print("running FULL (with patch content)...", flush=True)
    full = run(records, labels, client, include_patches=True)
    print("running ABLATED (title + metadata only)...\n", flush=True)
    ablated = run(records, labels, client, include_patches=False)

    print(f"{'run':<10}{'correct':>10}{'sec recall':>12}{'fallbacks':>12}{'skipped':>10}{'llm calls':>12}")
    print("-" * 66)
    for name, r in (("full", full), ("ablated", ablated)):
        print(f"{name:<10}{r['hits']:>5}/{r['total']:<4}"
              f"{r['security_hits']:>6}/{r['security_total']:<5}"
              f"{r['fallbacks']:>12}{r['skips']:>10}{r['calls']:>12}")

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
