#!/usr/bin/env bash
# PreToolUse hook — block dangerous Bash commands.
# Exits 2 (hard block) when a forbidden pattern is detected.

set -u

INPUT=$(cat)

CMD=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
if [[ -z "$CMD" ]]; then
  exit 0
fi

# Bypass quality gates
if echo "$CMD" | grep -qE '(^|[^a-zA-Z_])--no-verify([^a-zA-Z_]|$)'; then
  echo "[block-dangerous] --no-verify is forbidden by CLAUDE.md. Fix the underlying hook failure instead." >&2
  exit 2
fi
if echo "$CMD" | grep -qE '(^|\s)SKIP=[a-zA-Z0-9,_-]+\s+(git|pre-commit)'; then
  echo "[block-dangerous] SKIP= bypassing pre-commit is forbidden. Fix the underlying check failure." >&2
  exit 2
fi

# Force push to main/master
if echo "$CMD" | grep -qE 'git push\s+(.*\s)?(-f|--force(-with-lease)?)\b.*\b(main|master)\b'; then
  echo "[block-dangerous] Force push to main/master is blocked. Ask the user before proceeding." >&2
  exit 2
fi
if echo "$CMD" | grep -qE 'git push\s+(.*\s)?(main|master)\b.*\s(-f|--force(-with-lease)?)\b'; then
  echo "[block-dangerous] Force push to main/master is blocked. Ask the user before proceeding." >&2
  exit 2
fi

# Destructive resets (allow if explicitly asked; this is a soft guard)
if echo "$CMD" | grep -qE 'git\s+(reset\s+--hard|clean\s+-fd|checkout\s+\.)\b'; then
  echo "[block-dangerous] Destructive git op detected: '$CMD'. Confirm with the user before running." >&2
  exit 2
fi

# Bypass test/coverage by deleting tests
if echo "$CMD" | grep -qE '\brm\b.*\btests?/'; then
  echo "[block-dangerous] Removing tests is forbidden. If a test is wrong, fix it explicitly with the user's approval." >&2
  exit 2
fi

exit 0
