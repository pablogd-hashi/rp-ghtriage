"""The reasoning loop. One pull request in, one judgement out.

Read top to bottom — that is the order it runs in. The three places a change is
likely to land are marked SEAM 1/2/3.

The promise this file keeps: EVERY record produces a result. There is no path
where a PR arrives and nothing comes out. Failure is a value we record, not an
absence we ignore.
"""

from __future__ import annotations

import json
import time

from .contract import Category, LabelSource, TriageResult
from .llm import LLMClient, LLMError
from .parse import ParseError, extract_first_json_object, parse_classification, repair, strip_fences
from .prompts import (
    CLASSIFY_RETRY_SYSTEM,
    CLASSIFY_SYSTEM,
    DETAILS_SYSTEM,
    classify_user,
    details_user,
)

DEFAULT_THRESHOLD = 0.65


# ── SEAM 1: the guard ────────────────────────────────────────────────────────────
# Runs before any model call. Answers: is this worth spending money on?
# Extensions that land here: skip known-bot patterns, skip tiny PRs, skip vendored
# paths. Add a condition, add a fixture, done.

def should_skip(record: dict) -> str | None:
    """Return a reason to skip, or None to proceed. No model call happens here."""
    if record.get("draft"):
        return "draft PR"

    files = record.get("files") or []
    if not files:
        return "no files returned by enrichment"

    # Nothing to read means nothing to judge. Asking the model anyway would get us
    # a confident-sounding guess based on the repo name, which is worse than
    # admitting we do not know.
    has_content = any((f.get("patch") or "").strip() for f in files)
    if not has_content and not (record.get("title") or "").strip():
        return "no patch content and no title"

    return None


def _skipped(record: dict, reason: str, started: float) -> TriageResult:
    return TriageResult(
        category=Category.unclear,
        confidence=0.0,
        rationale=f"Skipped: {reason}.",
        evidence_files=[],
        label_source=LabelSource.skipped,
        model="",
        llm_calls=0,
        latency_ms=int((time.monotonic() - started) * 1000),
    )


def _fallback(record: dict, reason: str, model: str, calls: int, started: float) -> TriageResult:
    """We tried and failed. Say so, in the row, with the reason.

    This is the only place `unclear` is written after a model call — so a row
    labelled unclear with label_source=fallback always means "we gave up", never
    "the model said something we quietly accepted"."""
    return TriageResult(
        category=Category.unclear,
        confidence=0.0,
        rationale=f"Could not classify: {reason}.",
        evidence_files=[],
        label_source=LabelSource.fallback,
        model=model,
        llm_calls=calls,
        latency_ms=int((time.monotonic() - started) * 1000),
    )


def _extract_details(client: LLMClient, record: dict, evidence_files: list[str]) -> dict:
    """The second, narrower call. Best-effort by design.

    If this fails we keep the classification and lose only the prose note — the
    label is the valuable part, and it is already in hand. So a failure here
    must never downgrade a good classification to a fallback.
    """
    try:
        raw = client.complete(DETAILS_SYSTEM, details_user(record, evidence_files), max_tokens=300)
        blob = extract_first_json_object(strip_fences(raw))
        if blob is None:
            return {}
        data = json.loads(repair(blob))
        if not isinstance(data, dict):
            return {}
        return {
            "affected_area": str(data.get("affected_area", ""))[:120] or None,
            "risk_note": str(data.get("risk_note", ""))[:400] or None,
        }
    except (LLMError, ValueError, TypeError):
        return {}


def triage(
    record: dict,
    client: LLMClient,
    threshold: float = DEFAULT_THRESHOLD,
    include_patches: bool = True,
) -> TriageResult:
    """Classify one enriched pull request record.

    include_patches=False is the ablation used by evals/run.py — the model then
    sees only what the GitHub feed could have given us.
    """
    started = time.monotonic()
    calls = 0

    # SEAM 1 --------------------------------------------------------------------
    skip_reason = should_skip(record)
    if skip_reason:
        return _skipped(record, skip_reason, started)

    # Attempt 1: the normal prompt.
    classification = None
    failure = ""
    try:
        calls += 1
        raw = client.complete(CLASSIFY_SYSTEM, classify_user(record, include_patches))
        classification = parse_classification(raw)
    except ParseError as exc:
        failure = f"unreadable answer ({exc})"
    except LLMError as exc:
        failure = f"model unreachable ({exc})"

    # SEAM 2: the confidence gate -----------------------------------------------
    # Retry when the answer was unusable OR when the model told us it was unsure.
    # Both mean the same thing operationally: we do not yet have an answer worth
    # storing. Extensions that land here: a third tier, routing urgent items to
    # their own topic, escalating `security` regardless of score.
    needs_retry = classification is None or classification.confidence.score < threshold

    if needs_retry:
        low = classification.confidence.score if classification else None
        try:
            calls += 1
            raw = client.complete(
                CLASSIFY_RETRY_SYSTEM,
                classify_user(record, include_patches),
                max_tokens=400,
            )
            retried = parse_classification(raw)
        except (ParseError, LLMError) as exc:
            reason = failure or f"low confidence {low} and retry failed"
            return _fallback(record, f"{reason}; retry also failed ({exc})", client.name, calls, started)

        # The retry parsed. If the model is STILL telling us it is unsure, we take
        # it at its word rather than storing a label neither of us believes.
        if retried.confidence.score < threshold:
            return _fallback(
                record,
                f"model unsure twice (best score {retried.confidence.score})",
                client.name, calls, started,
            )

        classification = retried
        source = LabelSource.model_retry
    else:
        source = LabelSource.model

    # Confident enough to be worth the second call.
    # Counted even when the call returns nothing — llm_calls is how many
    # times we paid, not how many times we parsed. The UI shows this number.
    calls += 1
    details = _extract_details(client, record, classification.evidence_files)

    return TriageResult(
        category=classification.category,
        confidence=classification.confidence.score,
        rationale=classification.confidence.rationale,
        evidence_files=classification.evidence_files,
        affected_area=details.get("affected_area"),
        risk_note=details.get("risk_note"),
        label_source=source,
        model=client.name,
        llm_calls=calls,
        latency_ms=int((time.monotonic() - started) * 1000),
    )
