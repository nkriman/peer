#!/usr/bin/env python3
"""UserPromptSubmit hook — re-inject identity-core every N user prompts.

Prevents long-session spec drift. Counter is per session_id, persisted under
.claude/session-state/. After every Nth prompt, returns additionalContext that
re-grounds the agent in the load-bearing invariants.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REGROUND_EVERY = 10  # turns

def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0

    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
    session_id = data.get("session_id", "unknown")

    state_dir = project_dir / ".claude" / "session-state"
    state_dir.mkdir(parents=True, exist_ok=True)
    counter_file = state_dir / f"turn-count-{session_id}.txt"

    try:
        count = int(counter_file.read_text().strip())
    except (FileNotFoundError, ValueError):
        count = 0
    count += 1
    counter_file.write_text(str(count))

    if count % REGROUND_EVERY != 0:
        return 0

    identity = project_dir / ".claude" / "identity-core.md"
    if not identity.exists():
        return 0

    spec = identity.read_text()
    preamble = (
        f"[PERIODIC RE-GROUNDING — turn {count}] "
        "These invariants are load-bearing. Re-read before responding."
    )

    out = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": f"{preamble}\n\n{spec}",
        }
    }
    json.dump(out, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
