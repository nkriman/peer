#!/usr/bin/env bash
# PostToolUse hook — auto-format Python files after Edit/Write/MultiEdit.
# Never blocks (exit 0); formatters self-correct.

set -u

cd "${CLAUDE_PROJECT_DIR:-$(pwd)}" || exit 0

INPUT=$(cat)

FILE=$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
if [[ -z "$FILE" || ! -f "$FILE" ]]; then
  exit 0
fi

if [[ "$FILE" != *.py ]]; then
  exit 0
fi

if ! command -v uv >/dev/null 2>&1; then
  exit 0
fi

uv run ruff check --fix --quiet "$FILE" 2>/dev/null || true
uv run ruff format --quiet "$FILE" 2>/dev/null || true

exit 0
