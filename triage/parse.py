"""Turning whatever the model actually said into something we can trust.

This is the riskiest code here, because it is the only place where untrusted text
becomes structured data. Small local models do not return clean JSON. They wrap it
in chat ("Sure! Here's the analysis:"), fence it in markdown, leave trailing commas,
use curly quotes, and invent labels that are not on the list.

The rule this file obeys:

    REPAIR FORMATTING, NEVER REPAIR MEANING.

Fixing a trailing comma is formatting. Turning "banana" into "unclear" would be
inventing a judgement the model never made — so we refuse, and let the caller retry
or fall back honestly.
"""

from __future__ import annotations

import json
import re

from .contract import MODEL_CATEGORIES, Category, Classification, Confidence


class ParseError(Exception):
    """The model's answer could not be turned into a valid Classification.

    Always caught by reason.py, which decides whether to retry or give up. It is
    never allowed to reach the consumer loop."""


# ── Step 1: get rid of the wrapping ──────────────────────────────────────────────

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def strip_fences(text: str) -> str:
    """Pull the contents out of a ```json ... ``` block if there is one.

    Models fence their output constantly, even when told not to. If there is no
    fence we return the text unchanged and let the brace scan deal with it.
    """
    match = _FENCE.search(text)
    return match.group(1) if match else text


# ── Step 2: find the object ──────────────────────────────────────────────────────

def extract_first_json_object(text: str) -> str | None:
    """Return the first balanced {...} block, or None.

    WHY A COUNTER AND NOT A REGEX: a regex like r'\\{.*\\}' cannot count. Given

        Sure! {"category": "docs", "note": "fixes the {placeholder} bug"} Hope that helps!

    a greedy regex grabs to the LAST closing brace and a lazy one stops at the
    first — both wrong. You have to walk the string and track depth.

    We also track whether we are inside a JSON string, because a brace inside a
    string value is just a character and must not change the depth. That is the
    case a regex can never get right.
    """
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escaped = False

    for i in range(start, len(text)):
        ch = text[i]

        if in_string:
            if escaped:
                escaped = False       # this char was escaped; it means nothing special
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue                  # inside a string: braces are just characters

        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]   # balanced — this is the object

    return None   # ran off the end: truncated output, no closing brace


# ── Step 3: fix formatting damage ────────────────────────────────────────────────

# "smart" quotes, which models copy in from prose and which json.loads rejects.
_SMART_QUOTES = {
    "“": '"', "”": '"',   # “ ”
    "‘": "'", "’": "'",   # ‘ ’
}

# A comma directly before a closing brace or bracket: {"a": 1,} — invalid JSON,
# and something models produce constantly.
_TRAILING_COMMA = re.compile(r",(\s*[}\]])")


def repair(blob: str) -> str:
    """Fix formatting the model got wrong. Never changes any value."""
    for bad, good in _SMART_QUOTES.items():
        blob = blob.replace(bad, good)
    return _TRAILING_COMMA.sub(r"\1", blob)


# ── Step 4: normalise the label ──────────────────────────────────────────────────

# Real drifts seen from small models. Every key here is a FORMATTING variation of a
# real category — a different case, spacing, or an obvious synonym. Nothing here
# invents a judgement.
_CATEGORY_ALIASES = {
    "security fix": "security",
    "security-fix": "security",
    "securityfix": "security",
    "vulnerability": "security",
    "dependency bump": "dependency-bump",
    "dependency_bump": "dependency-bump",
    "dependencybump": "dependency-bump",
    "deps": "dependency-bump",
    "dependencies": "dependency-bump",
    "documentation": "docs",
    "doc": "docs",
    "refactoring": "refactor",
    "feat": "feature",
}


def normalize_category(value: object) -> str | None:
    """Map a model's label onto our enum, or return None if it is not one of ours.

    Returning None is the important behaviour. It means the caller RETRIES rather
    than storing a guess. `unclear` is never produced here — only the fallback in
    reason.py may write that, so "unclear" always means "we gave up" and never
    "the model said something odd".
    """
    if not isinstance(value, str):
        return None

    cleaned = value.strip().lower().replace("_", "-")
    if cleaned in MODEL_CATEGORIES:
        return cleaned

    # Try the alias table with underscores/hyphens both ways round.
    for candidate in (cleaned, cleaned.replace("-", " "), cleaned.replace("-", "_")):
        if candidate in _CATEGORY_ALIASES:
            return _CATEGORY_ALIASES[candidate]

    return None   # not one of ours — reject, do not coerce


def _coerce_confidence(raw: object) -> float:
    """Pull a 0..1 score out of whatever the model put in the confidence slot.

    Handles the two shapes it actually uses: a bare number, or a nested object
    {"score": 0.8, "rationale": "..."} — which is what we asked for.
    Percentages (85 meaning 85%) are rescaled; anything else fails.
    """
    if isinstance(raw, dict):
        raw = raw.get("score", raw.get("confidence"))

    if isinstance(raw, bool) or raw is None:
        raise ParseError(f"confidence missing or not a number: {raw!r}")

    if isinstance(raw, str):
        try:
            raw = float(raw.strip().rstrip("%"))
        except ValueError as exc:
            raise ParseError(f"confidence not numeric: {raw!r}") from exc

    if not isinstance(raw, (int, float)):
        raise ParseError(f"confidence not numeric: {raw!r}")

    score = float(raw)
    if 1.0 < score <= 100.0:      # model answered in percent
        score = score / 100.0
    if not 0.0 <= score <= 1.0:
        raise ParseError(f"confidence out of range: {score}")
    return score


# ── The one function the rest of the codebase calls ──────────────────────────────

def parse_classification(text: str) -> Classification:
    """Model text in, validated Classification out, or ParseError.

    Never returns a default. A caller that gets a ParseError must decide what to
    do about it — that decision lives in reason.py, not here.
    """
    if not text or not text.strip():
        raise ParseError("model returned nothing")

    blob = extract_first_json_object(strip_fences(text))
    if blob is None:
        raise ParseError("no balanced JSON object in model output")

    try:
        data = json.loads(repair(blob))
    except json.JSONDecodeError as exc:
        raise ParseError(f"not valid JSON after repair: {exc}") from exc

    if not isinstance(data, dict):
        raise ParseError(f"expected a JSON object, got {type(data).__name__}")

    category = normalize_category(data.get("category"))
    if category is None:
        raise ParseError(f"category not in enum: {data.get('category')!r}")

    rationale = ""
    raw_conf = data.get("confidence")
    if isinstance(raw_conf, dict):
        rationale = str(raw_conf.get("rationale", "") or "")
    rationale = rationale or str(data.get("rationale", "") or "")

    files = data.get("evidence_files") or []
    if not isinstance(files, list):
        files = []

    return Classification(
        category=Category(category),
        confidence=Confidence(score=_coerce_confidence(raw_conf), rationale=rationale),
        evidence_files=[str(f) for f in files][:10],
    )
