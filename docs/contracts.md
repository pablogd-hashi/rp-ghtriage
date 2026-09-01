# Contracts

The shapes each stage promises the next one. **This is my artifact** — the agent writes
code against these, not the other way round. If a shape changes, it changes here first.

Three boundaries matter:

1. What Connect puts on `pr.enriched`
2. What the reasoning loop returns
3. What lands in Postgres

---

## 1. `pr.enriched` — what Connect promises the worker

Connect owns everything up to here: polling, filtering, deduping, fetching the real
content, and bounding its size. The worker is allowed to assume all of this is true.

```json
{
  "event_id":         "58239847362",
  "pr_url":           "https://api.github.com/repos/acme/widgets/pulls/412",
  "html_url":         "https://github.com/acme/widgets/pull/412",
  "repo":             "acme/widgets",
  "pr_number":        412,
  "author":           "some-human",
  "draft":            false,
  "event_created_at": "2026-08-31T09:14:22Z",

  "title":            "bump deps",
  "body":             "routine update",

  "additions":        14,
  "deletions":        3,
  "files_changed":    2,

  "files": [
    {
      "filename":  "src/auth/middleware.py",
      "status":    "modified",
      "additions": 12,
      "deletions": 3,
      "patch":     "@@ -18,7 +18,7 @@ def verify(token):\n-    if not token:\n..."
    }
  ]
}
```

### Guarantees

| Field | Promise |
|---|---|
| `pr_url` | Always present. Unique. The primary key everywhere downstream. |
| `title`, `body` | Present as strings. **May be empty** — plenty of PRs have no description. |
| `files` | A list. **May be empty** if the fetch returned nothing. |
| `patch` | Truncated to ~2 KB per file, ~12 KB total across all files. |
| `event_created_at` | ISO-8601 string, never an epoch number. |

### What never reaches this topic

- Anything that is not a `PullRequestEvent` with `action: opened`
- Anything opened by a bot (`[bot]` suffix, `dependabot`, `renovate`)
- Any event id we have already seen inside the cache TTL
- Anything where **both** enrichment fetches failed → goes to `pr.dlq` instead

The last one is the important promise: **the worker never receives a record with no
content to read.** If we could not fetch the change, we do not reason about it.

---

## 2. What the reasoning loop returns

```json
{
  "category":      "security",
  "confidence":    0.82,
  "rationale":     "Modifies token verification in auth middleware.",
  "evidence_files": ["src/auth/middleware.py"],
  "affected_area": "authentication",
  "risk_note":     "Changes the empty-token branch; test the reject path.",
  "label_source":  "model",
  "llm_calls":     2,
  "latency_ms":    3120
}
```

### Enums — nothing outside these lists is ever written

**`category`**

| Value | Means |
|---|---|
| `security` | Touches auth, secrets, permissions, crypto, input validation |
| `feature` | Adds behaviour a user would notice |
| `refactor` | Changes structure, not behaviour |
| `docs` | Documentation, comments, README only |
| `dependency-bump` | Version changes only |
| `unclear` | We do not know, and we are saying so |

**`label_source`** — how the answer was reached

| Value | Means |
|---|---|
| `model` | First answer, confident enough to keep |
| `model_retry` | First answer was unusable or unsure; the stricter retry worked |
| `fallback` | Both attempts failed. Category is forced to `unclear`, confidence to 0 |
| `skipped` | The model was never called (draft PR, no files, nothing to read) |

### Rules the loop must obey

1. **A model label outside the enum is rejected, not coerced.** `"banana"` does not become
   `unclear` silently — it fails the parse and triggers the retry. Only the *fallback*
   writes `unclear`, and it records that it did.
2. **Every path writes a row.** There is no case where a PR arrives and nothing lands.
   Failure is a value, not an absence.
3. **`affected_area` and `risk_note` are only ever set by the second call**, so they are
   null on `fallback` and `skipped` rows. That is expected, not a bug.
4. **`confidence` is 0.0–1.0.** Anything outside that range fails validation.

---

## 3. Postgres — `pr_triage`

See `db/schema.sql`. Same fields, one row per `pr_url`, written with an UPSERT.

Why UPSERT and not INSERT: the same PR legitimately arrives more than once. Polls overlap,
the dedupe cache dies with its container, and a cold-start model failure should be
correctable by a later, better answer overwriting it.

---

## Where the surprise extension will land

Three places, one edit each:

- **A new field** → here first, then the Connect projection, then the prompt, then the row
- **A new routing rule** (e.g. urgent → its own topic) → the confidence gate in `reason.py`
- **A new skip rule** (e.g. known-bot pattern) → the guard at the top of `reason.py`
