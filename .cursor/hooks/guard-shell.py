#!/usr/bin/env python3
"""Block wiping the compose volumes, and block pushing main."""

from __future__ import annotations

import json
import re
import sys

DENY_DOWN = (
    "docker compose down -v wipes the database volume. "
    "Refused unless a person asked for it in the prompt."
)
DENY_PUSH = "Pushes to main are refused. main is the interview demo."


def main() -> int:
    raw = sys.stdin.read() or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {}
    command = data.get("command") or ""

    wipe = re.search(r"docker(?:-|\s+)compose\s+down\b", command) and re.search(
        r"(?:^|\s)(-v|--volumes)(?:\s|$)", command
    )
    push_main = re.search(r"\bgit\s+push\b", command) and re.search(
        r"(?:^|[\s:/])main(?:\s|$)", command
    )
    if wipe or push_main:
        message = DENY_DOWN if wipe else DENY_PUSH
        json.dump(
            {"permission": "deny", "user_message": message, "agent_message": message},
            sys.stdout,
        )
        return 0

    json.dump({"permission": "allow"}, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
