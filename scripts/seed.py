"""Fill the database from the fixtures, so the UI is never empty.

This runs the REAL reasoning loop over saved records — the same code path the
worker uses. Nothing here is faked: the rows you see are genuine model output,
just over PRs captured earlier rather than PRs arriving right now.

Why it exists: PullRequestEvents are roughly 2 in every 100 GitHub events, so a
cold `docker compose up` can sit with an empty table for several minutes. That is
a bad first thirty seconds for someone evaluating this.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from triage import store                                   # noqa: E402
from triage.llm import get_client                          # noqa: E402
from triage.reason import DEFAULT_THRESHOLD, triage        # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
THRESHOLD = float(os.environ.get("CONFIDENCE_THRESHOLD", DEFAULT_THRESHOLD))


def main() -> int:
    records = json.loads((ROOT / "fixtures/enriched.json").read_text())
    client = get_client()
    conn = store.connect()

    print(f"seeding {len(records)} fixtures with {client.name} ...", flush=True)
    for i, record in enumerate(records, 1):
        result = triage(record, client, THRESHOLD)
        store.save(conn, record, result)
        print(f"  [{i:>2}/{len(records)}] {result.category.value:16} "
              f"{result.confidence:.2f} [{result.label_source.value}] "
              f"{record['repo']}#{record['pr_number']}", flush=True)

    conn.close()
    print("\ndone — open http://localhost:8000")
    return 0


if __name__ == "__main__":
    sys.exit(main())
