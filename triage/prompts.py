"""The two prompts. Kept apart from the loop so the wording can change without
touching the control flow, and so a reviewer can read what we actually ask.

Two calls, not one, and they do different jobs:

  CLASSIFY , reads everything, picks one label, says how sure it is.
  DETAILS  , only runs when CLASSIFY was confident. Reads only the files
              CLASSIFY pointed at, and writes the human-facing note.

Splitting them means the expensive, wordy call only happens on records worth
spending it on, and the cheap call stays cheap.
"""

from __future__ import annotations

CLASSIFY_SYSTEM = """\
You classify GitHub pull requests by reading the actual code change.

The title is often wrong or lazy. Trust the diff over the title. A PR titled
"bump deps" that modifies authentication code is a security change, not a
dependency bump.

Answer with ONLY a JSON object, no prose, no markdown fence:

{"category": "<one of: security|feature|refactor|docs|dependency-bump>",
 "confidence": {"score": <0.0-1.0>, "rationale": "<one short sentence>"},
 "evidence_files": ["<the filenames that decided it>"]}

Definitions:
  security         auth, secrets, permissions, crypto, input validation, injection
  feature          adds behaviour a user would notice
  refactor         structure changed, behaviour unchanged
  docs             documentation, comments, README only
  dependency-bump  version numbers only, nothing else

Set score below 0.5 if the diff is too small or ambiguous to tell."""

CLASSIFY_RETRY_SYSTEM = """\
Return ONLY a JSON object. No explanation. No markdown fence. No text before or after.

{"category": "security"|"feature"|"refactor"|"docs"|"dependency-bump",
 "confidence": {"score": 0.0-1.0, "rationale": "one sentence"},
 "evidence_files": ["filename"]}

The category MUST be exactly one of those five strings, lowercase."""

DETAILS_SYSTEM = """\
You write a one-line risk note for an engineer triaging pull requests.

Answer with ONLY a JSON object, no prose:

{"affected_area": "<short noun phrase, e.g. 'authentication', 'billing API'>",
 "risk_note": "<one sentence: what could break, or what to test>"}

Be concrete and specific to this diff. Do not restate the category."""


def _render_files(files: list[dict], include_patches: bool) -> str:
    if not files:
        return "(no files were returned by the enrichment fetch)"

    parts = []
    for f in files:
        header = (
            f"--- {f.get('filename', '?')} "
            f"({f.get('status', '?')}, +{f.get('additions', 0)}/-{f.get('deletions', 0)})"
        )
        patch = f.get("patch") or ""
        if include_patches and patch:
            parts.append(f"{header}\n{patch}")
        else:
            parts.append(header)
    return "\n\n".join(parts)


def classify_user(record: dict, include_patches: bool = True) -> str:
    """Build the first prompt.

    include_patches=False is the ABLATION: the model then sees only what the
    GitHub events feed could have told us, with no fetched content. Used by
    evals/run.py to prove the enrichment is doing work.
    """
    return (
        f"Repository: {record.get('repo', '?')}\n"
        f"Title: {record.get('title') or '(no title)'}\n"
        f"Description: {(record.get('body') or '(none)')[:1500]}\n"
        f"Changed files: {record.get('files_changed', 0)} "
        f"(+{record.get('additions', 0)}/-{record.get('deletions', 0)})\n\n"
        f"{_render_files(record.get('files') or [], include_patches)}"
    )


def details_user(record: dict, evidence_files: list[str]) -> str:
    """Build the second prompt, only the files the first call named."""
    wanted = set(evidence_files)
    files = [f for f in (record.get("files") or []) if f.get("filename") in wanted]
    if not files:
        files = (record.get("files") or [])[:2]   # model named nothing usable

    return (
        f"Repository: {record.get('repo', '?')}\n"
        f"Title: {record.get('title') or '(no title)'}\n\n"
        f"{_render_files(files, include_patches=True)}"
    )
