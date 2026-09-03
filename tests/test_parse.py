"""Tests for the dirty-JSON parser.

Every case here is something a 3B model actually does. If any of these stops
working, rows get silently mislabelled, which is the worst failure this system
has, because a wrong label looks exactly like a right one.
"""

from __future__ import annotations

import pytest

from triage.contract import Category
from triage.parse import (
    ParseError,
    extract_first_json_object,
    normalize_category,
    parse_classification,
    repair,
)

GOOD = '{"category":"security","confidence":{"score":0.9,"rationale":"disables expiry check"},"evidence_files":["a.py"]}'


# ── finding the object ───────────────────────────────────────────────────────────

def test_plain_json():
    assert parse_classification(GOOD).category is Category.security


def test_chatty_preamble_and_markdown_fence():
    """The single most common shape: prose, then a fenced block, then more prose."""
    text = f"Sure! Here's my analysis:\n\n```json\n{GOOD}\n```\n\nHope that helps!"
    assert parse_classification(text).category is Category.security


def test_brace_inside_a_string_does_not_end_the_object():
    """THE reason this is a brace counter and not a regex.

    A greedy regex runs to the last '}' and a lazy one stops at the first. Only
    walking the string while tracking whether we are inside a quote gets this right.
    """
    text = 'Result: {"category":"docs","confidence":{"score":0.8,"rationale":"fixes the {placeholder} bug"}} done'
    result = parse_classification(text)
    assert result.category is Category.docs
    assert "{placeholder}" in result.confidence.rationale


def test_escaped_quote_inside_string():
    text = r'{"category":"docs","confidence":{"score":0.7,"rationale":"the \"foo\" flag"}}'
    assert parse_classification(text).category is Category.docs


def test_truncated_output_is_rejected():
    """Model hit its token limit mid-object. There is no closing brace, so there is
    no object, we must not accept a half-answer."""
    assert extract_first_json_object('{"category":"security","confid') is None
    with pytest.raises(ParseError):
        parse_classification('{"category":"security","confid')


def test_no_json_at_all():
    with pytest.raises(ParseError):
        parse_classification("I think this is probably a security change, honestly.")


def test_empty_response():
    with pytest.raises(ParseError):
        parse_classification("")


# ── formatting repair ────────────────────────────────────────────────────────────

def test_trailing_comma_is_repaired():
    text = '{"category":"docs","confidence":{"score":0.8,},}'
    assert parse_classification(text).category is Category.docs


def test_smart_quotes_are_repaired():
    assert '"category"' in repair('{“category”: “docs”}')


# ── the enum: normalise formatting, never invent meaning ─────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("security", "security"),
    ("  SECURITY  ", "security"),
    ("Security Fix", "security"),
    ("dependency bump", "dependency-bump"),
    ("dependency_bump", "dependency-bump"),
    ("deps", "dependency-bump"),
    ("Documentation", "docs"),
    ("refactoring", "refactor"),
])
def test_known_label_drift_is_normalised(raw, expected):
    assert normalize_category(raw) == expected


@pytest.mark.parametrize("raw", ["banana", "critical", "", None, 42, ["security"]])
def test_unknown_label_is_rejected_not_coerced(raw):
    """The important one.

    An unrecognised label must NOT quietly become 'unclear'. Returning None makes
    the caller retry. If this ever coerced instead, 'unclear' would stop meaning
    'we gave up' and start meaning 'the model said something odd and we hid it'.
    """
    assert normalize_category(raw) is None


def test_unknown_category_raises_so_the_loop_can_retry():
    with pytest.raises(ParseError, match="not in enum"):
        parse_classification('{"category":"banana","confidence":{"score":0.9}}')


def test_unclear_is_not_a_choice_the_model_may_make():
    """`unclear` is ours to write, in the fallback, not the model's to pick."""
    with pytest.raises(ParseError):
        parse_classification('{"category":"unclear","confidence":{"score":0.9}}')


# ── confidence ───────────────────────────────────────────────────────────────────

def test_bare_number_confidence():
    assert parse_classification('{"category":"docs","confidence":0.42}').confidence.score == 0.42


def test_percentage_is_rescaled():
    assert parse_classification('{"category":"docs","confidence":85}').confidence.score == 0.85


@pytest.mark.parametrize("bad", ['"high"', "null", "-1", "1000"])
def test_unusable_confidence_is_rejected(bad):
    with pytest.raises(ParseError):
        parse_classification('{"category":"docs","confidence":%s}' % bad)
