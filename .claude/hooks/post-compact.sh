#!/usr/bin/env bash
# PostCompact hook — re-inject identity-core spec after compaction.
# Compaction is the highest-risk moment for spec drift. This hook re-grounds the agent.

set -u

cd "${CLAUDE_PROJECT_DIR:-$(pwd)}" || exit 0

cat >/dev/null  # drain stdin

IDENTITY_FILE=".claude/identity-core.md"
if [[ ! -f "$IDENTITY_FILE" ]]; then
  exit 0
fi

SPEC=$(cat "$IDENTITY_FILE")
PREAMBLE="[POST-COMPACT RE-GROUNDING] Context was just compacted. The invariants below are load-bearing — re-read them before continuing."

jq -n --arg ctx "$PREAMBLE"$'\n\n'"$SPEC" '{
  hookSpecificOutput: {
    hookEventName: "PostCompact",
    additionalContext: $ctx
  }
}'
