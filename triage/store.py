"""Writing results to Postgres. One statement, one reason it is an UPSERT."""

from __future__ import annotations

import json
import os

import psycopg2
import psycopg2.extras

from .contract import TriageResult

# ON CONFLICT, not INSERT, because the same PR legitimately arrives more than once:
#   - consecutive GitHub polls overlap
#   - Connect's dedupe cache is in-memory and dies with its container
#   - a cold-start model failure should be correctable by a later, better answer
# Writing twice has to be safe, and the second write wins.
#
# The cost of that rule: it cuts both ways. A later run with a broken or missing model
# overwrites a good row with a fallback. Last-write-wins buys cold-start recovery and
# pays for it with the risk of losing a better answer.
#
# For a demo, recovery is worth more. For a customer, the opposite: only overwrite when
# the new answer is at least as good, comparing label_source and confidence before the
# UPDATE fires.
UPSERT = """
INSERT INTO pr_triage (
    pr_url, repo, pr_number, title, author,
    files_changed, additions, deletions,
    category, confidence, rationale, affected_area, risk_note,
    label_source, model, llm_calls, latency_ms, evidence, event_created_at
) VALUES (
    %(pr_url)s, %(repo)s, %(pr_number)s, %(title)s, %(author)s,
    %(files_changed)s, %(additions)s, %(deletions)s,
    %(category)s, %(confidence)s, %(rationale)s, %(affected_area)s, %(risk_note)s,
    %(label_source)s, %(model)s, %(llm_calls)s, %(latency_ms)s, %(evidence)s, %(event_created_at)s
)
ON CONFLICT (pr_url) DO UPDATE SET
    title            = EXCLUDED.title,
    category         = EXCLUDED.category,
    confidence       = EXCLUDED.confidence,
    rationale        = EXCLUDED.rationale,
    affected_area    = EXCLUDED.affected_area,
    risk_note        = EXCLUDED.risk_note,
    label_source     = EXCLUDED.label_source,
    model            = EXCLUDED.model,
    llm_calls        = EXCLUDED.llm_calls,
    latency_ms       = EXCLUDED.latency_ms,
    evidence         = EXCLUDED.evidence,
    triaged_at       = now()
"""


def dsn() -> str:
    return os.environ.get("POSTGRES_DSN", "postgresql://triage:triage@postgres:5432/triage")


def connect(retries: int = 30):
    """Connect, waiting for Postgres to accept us. The compose healthcheck should
    make this unnecessary, but a worker that crash-loops on startup is a bad demo."""
    import time
    last = None
    for _ in range(retries):
        try:
            conn = psycopg2.connect(dsn())
            conn.autocommit = True
            return conn
        except psycopg2.OperationalError as exc:
            last = exc
            time.sleep(2)
    raise RuntimeError(f"could not reach postgres: {last}")


def row_from(record: dict, result: TriageResult) -> dict:
    return {
        "pr_url": record["pr_url"],
        "repo": record.get("repo", ""),
        "pr_number": record.get("pr_number", 0),
        "title": record.get("title"),
        "author": record.get("author"),
        "files_changed": record.get("files_changed"),
        "additions": record.get("additions"),
        "deletions": record.get("deletions"),
        "category": result.category.value,
        "confidence": result.confidence,
        "rationale": result.rationale,
        "affected_area": result.affected_area,
        "risk_note": result.risk_note,
        "label_source": result.label_source.value,
        "model": result.model,
        "llm_calls": result.llm_calls,
        "latency_ms": result.latency_ms,
        "evidence": json.dumps(result.evidence_files),
        "event_created_at": record.get("event_created_at"),
    }


def save(conn, record: dict, result: TriageResult) -> None:
    with conn.cursor() as cur:
        cur.execute(UPSERT, row_from(record, result))


def recent(conn, category: str | None = None, limit: int = 100) -> list[dict]:
    """What the web page shows."""
    sql = "SELECT * FROM pr_triage"
    params: list = []
    if category:
        sql += " WHERE category = %s"
        params.append(category)
    sql += " ORDER BY triaged_at DESC LIMIT %s"
    params.append(limit)

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def counts_by_category(conn) -> dict[str, int]:
    with conn.cursor() as cur:
        cur.execute("SELECT category, count(*) FROM pr_triage GROUP BY category")
        return {row[0]: row[1] for row in cur.fetchall()}
