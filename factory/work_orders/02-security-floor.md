# Security floor

## Goal

A raise-only floor in `triage/reason.py`, next to `should_skip`. It may set the
category to `security`. It must not lower a label. `label_source` stays the four
existing values. The new field is `floor_raised`, threaded with the extend-field
skill. The model is not asked for it.

## Patterns

These patterns were written knowing the fixtures. Say that in the notes.

Patch patterns:

- JWT `verify_exp` disabled (`f001`)
- CORS `*` with credentials (`f006`)
- a hardcoded key (`f012`, `sk_live_...`)
- string-built SQL (`f003`, the deleted concatenation is still in the patch)

After `_extract_details`, a non-security label disagrees with the note when
`affected_area` is `security`, or the note says `sql injection` or
`unauthorized access`.

## Acceptance

- Fixtures shaped like `f001`, `f003`, and `f006` raise even when the model
  says otherwise. `f012` raises on the hardcoded-key pattern.
- A fixture shaped like `f010` (an `x/crypto` version bump) does not raise.
- The floor never lowers `security` to another category.
- Existing fallback tests still prove an unclear row, using a benign patch.
- Eval prints a `floor` row and its false raises. False raises on the twelve
  fixtures are 0.
- `python scripts/gate.py` exits 0.

## Likely files

- `docs/contracts.md`
- `triage/contract.py`
- `triage/prompts.py`
- `triage/reason.py`
- `db/schema.sql`
- `db/migrate.sql`
- `triage/store.py`
- `web.py`
- `tests/test_reason.py`
- `evals/run.py`
- `evals/baseline.json`
