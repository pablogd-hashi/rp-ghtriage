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


def run_agent_mode(records: dict, labels: list, repeat: int) -> int:
    """Four rows. The agent rows are scripted unless a person runs a hosted model.

    Scripted means the replies are fixtures. The numbers show the loop, the
    budget, and label stability. They are not a claim about a hosted model.
    """
    from triage.agent import run_agent
    from triage.contract import Category, LabelSource, TriageResult
    from triage.llm import ScriptedToolLLM
    from triage.reason import apply_floor

    catalog = json.loads((ROOT / "fixtures/tool_catalog.json").read_text())
    rows = recorded_predictions()
    workflow_hits = 0
    workflow_sec = 0
    sec_total = 0
    floor_hits = 0
    floor_sec = 0
    agent_hits = 0
    agent_sec = 0
    both_hits = 0
    both_sec = 0
    agent_calls = 0
    both_calls = 0
    agent_latency = 0
    both_latency = 0
    agent_flips = 0
    both_flips = 0
    workflow_latency = 0

    for item in labels:
        record = records[item["event_id"]]
        recorded = rows[item["event_id"]]
        workflow_latency += int(recorded.get("latency_ms") or 0)
        before = TriageResult(
            category=Category(recorded["category"]),
            confidence=float(recorded["confidence"]),
            rationale=recorded.get("rationale") or "",
            affected_area=recorded.get("affected_area"),
            risk_note=recorded.get("risk_note"),
            evidence_files=recorded.get("evidence") or [],
            label_source=LabelSource(recorded["label_source"]),
        )
        after = apply_floor(before, record)
        if before.category.value == item["label"]:
            workflow_hits += 1
        if after.category.value == item["label"]:
            floor_hits += 1
        if item["label"] == "security":
            sec_total += 1
            if before.category is Category.security:
                workflow_sec += 1
            if after.category is Category.security:
                floor_sec += 1

        if before.label_source is LabelSource.skipped:
            # unclear belongs to the worker. The agent is not asked.
            agent_labels = [before.category.value] * repeat
            both_labels = [before.category.value] * repeat
        else:
            def once(current: str) -> dict:
                client = ScriptedToolLLM([
                    {"type": "tool", "name": "list_changed_files", "input": {}},
                    json.dumps({
                        "category": after.category.value,
                        "rationale": "scripted; the floor label is the proposal",
                    }),
                ])
                return run_agent(record, client, current_category=current, catalog=catalog)

            agent_labels = []
            both_labels = []
            for _ in range(repeat):
                agent_out = once(before.category.value)
                both_out = once(after.category.value)
                agent_labels.append(agent_out["category"])
                both_labels.append(both_out["category"])
                agent_calls += agent_out["tool_calls"]
                both_calls += both_out["tool_calls"]
                agent_latency += agent_out["latency_ms"]
                both_latency += both_out["latency_ms"]
        if len(set(agent_labels)) > 1:
            agent_flips += 1
        if len(set(both_labels)) > 1:
            both_flips += 1
        if agent_labels[-1] == item["label"]:
            agent_hits += 1
        if both_labels[-1] == item["label"]:
            both_hits += 1
        if item["label"] == "security":
            if agent_labels[-1] == "security":
                agent_sec += 1
            if both_labels[-1] == "security":
                both_sec += 1

    total = len(labels)
    runs = total * repeat
    table = [
        ("workflow", workflow_hits, workflow_sec, 0, workflow_latency // total, 0),
        ("workflow+floor", floor_hits, floor_sec, 0, workflow_latency // total, 0),
        ("agent (scripted)", agent_hits, agent_sec, agent_calls, agent_latency // runs, agent_flips),
        ("floor+agent (scripted)", both_hits, both_sec, both_calls, both_latency // runs, both_flips),
    ]
    print(f"agent source: scripted    repeat: {repeat}    fixtures: {total}")
    print("A hosted model is LLM_PROVIDER=anthropic. These agent rows are the loop, not that model.\n")
    print(f"{'run':<24}{'correct':>10}{'sec recall':>12}{'tool calls':>12}{'latency':>10}{'flips':>8}")
    print("-" * 76)
    for name, hits, sec, calls, latency, flips in table:
        print(f"{name:<24}{hits:>5}/{total:<4}{sec:>6}/{sec_total:<5}{calls:>12}{latency:>8}ms{flips:>8}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate", action="store_true")
    parser.add_argument("--mode", choices=("workflow", "agent"), default="workflow")
    parser.add_argument("--repeat", type=int, default=1)
    args = parser.parse_args(argv)
    records, labels = load()
    if args.gate:
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

    if args.mode == "agent":
        return run_agent_mode(records, labels, max(1, args.repeat))

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
