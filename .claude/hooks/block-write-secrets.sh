#!/usr/bin/env bash
# PreToolUse hook for Write/Edit — block obvious credential patterns and .env writes.

set -u

INPUT=$(cat)

FILE=$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
if [[ -z "$FILE" ]]; then
  exit 0
fi

# Block .env writes (use environment vars or a template instead)
case "$(basename "$FILE")" in
  .env|.env.*|secrets.*|credentials.*)
    # Allow .env.example / .env.template (templates with no secrets)
    case "$(basename "$FILE")" in
      *.example|*.template|*.sample) exit 0 ;;
    esac
    echo "[block-write-secrets] Refusing to write to $FILE. Use a .env.example template instead." >&2
    exit 2
    ;;
esac

# Inspect content for obvious credential patterns
CONTENT=$(printf '%s' "$INPUT" | jq -r '.tool_input.content // .tool_input.new_string // empty' 2>/dev/null)
if [[ -z "$CONTENT" ]]; then
  exit 0
fi

if printf '%s' "$CONTENT" | grep -qE '(sk-ant-[A-Za-z0-9_-]{30,}|sk-[A-Za-z0-9]{32,}|ghp_[A-Za-z0-9]{30,}|AKIA[A-Z0-9]{16})'; then
  echo "[block-write-secrets] Real-looking API key detected in $FILE. Refusing." >&2
  exit 2
fi

exit 0
