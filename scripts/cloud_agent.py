#!/usr/bin/env python3
"""Start a Cursor cloud agent from sdd/factory.

`main` is the demo. The agent starts at ref `sdd/factory` and is told to
commit on `sdd/factory-<key>` and to open a pull request with base
`sdd/factory`. autoCreatePR stays false: the API would otherwise open a
pull request against the repository default branch, which is `main`.

Needs a Cursor plan, the repo connected in Cursor settings, and CURSOR_API_KEY.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

REPO = "https://github.com/pablogd-hashi/rp-ghtriage"
API = "https://api.cursor.com/v1/agents"


def branch_name(request_id: str) -> str:
    parts = request_id.split("-")
    if len(parts) >= 2 and parts[0] == "RP" and parts[1].isdigit():
        return f"sdd/factory-RP-{parts[1]}"
    return f"sdd/factory-{request_id}"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: cloud_agent.py <request-id>", file=sys.stderr)
        return 2
    key = os.environ.get("CURSOR_API_KEY", "").strip()
    if not key:
        print(
            "CURSOR_API_KEY is not set. Cloud agents need a Cursor plan and "
            "this repo connected in Cursor settings. Local delivery is the default."
        )
        return 2
    request_id = argv[1]
    branch = branch_name(request_id)
    text = (
        f"Run the SDD flow for requests/{request_id}, autonomous mode, "
        "stop at 06-pr. PR base is sdd/factory, never main. "
        f"Commit on branch {branch}. Do not check out, push, merge, rebase, "
        "reset, or open a pull request against main."
    )
    body = {
        "prompt": {"text": text},
        "repos": [{"url": REPO, "startingRef": "sdd/factory"}],
        "autoCreatePR": False,
        "workOnCurrentBranch": False,
        "name": branch[:100],
    }
    request = urllib.request.Request(
        API,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        print(response.read().decode())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
