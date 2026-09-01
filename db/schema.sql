-- One row per pull request. Primary key is the PR's API URL, which is stable and
-- unique, so re-processing the same PR updates the row instead of colliding.
--
-- Why an UPSERT rather than an INSERT: the same PR legitimately arrives more than
-- once. Consecutive GitHub polls overlap, the dedupe cache dies with the Connect
-- container, and a cold-start model failure should be fixable by a later, better
-- answer. Writing twice must be safe.
--
-- This file runs ONCE, on an empty volume. Adding a column later does nothing
-- until `task down` (wipes the volume) or you add the same ALTER to migrate.sql
-- and run `task migrate`.

CREATE TABLE IF NOT EXISTS pr_triage (
    pr_url            TEXT PRIMARY KEY,
    repo              TEXT        NOT NULL,
    pr_number         INTEGER     NOT NULL,
    title             TEXT,
    author            TEXT,

    files_changed     INTEGER,
    additions         INTEGER,
    deletions         INTEGER,

    -- What the model decided.
    category          TEXT        NOT NULL,
    confidence        REAL        NOT NULL,
    rationale         TEXT,
    affected_area     TEXT,        -- only filled in by the second, narrower call
    risk_note         TEXT,        -- ditto

    -- How we got there. This column is the reason we can explain a weird row live:
    --   model        first answer, confident enough to keep
    --   model_retry  first answer was unusable or unsure; the stricter retry worked
    --   fallback     both attempts failed; we wrote "unclear" rather than guessing
    --   skipped      never asked the model (draft PR, no files, nothing to read)
    label_source      TEXT        NOT NULL,

    model             TEXT,
    llm_calls         INTEGER     NOT NULL DEFAULT 0,
    latency_ms        INTEGER,
    evidence          JSONB,       -- the filenames the model said it based the call on

    event_created_at  TIMESTAMPTZ, -- when GitHub says the PR was opened
    triaged_at        TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- The web page's only query: newest first, optionally filtered by category.
CREATE INDEX IF NOT EXISTS pr_triage_category_recent
    ON pr_triage (category, triaged_at DESC);
