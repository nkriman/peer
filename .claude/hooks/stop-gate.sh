#!/usr/bin/env bash
# Stop hook — runs at end of every assistant turn.
# Blocks (exit 2) if quality gates fail, forcing the agent to fix before finishing.
#
# Layers, fastest to slowest:
#   1. ruff check       (~ms)
#   2. mypy src/peer    (~s)
#   3. pytest -x -q     (seconds)
#   4. behave @fast     (seconds)
#
# If you need to debug a hook firing, run it manually:
#   bash .claude/hooks/stop-gate.sh

set -u

cd "${CLAUDE_PROJECT_DIR:-$(pwd)}" || exit 0

# Discard stdin (Claude Code passes JSON; we don't need it here).
cat >/dev/null

# Skip if uv unavailable (e.g. fresh checkout before `uv sync`).
if ! command -v uv >/dev/null 2>&1; then
  echo "[stop-gate] uv not found; skipping quality gates" >&2
  exit 0
fi

FAILED=0

# 1. Ruff: lint
if ! uv run ruff check . 2>&1 | tail -20 >&2; then
  echo "[stop-gate] ruff check FAILED — fix lint errors before finishing." >&2
  FAILED=1
fi

# 2. Mypy: types
if ! uv run mypy src/peer --show-error-codes 2>&1 | tail -15 >&2; then
  echo "[stop-gate] mypy FAILED — fix type errors before finishing." >&2
  FAILED=1
fi

# 3. Pytest: fail-fast
if ! uv run pytest -x -q --tb=short 2>&1 | tail -25 >&2; then
  echo "[stop-gate] pytest FAILED — fix tests before finishing (NEVER delete/skip tests to pass)." >&2
  FAILED=1
fi

# 4. BDD @fast (only if features exist)
if [[ -d features ]] && find features -name '*.feature' -type f | grep -q .; then
  if ! uv run behave features/ --tags=@fast --no-capture --no-color 2>&1 | tail -20 >&2; then
    echo "[stop-gate] behave @fast FAILED — fix BDD scenarios before finishing." >&2
    FAILED=1
  fi
fi

if [[ $FAILED -ne 0 ]]; then
  echo "" >&2
  echo "[stop-gate] One or more quality gates failed. Fix and re-run. Do not bypass with --no-verify." >&2
  exit 2
fi

exit 0
