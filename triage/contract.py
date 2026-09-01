"""The shapes everything agrees on. See docs/contracts.md for the prose version.

This is the trust boundary: the model is asked to produce JSON matching TriageResult,
and we validate before anything is stored or shown. A model answer that does not fit
these shapes is rejected, not massaged into something that fits.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Category(str, Enum):
    """What kind of change this is. The model must pick exactly one of these."""

    security = "security"                # auth, secrets, permissions, crypto, validation
    feature = "feature"                  # behaviour a user would notice
    refactor = "refactor"                # structure changed, behaviour did not
    docs = "docs"                        # docs, comments, README only
    dependency_bump = "dependency-bump"  # version numbers only
    unclear = "unclear"                  # we do not know, and we are saying so


class LabelSource(str, Enum):
    """HOW we arrived at the label. This is the column that lets us explain a weird
    row during a live demo instead of going quiet."""

    model = "model"              # first answer, confident enough to keep
    model_retry = "model_retry"  # first answer unusable/unsure; stricter retry worked
    fallback = "fallback"        # both attempts failed; forced to unclear, honestly
    skipped = "skipped"          # never asked the model (draft, no files, nothing to read)


class Confidence(BaseModel):
    """A bounded score plus the model's own one-line reason for it.

    Bounded 0..1 so the UI can render it without clamping, and so a model that
    returns 95 (meaning 95%) fails validation instead of silently becoming 'very
    confident indeed'."""

    score: float = Field(ge=0.0, le=1.0)
    rationale: str = ""


class Classification(BaseModel):
    """What the FIRST model call must return."""

    category: Category
    confidence: Confidence
    evidence_files: list[str] = Field(default_factory=list)


class Details(BaseModel):
    """What the SECOND, narrower model call must return. Only ever requested when
    the first call was confident, so these are null on fallback/skipped rows."""

    affected_area: str = ""
    risk_note: str = ""


class TriageResult(BaseModel):
    """The finished judgement for one pull request — what gets stored and shown."""

    category: Category
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = ""
    evidence_files: list[str] = Field(default_factory=list)
    affected_area: str | None = None
    risk_note: str | None = None

    label_source: LabelSource
    model: str = ""
    llm_calls: int = 0
    latency_ms: int = 0


# The categories a model is allowed to choose. `unclear` is deliberately NOT here:
# only our own fallback may write it, so "unclear" always means "we gave up", never
# "the model shrugged". That distinction is visible in label_source.
MODEL_CATEGORIES = frozenset(c.value for c in Category if c is not Category.unclear)
