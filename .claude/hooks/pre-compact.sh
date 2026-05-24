#!/usr/bin/env bash
# PreCompact hook — snapshot key session state to a file before compaction destroys it.

set -u

cd "${CLAUDE_PROJECT_DIR:-$(pwd)}" || exit 0

INPUT=$(cat)

SESSION_ID=$(printf '%s' "$INPUT" | jq -r '.session_id // "unknown"' 2>/dev/null)
TRANSCRIPT=$(printf '%s' "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null)

SNAPSHOT_DIR=".claude/session-state"
mkdir -p "$SNAPSHOT_DIR"
SNAPSHOT_FILE="$SNAPSHOT_DIR/pre-compact-$SESSION_ID.md"

{
  echo "# Pre-compact snapshot — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo
  echo "## Git state"
  echo '```'
  git -C "${CLAUDE_PROJECT_DIR:-.}" status --short 2>/dev/null | head -30
  echo '```'
  echo
  echo "## Recent commits"
  echo '```'
  git -C "${CLAUDE_PROJECT_DIR:-.}" log --oneline -10 2>/dev/null
  echo '```'

  if [[ -n "$TRANSCRIPT" && -f "$TRANSCRIPT" ]]; then
    echo
    echo "## Tail of transcript (last 60 lines, decisions only)"
    echo '```'
    grep -iE '(decision|chose|switched|invariant|REASON:|because)' "$TRANSCRIPT" 2>/dev/null | tail -60
    echo '```'
  fi
} > "$SNAPSHOT_FILE" 2>/dev/null

exit 0
