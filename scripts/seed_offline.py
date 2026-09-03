"""Load RECORDED results into the database. No model required.

These are the real output of an earlier live run (see the `model` column on every
row says which model produced them). Nothing here is invented: this is a
recording, not a simulation.

Why it exists: pulling a 2GB model can fail on a slow or restricted network, it
did on the machine this was built on, timing out against Ollama's CDN from inside
Docker. If that happens to whoever runs this, they should still see a working UI
and be able to judge the system, rather than an empty table.

For live results from the actual reasoning loop, use `task seed` instead.
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from triage import store   # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent

INSERT = """
INSERT INTO pr_triage (
    pr_url, repo, pr_number, title, author, files_changed, additions, deletions,
    category, confidence, rationale, affected_area, risk_note, label_source,
    model, llm_calls, latency_ms, evidence, event_created_at
) VALUES (
    %(pr_url)s, %(repo)s, %(pr_number)s, %(title)s, %(author)s, %(files_changed)s,
    %(additions)s, %(deletions)s, %(category)s, %(confidence)s, %(rationale)s,
    %(affected_area)s, %(risk_note)s, %(label_source)s, %(model)s, %(llm_calls)s,
    %(latency_ms)s, %(evidence)s, %(event_created_at)s
)
ON CONFLICT (pr_url) DO NOTHING
"""


def main() -> int:
    """Always exits 0.

    `web` waits for this container to finish before it starts. If seeding could
    fail the build, a missing fixture or a schema change would mean no UI at all
   , strictly worse than an empty table. The UI must be the last thing to fail,
    never the first. So a failure here is loud, and then we get out of the way.
    """
    try:
        rows = json.loads((ROOT / "fixtures/triaged.json").read_text())
        conn = store.connect()

        with conn.cursor() as cur:
            for row in rows:
                row["evidence"] = json.dumps(row.get("evidence") or [])
                cur.execute(INSERT, row)

        print(f"loaded {len(rows)} recorded results (from {rows[0]['model']})")
        print("these are a RECORDING of a real run, not live output, use `task seed` for live")
        print("open http://localhost:8000")
        conn.close()
    except Exception as exc:  # noqa: BLE001 - see docstring
        print("", file=sys.stderr)
        print("#" * 60, file=sys.stderr)
        print(f"# SEEDING FAILED: {exc}", file=sys.stderr)
        print("# The UI will still start, it will just be empty.", file=sys.stderr)
        print("# Retry with:  task seed:offline", file=sys.stderr)
        print("#" * 60, file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
