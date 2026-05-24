# peer — Project Instructions for AI Agents

`peer` is an opinionated framework for building AI PR-review agents with evaluation built in. The repo is a long-running, agent-driven project: quality must hold across many sessions, not just one PR.

This file is the contract. Every agent session reads it. If you find yourself disagreeing with a rule here, stop and ask the user — do not silently route around it.

---

## Quality Gates (NON-NEGOTIABLE)

Every code change must pass, in order, before you finish a turn:

1. `uv run ruff check . --fix`
2. `uv run ruff format .`
3. `uv run mypy src/peer`
4. `uv run pytest -x -q`
5. `uv run behave features/ --tags=@fast --no-capture` (when feature files exist)

The `Stop` hook enforces (3)–(5). You cannot end a turn while any of them fail.

**Forbidden bypasses:**

- NEVER use `git commit --no-verify`
- NEVER use `SKIP=` to bypass pre-commit hooks
- NEVER use `pytest -k` to silently exclude failing tests
- NEVER delete or `@skip` a test to "fix" coverage or a failure
- NEVER modify a test's assertion to make it pass — fix the code instead
- NEVER add `# type: ignore` without a comment explaining *why* the type checker is wrong

If a hook fails, fix the underlying issue. If you genuinely cannot, surface the blocker to the user — do not bypass.

---

## Architecture Invariants

These shape every change. Violating them is a design break, not a style issue.

- **Protocols over inheritance.** Public extension points are `Protocol`s (`peer.dataset.types`, `peer.eval.EvalMetric`, `peer.reviewers.Reviewer`). Users override by *constructing*, not subclassing.
- **Storage is injected.** No module imports a storage backend directly. `Curator.storage` is optional and passed in.
- **Curator is preview-safe.** Curation must run end-to-end with `storage=None` (preview mode). No I/O sneaks into the curation pipeline.
- **Pure functions in `peer.eval.metrics`.** Metrics take `(results, dataset)` and return a `MetricResult`. No file reads, no network, no side effects.
- **One concept per module.** `agent.py` reviews PRs, `curate.py` builds datasets, `eval/` grades agents. Resist cross-pollination.

---

## Behavioral Driven Development

BDD scenarios in `features/` are executable specs. They are the source of truth for end-user behavior; the Python tests in `tests/` verify implementation details.

When implementing a new user-facing capability:

1. Write the Gherkin scenario in `features/<area>.feature` first.
2. Commit the failing feature file.
3. Implement until `behave features/<area>.feature` is green.
4. Tag fast scenarios `@fast` (run on every Stop hook). Tag slow ones `@slow` (CI only).

Anti-patterns to avoid in Gherkin:

- Vague `Then` steps ("Then the result is correct") — assert specific observable state.
- UI/HTTP-level steps in domain scenarios — describe behavior, not transport.
- Multi-behavior scenarios — one scenario, one behavior.

See `.claude/skills/bdd-standards/SKILL.md` for full guidelines (auto-loaded when writing features).

---

## Long-Running Session Discipline

This project's work spans many sessions. The agent must not let quality drift across them.

- The `SessionStart` hook re-loads `.claude/identity-core.md` (the load-bearing invariants).
- The `PostCompact` hook re-injects the same context — compaction is the highest-risk moment for spec drift.
- A periodic re-grounding hook runs every 10 user prompts. If you see a "PERIODIC RE-GROUNDING" line in context, treat it as fresh ground truth.
- Run `/compact` proactively at phase boundaries (after a feature lands, before starting a new area) — do not wait for the context to fill.

When you finish a logical phase, record it in `openspec/changes/<change-id>/` per the OpenSpec workflow already in use.

---

## Doing Tasks

- Use `bd` for issue tracking (`bd ready`, `bd show`, `bd close`). Do NOT use TodoWrite/TaskCreate/markdown TODO lists.
- Prefer editing existing files to creating new ones.
- Default to writing no comments — only the *why* when non-obvious.
- Never commit unless the user explicitly asks.
- Never push unless the user explicitly asks. `bd dolt push && git push` is the session-close ritual, but only when the user signals end-of-session.

---

## Build & Test

```bash
# Setup (one-time)
uv sync --extra dev
uv run pre-commit install

# Lint + format
uv run ruff check . --fix
uv run ruff format .

# Type check
uv run mypy src/peer

# Tests
uv run pytest -x -q                          # unit tests
uv run behave features/ --tags=@fast         # fast BDD scenarios
uv run behave features/                      # all BDD scenarios
uv run pytest --cov=src/peer --cov-fail-under=80  # coverage gate

# The whole thing
uv run pre-commit run --all-files
```


<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:ca08a54f -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

## Session Completion

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd dolt push
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
<!-- END BEADS INTEGRATION -->
