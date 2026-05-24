# peer — Identity Core

You are working on `peer`, a framework for building AI PR-review agents with built-in evaluation. This file is re-injected at `SessionStart` and `PostCompact`. Treat it as load-bearing.

## Non-negotiable rules

1. Every code change must pass: `ruff check`, `ruff format`, `mypy src/peer`, `pytest -x`, `behave --tags=@fast`.
2. NEVER bypass hooks (`--no-verify`, `SKIP=`, deleting tests). Fix the underlying issue.
3. NEVER add `# type: ignore` without a comment explaining why the checker is wrong.
4. NEVER subclass to extend `peer` internals — override by constructing with a `Protocol` impl.
5. `Curator` must run with `storage=None` (preview mode). No I/O leaks into curation.

## Architecture invariants

- Public extension points are `Protocol`s; users override by *constructing*, not subclassing.
- Storage is injected. No module imports a storage backend directly.
- Metrics in `peer.eval.metrics` are pure functions of `(results, dataset)`.
- Modules have one concept: `agent.py` reviews, `curate.py` builds datasets, `eval/` grades.

## BDD discipline

- Features in `features/` are executable specs. Gherkin scenarios are the source of truth for end-user behavior.
- Tag fast scenarios `@fast` (Stop hook), heavy ones `@slow` (CI only).
- One scenario, one behavior. Assert specific observable state, not "the result is correct".

## Workflow

- `bd` for issue tracking — NEVER `TodoWrite`/`TaskCreate`/markdown TODOs.
- Never commit or push unless the user explicitly asks.
- Run `/compact` proactively at phase boundaries, not at context exhaustion.

## Current focus

Track active OpenSpec changes in `openspec/changes/`. The most recent ones are the live priorities; archived ones are history.
