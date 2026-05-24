#!/usr/bin/env bash
# SessionStart hook — inject identity-core spec at the start of every session.
# Returns JSON additionalContext that Claude Code adds to the system prompt.

set -u

cd "${CLAUDE_PROJECT_DIR:-$(pwd)}" || exit 0

cat >/dev/null  # drain stdin

IDENTITY_FILE=".claude/identity-core.md"
if [[ ! -f "$IDENTITY_FILE" ]]; then
  exit 0
fi

SPEC=$(cat "$IDENTITY_FILE")

# List active OpenSpec changes for context
ACTIVE_CHANGES=""
if [[ -d openspec/changes ]]; then
  ACTIVE_CHANGES=$(find openspec/changes -maxdepth 1 -mindepth 1 -type d 2>/dev/null | xargs -n1 basename 2>/dev/null | sort)
fi

EXTRA=""
if [[ -n "$ACTIVE_CHANGES" ]]; then
  EXTRA=$'\n\n## Active OpenSpec changes\n'"$ACTIVE_CHANGES"
fi

jq -n --arg spec "$SPEC$EXTRA" '{
  hookSpecificOutput: {
    hookEventName: "SessionStart",
    additionalContext: $spec
  }
}'
