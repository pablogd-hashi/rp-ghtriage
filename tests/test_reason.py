"""Tests for the branching in the reasoning loop.

Driven by FakeLLM, whose call log lets us assert what DID and DID NOT happen,
"the second call never ran" is as important as "the label was right".
"""

from __future__ import annotations

from triage.contract import Category, LabelSource
from triage.llm import FakeLLM, LLMClient, LLMError
from triage.reason import should_skip, triage

GOOD_PATCH = "@@ -1,3 +1,4 @@\n-    jwt.decode(t, S)\n+    jwt.decode(t, S, options={'verify_exp': False})"


def record(**over) -> dict:
    base = {
        "pr_url": "https://api.github.com/repos/acme/api/pulls/1",
        "repo": "acme/api", "pr_number": 1, "author": "someone", "draft": False,
        "title": "bump deps", "body": "", "files_changed": 1,
        "additions": 1, "deletions": 1,
        "files": [{"filename": "src/auth.py", "status": "modified",
                   "additions": 1, "deletions": 1, "patch": GOOD_PATCH}],
    }
    base.update(over)
    return base


def classification(cat="security", score=0.9, files=("src/auth.py",)) -> str:
    return ('{"category":"%s","confidence":{"score":%s,"rationale":"because"},'
            '"evidence_files":%s}' % (cat, score, list(files))).replace("'", '"')


DETAILS = '{"affected_area":"authentication","risk_note":"expiry checks disabled"}'


# ── SEAM 1: the guard ────────────────────────────────────────────────────────────

def test_draft_pr_is_skipped_without_calling_the_model():
    llm = FakeLLM([])                      # no replies: any call would raise
    result = triage(record(draft=True), llm)
    assert result.label_source is LabelSource.skipped
    assert result.category is Category.unclear
    assert llm.calls == []                 # the point: we spent nothing
    assert result.llm_calls == 0


def test_no_files_is_skipped():
    result = triage(record(files=[]), FakeLLM([]))
    assert result.label_source is LabelSource.skipped
    assert "no files" in result.rationale


def test_should_skip_lets_a_real_pr_through():
    assert should_skip(record()) is None


# ── The happy path ───────────────────────────────────────────────────────────────

def test_confident_answer_triggers_the_second_call():
    llm = FakeLLM([classification(score=0.9), DETAILS])
    result = triage(record(), llm, threshold=0.65)

    assert result.category is Category.security
    assert result.label_source is LabelSource.model
    assert len(llm.calls) == 2                        # classify, then details
    assert result.affected_area == "authentication"
    assert result.llm_calls == 2


def test_second_call_only_sees_the_files_the_first_call_named():
    """The details prompt is narrower on purpose. That is what makes two calls
    cheaper than one big one."""
    rec = record(files=[
        {"filename": "src/auth.py", "status": "modified", "additions": 1, "deletions": 1, "patch": "AUTHPATCH"},
        {"filename": "docs/readme.md", "status": "modified", "additions": 1, "deletions": 1, "patch": "DOCSPATCH"},
    ])
    llm = FakeLLM([classification(files=("src/auth.py",)), DETAILS])
    triage(rec, llm)

    details_prompt = llm.calls[1]["user"]
    assert "AUTHPATCH" in details_prompt
    assert "DOCSPATCH" not in details_prompt


# ── SEAM 2: the confidence gate ──────────────────────────────────────────────────

def test_low_confidence_retries_and_the_retry_can_succeed():
    llm = FakeLLM([classification(score=0.2), classification(score=0.9), DETAILS])
    result = triage(record(), llm, threshold=0.65)

    assert result.label_source is LabelSource.model_retry
    assert result.category is Category.security
    # The retry used the stricter system prompt, not the original one.
    assert "No explanation" in llm.calls[1]["system"]


def test_unparseable_answer_retries():
    llm = FakeLLM(["I reckon it's a security thing", classification(score=0.9), DETAILS])
    result = triage(record(), llm, threshold=0.65)
    assert result.label_source is LabelSource.model_retry
    assert result.category is Category.security


def test_two_bad_answers_fall_back_and_still_write_a_row():
    """THE most important test in the repo.

    Both attempts fail. We must still produce a result, labelled unclear, marked
    fallback, with the reason recorded. A PR must never vanish silently."""
    llm = FakeLLM(["total nonsense", "still nonsense"])
    result = triage(record(), llm, threshold=0.65)

    assert result.label_source is LabelSource.fallback
    assert result.category is Category.unclear
    assert result.confidence == 0.0
    assert "Could not classify" in result.rationale
    assert len(llm.calls) == 2          # tried twice, then stopped. No third attempt.


def test_model_unsure_twice_falls_back_rather_than_storing_a_guess():
    llm = FakeLLM([classification(score=0.2), classification(score=0.3)])
    result = triage(record(), llm, threshold=0.65)
    assert result.label_source is LabelSource.fallback
    assert "unsure twice" in result.rationale


def test_banana_label_is_not_silently_accepted():
    """An out-of-enum label must trigger the retry path, not become a stored label."""
    llm = FakeLLM([classification(cat="banana", score=0.99), classification(score=0.9), DETAILS])
    result = triage(record(), llm, threshold=0.65)
    assert result.category is Category.security
    assert result.label_source is LabelSource.model_retry


# ── Failure of the model itself, not its output ──────────────────────────────────

class DeadLLM(LLMClient):
    name = "dead"

    def complete(self, system, user, max_tokens=700):
        raise LLMError("connection refused")


def test_unreachable_model_falls_back_instead_of_crashing():
    result = triage(record(), DeadLLM(), threshold=0.65)
    assert result.label_source is LabelSource.fallback
    assert result.category is Category.unclear


def test_details_failure_keeps_the_good_classification():
    """A failed second call must lose only the prose note, never downgrade a label
    we already have in hand."""
    llm = FakeLLM([classification(score=0.9)])       # runs out before DETAILS
    result = triage(record(), llm, threshold=0.65)

    assert result.category is Category.security       # kept
    assert result.label_source is LabelSource.model   # NOT fallback
    assert result.affected_area is None               # only the note was lost
    assert result.llm_calls == 2                      # we still paid for the attempt
    assert len(llm.calls) == 2


def test_unparseable_details_are_counted_but_do_not_downgrade():
    """Dirty JSON on the second call: keep the label, count the call, lose the note."""
    llm = FakeLLM([classification(score=0.9), "sure, authentication I guess"])
    result = triage(record(), llm, threshold=0.65)

    assert result.category is Category.security
    assert result.label_source is LabelSource.model
    assert result.affected_area is None
    assert result.llm_calls == 2


# ── The model being absent must not destroy work ─────────────────────────────────

def test_dead_model_is_reported_as_unavailable():
    """The worker checks this before it consumes anything.

    If a missing model reported itself as available, the worker would consume,
    write fallback rows, and commit the offsets. Committing is the damaging part:
    GitHub does not re-emit a PullRequestEvent, so the pull request would never be
    classified again. Waiting instead leaves the message on the topic.
    """
    assert DeadLLM().available() is False


def test_working_model_is_reported_as_available():
    assert FakeLLM([]).available() is True
