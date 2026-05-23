# Reverse-engineering The-PR-Agent/pr-agent — what peer should borrow

**Source:** [github.com/The-PR-Agent/pr-agent](https://github.com/The-PR-Agent/pr-agent) (Apache 2.0, 11.3k stars, ~100MB Python). Formerly Codium PR-Agent / Qodo. The OG open-source PR reviewer. Updated daily.

## TL;DR

PR-Agent has shipped, in production, almost every feature peer is currently designing:
- Configurable per-repo settings via TOML (`.pr_agent.toml`)
- Three-tier settings (global → repo → wiki)
- Per-tool `extra_instructions` plain-English overrides
- File-level + repo-level + PR-level ignore patterns
- Dynamic context window extension (smarter than peer's fixed ±20)
- Custom `__new hunk__` / `__old hunk__` diff format with explicit line numbers
- Jinja2-templated TOML prompts (huge flexibility win over hardcoded Python strings)
- YAML structured output (works across providers without per-SDK tool-call shape)
- Multi-model retry with fallback
- Incremental review (`-i`): only re-review new commits since last review
- `num_max_findings` cap (default 3) — explicit noise control
- `large_patch_policy = "clip"|"skip"` — graceful over-size handling
- `KeyIssuesComponentLink` schema with `issue_header` ("Possible Bug", etc.) + `start_line`/`end_line`
- LiteLLM-based AI handler that supports every major provider

And their **reviewer prompt is materially better-calibrated than peer's**.

Most of what peer's 5 in-flight changes (`eval-metrics-v01` / `peer-config-v01` / `linter-context-v01` / `patch-suggestions-v01` / `benchmark-v01`) propose, PR-Agent already implements differently. Many of their patterns are directly portable into peer with small adjustments.

This doc lists what to **borrow as-is**, what to **borrow with modifications**, and what to **deliberately not adopt** for peer.

## Architecture map (what's where)

```
pr-agent/
  pr_agent/
    cli.py                       — entry point
    config_loader.py             — config layering (global / repo / wiki)
    agent/                       — orchestrator base
    tools/                       — one .py per command
      pr_reviewer.py             — the /review command (22kb)
      pr_code_suggestions.py     — the /improve command (54kb)
      pr_description.py          — the /describe command (44kb)
      pr_questions.py            — the /ask command
      pr_add_docs.py             — auto-docstring
      pr_update_changelog.py
      pr_similar_issue.py
      ticket_pr_compliance_check.py — Jira/issue compliance
    algo/                        — shared utilities
      ai_handlers/               — LiteLLM-based provider dispatch
      pr_processing.py           — diff compression, dynamic context (26kb)
      token_handler.py           — Anthropic accurate counting + tiktoken
      git_patch_processing.py    — patch parsing (22kb)
      language_handler.py
      file_filter.py
    git_providers/               — GitHub / GitLab / Bitbucket / Azure DevOps abstraction
    identity_providers/
    secret_providers/
    log/
    servers/                     — webhook receivers
    settings/                    — TOML config + TOML prompts (Jinja2)
      configuration.toml         — master config (14kb)
      pr_reviewer_prompts.toml   — reviewer prompt template (14kb)
      pr_description_prompts.toml
      pr_code_suggestions...     — inline in the .py (not a .toml)
      ignore.toml                — glob / regex ignore patterns
      generated_code_ignore.toml — per-tech-stack generated-code patterns
      custom_labels.toml
      language_extensions.toml   — Python/JS/Go/Java/... file ext maps
  .pr_agent.toml                 — root example config showing user setup
```

## What to borrow as-is

### 1. The diff format with `__new hunk__` / `__old hunk__` + numbered lines

Their prompt presents the diff like this:

```
## File: 'src/file1.py'

@@ ... @@ def func1():
__new hunk__
11  unchanged code line0
12  unchanged code line1
13 +new code line2 added
14  unchanged code line3
__old hunk__
 unchanged code line0
 unchanged code line1
-old code line2 removed
 unchanged code line3
```

**Why this matters for peer:** earlier in this session, peer hallucinated line 442 as the location of the `is_settings` check when it was actually line 444 — the kind of off-by-2 error that happens because the LLM is counting hunks by hand. Explicit numbered new-file lines make it impossible to miscount.

**Action:** swap peer's current "raw unified diff inside ```diff fences" format for this `__new hunk__` style with new-file line numbers prepended.

Affects: `src/peer/prompts.py:format_prompt`. ~30 lines of change.

### 2. The "Determining what to flag" + "Constructing comments" prompt sections

Direct quote from `pr_reviewer_prompts.toml`:

> Determining what to flag:
> - For clear bugs and security issues, be thorough. Do not skip a genuine problem just because the trigger scenario is narrow.
> - For lower-severity concerns, be certain before flagging. If you cannot confidently explain why something is a problem with a concrete scenario, do not flag it.
> - Each issue must be discrete and actionable, not a vague concern about the codebase in general.
> - Do not speculate that a change might break other code unless you can identify the specific affected code path from the diff context.
> - Do not flag intentional design choices or stylistic preferences unless they introduce a clear defect.
> - When confidence is limited but the potential impact is high (e.g., data loss, security), report it with an explicit note on what remains uncertain. Otherwise, prefer not reporting over guessing.
>
> Constructing comments:
> - Be direct about why something is a problem and the realistic scenario where it manifests.
> - Communicate severity accurately. Do not overstate impact. If an issue only arises under specific inputs or environments, say so upfront.
> - Keep each issue description concise. Write so the reader grasps the point immediately without close reading.
> - Use a matter-of-fact, helpful tone. Avoid accusatory language, excessive praise, or filler phrases like 'Great job', 'Thanks for'.

This is **better than peer's current calibration prompt**. The "if you cannot confidently explain why something is a problem with a concrete scenario, do not flag it" line, in particular, addresses the hallucinated-rationale issue we saw in peer's output (line 442 in PR 7677, the speculative "could be expensive for large extras" comment).

**Action:** lift these two sections directly into `DEFAULT_SYSTEM_PROMPT` in `src/peer/prompts.py`. Apache 2.0 → MIT is compatible; cite attribution in the file header.

Affects: `src/peer/prompts.py`. ~20 lines.

### 3. `num_max_findings = 3` cap

Default cap on number of findings per PR. **Materially different from peer's current "agent decides how many".** Forces prioritization at prompt time.

**Action:** add `num_max_findings: int = 5` (slightly more permissive default than PR-Agent) to `Agent.__init__`; inject into the prompt as a hard limit; validate in `_validate_comments` by truncating extras and logging the drops.

Affects: `src/peer/agent.py`, `src/peer/prompts.py`. ~15 lines.

### 4. File-level ignore patterns (`ignore.toml`, `generated_code_ignore.toml`)

Their `generated_code_ignore.toml` lists 30+ generated-code patterns per tech stack: protobuf, OpenAPI/Swagger, GraphQL codegen, gRPC, Go generators, etc. Auto-skip in the diff fetcher.

**Action:** ship `dataset/reference/peer.yaml.example`'s rules section with these patterns baked in. Also add a `peer.config.IgnoreConfig` schema in `peer-config-v01` with glob+regex+generated-code patterns. Apply BEFORE codebase context extraction — saves tokens AND avoids wasting LLM attention on auto-generated noise.

Affects: extends `peer-config-v01` scope. ~50 lines + the example data.

### 5. `large_patch_policy = "clip" | "skip"` graceful over-size handling

When a single hunk exceeds the patch budget, PR-Agent either clips it (truncates) or skips the file. peer currently raises `ContextTooLarge` and aborts. Their approach lets the review proceed with partial context.

**Action:** add `oversize_hunk_policy = "clip"` (default) to `Agent` config. On oversize, truncate the hunk + log a WARNING + add a note to the prompt that this file was clipped. Apply at `context.gather()` time.

Affects: `src/peer/context.py`. ~20 lines.

## What to borrow with modifications

### 6. Jinja2-templated TOML prompts

Their entire prompt system uses TOML files with Jinja2 templating:

```toml
[pr_review_prompt]
system="""You are PR-Reviewer...
{%- if require_security_review %}
... security-specific instructions ...
{%- endif %}
"""
```

Lets users override prompts without touching Python, and lets the system conditionally include sections based on config flags.

**For peer:** the win is twofold — (a) users can ship custom prompts per team without forking peer; (b) we can `{% if codebase_context %}...{% endif %}` to conditionally include sections. Combined with `peer-config-v01`'s per-path conventions, this is the right pattern.

**Trade-off:** adds Jinja2 dependency. It's small (~200KB), Python's de facto templating engine, MIT-licensed. Worth it.

**Action:** in a follow-on change (call it `peer-prompts-v01`), refactor `src/peer/prompts.py` from Python f-strings to Jinja2-templated `.txt` or `.j2` files under `src/peer/templates/`. Update `Agent` to load + render templates with a Jinja2 environment. Keep the current Python-string fallback for back-compat.

Not a v0.2 blocker — current hardcoded strings work. But the architectural debt grows if we don't refactor before adding more conditional sections.

### 7. `extra_instructions` per-tool free-form field

PR-Agent's config has `extra_instructions = ""` on every tool. It's a free-form string injected into the prompt. Lets users tweak behavior without writing a full conventions doc.

**For peer:** add `extra_instructions: Optional[str] = None` to `Agent` and as a field in `.peer.yaml`. Smaller scope than `team_conventions` — for the "two-sentence tweak" use case rather than the "shared style guide" use case.

**Action:** extend `peer-config-v01`'s schema with `agent.extra_instructions: str | None`. Surface in the prompt as a short labeled section.

### 8. YAML structured output (with Pydantic-style schema in the prompt)

PR-Agent's reviewer prompt defines its output schema inside the system prompt as Pydantic-style classes (visible in the rendered prompt), and asks the model for YAML. They then `load_yaml(...)` the response. The model emits something like:

```yaml
key_issues_to_review:
  - relevant_file: src/foo.py
    issue_header: Possible Bug
    issue_content: ...
    start_line: 12
    end_line: 14
security_concerns: No
```

**Trade-off vs tool calling:**
- Tool calling (peer's current approach): stricter; per-provider; more reliable but provider-locked
- YAML output (PR-Agent): portable across providers (works for OpenAI, Anthropic, Gemini, local models with no changes); slightly less reliable; needs robust YAML parsing

**For peer:** keep tool calling as the default for Claude/OpenAI (more reliable), but add YAML-output mode as an alternative for non-tool-calling models. Goes in a future change (`reviewer-yaml-mode-v01` or similar). Not urgent.

### 9. `issue_header` field + better severity model

PR-Agent's `KeyIssuesComponentLink` has `issue_header: str` ("Possible Bug", "Performance Concern", etc.) — a short categorical label SEPARATE from severity. Their schema also has `start_line`/`end_line` (a range), not just `line`.

peer currently has only `severity`. Adding `issue_header` would give us a coarse category surface that's easier to filter / group than a free-form body.

**Action:** in `patch-suggestions-v01` or a small new change, add `Comment.issue_header: Optional[str] = None` and `Comment.end_line: Optional[int] = None`. Update tool schema accordingly. Don't make either required (keeps back-compat).

### 10. Dynamic context extension to function/class boundary

`allow_dynamic_context=true` + `max_extra_lines_before_dynamic_context=10` extends the surrounding context window until it hits an enclosing function or class definition. Smarter than peer's fixed ±20.

**For peer:** we already have tree-sitter symbol extraction (codebase_context.py). The same machinery could find the enclosing function/class span and use it as the surrounding-code window instead of ±20 raw lines.

**Action:** extend `gather_codebase_context` to optionally produce a "smart surrounding-code window" using tree-sitter spans. Wire into `Context.hunks[*].surrounding_code` as a replacement for the fixed window. Save tokens; better semantic boundaries.

Defer to a follow-on; not in any current change.

### 11. Incremental review (only review new commits since last)

PR-Agent's `-i` flag tracks the last reviewed commit and only re-reviews new ones. Massive cost saver on back-and-forth PRs.

**For peer:** would need a small state store (per-PR commit-SHA cache). Worth the build for production use. Defer to a `incremental-review-v01` change after current 5 land.

### 12. Multi-model retry with fallback

`retry_with_fallback_models` tries primary model, falls back to secondary (`fallback_models=["gpt-5.4-mini"]` in their config). Resilience against rate limits / outages.

**Action:** add `Agent(model=..., fallback_models=[...])` parameter. On rate-limit or transient errors, fall through to fallback. Small change.

## What to deliberately NOT adopt

### LiteLLM as the AI handler

PR-Agent uses LiteLLM as a unified-provider abstraction. ~50MB transitively, supports every model imaginable. peer's per-provider SDKs (anthropic + openai) are smaller and cleaner.

**Reason to skip:** peer's value isn't "supports 50 LLM providers" — it's the framework / eval loop. LiteLLM adds bloat and a layer of abstraction we don't need.

### Multi-tool / multi-command architecture (`/review` `/improve` `/describe` `/ask` ...)

PR-Agent has 14+ tools each with its own command. peer is one command (`peer review`) plus dataset/eval/benchmark commands.

**Reason to skip:** scope expansion. The eval framework is peer's value; adding `/improve` and `/describe` competitors is product expansion. Keep peer focused.

### Three-tier config (global → repo → wiki)

PR-Agent supports loading config from global file + repo file + wiki page (yes, GitHub wiki). Useful for SaaS deploys with shared org-level config.

**Reason to skip for v0.1:** repo-level `.peer.yaml` covers 95% of the use case. Global + wiki tiers are deployment-specific features that bloat the v0.1 schema. Defer to a `peer-config-v02` if/when a real user asks.

### Full `git_providers/` abstraction (GitHub + GitLab + Bitbucket + Azure DevOps)

PR-Agent abstracts over every git provider with full feature parity. peer is GitHub-only via `gh` CLI.

**Reason to skip:** users today are 95% on GitHub. The abstraction adds significant code surface for minimal marginal value. Defer until a real user is on GitLab.

### Auto-publish to GitHub (`publish_comment`, `publish_persistent_comment`)

PR-Agent's CLI auto-posts the review as a GitHub PR comment. peer is read-only (prints to stdout).

**Reason to skip:** read-only is intentional for v0.1. Auto-posting is a feature for the eventual `peer post-review` subcommand; lower priority than making the review itself better.

### Their full custom-labels / auto-approve / score-threshold system

PR-Agent has `enable_review_labels_security`, `enable_auto_approval`, `suggestions_score_threshold`, etc. — features for production teams running the bot continuously.

**Reason to skip:** product-bloat for v0.1. Focus is on the framework + reviewer quality, not on every operational knob.

## Concrete implementation impact on the 5 in-flight changes

### eval-metrics-v01 (no architectural impact)

Already designed correctly; PR-Agent doesn't change anything in this change. Implement as designed.

### peer-config-v01 (extend scope)

Add to the spec:
- `agent.extra_instructions: str | None` field (per Decision 7 above)
- `ignore:` top-level section: `glob: list[str]`, `regex: list[str]`, `generated_code: list[str]` patterns (per Decision 4)
- A `generated_code_patterns_default` constant in `src/peer/config.py` with PR-Agent's per-tech-stack patterns vendored

Schema change is small; example file gets richer.

### linter-context-v01 (no impact)

PR-Agent doesn't use linters per se (its prompt does the linting); linter-context-v01 is novel to peer. Implement as designed.

### patch-suggestions-v01 (extend scope)

Add to the spec:
- `Comment.issue_header: Optional[str]` — short categorical label
- `Comment.end_line: Optional[int]` — line range (PR-Agent's `start_line`/`end_line` pattern)

Schema changes are additive and back-compat. Tool schema gets two more optional fields.

### benchmark-v01 (no impact)

No PR-Agent influence here; benchmark-v01 is about the published dataset comparison.

## Prompt-engineering wins to land FIRST (smallest, highest impact)

Two changes worth doing before the larger ones — both are ~30-50 line edits with measurable downstream impact:

### PROMPT-WIN-1: Adopt PR-Agent's calibration language

Lift "Determining what to flag" + "Constructing comments" sections into `DEFAULT_SYSTEM_PROMPT`. Expected impact:
- Reduce hallucinated rationale (the line-442 issue)
- Reduce speculative low-confidence flags ("could be expensive for large extras")
- Improve severity calibration (the +0.75 over-severing issue)

Verifiable: re-run eval against v2 dataset; expect `severity_calibration` to move toward 0, `precision_per_severity` to lift on lower tiers, novel-but-noisy comment rate to drop.

### PROMPT-WIN-2: Adopt `__new hunk__`/`__old hunk__` numbered diff format

Replace peer's current ```diff fenced format in `format_prompt` with PR-Agent's structured format. Expected impact:
- Eliminate the line-number drift errors we saw (peer cited line 442 when truth was 444)
- Make `start_line`/`end_line` references in the agent's output mechanically correct

Verifiable: the PR 7677 case (and similar) should produce exact line citations after this change.

Both fit in a small new change — let's call it **`prompt-quality-v01`** — and should land BEFORE any of the 5 currently-in-flight changes are implemented, because they affect every downstream eval number.

## Net recommendation

1. **Land `prompt-quality-v01` first** (~1 hour total): lift PR-Agent's calibration language + adopt their diff format. Re-eval; capture new headline numbers.
2. **Implement `eval-metrics-v01` next**: makes those new numbers comparable to the industry.
3. **Extend `peer-config-v01` scope** to include `extra_instructions` + `ignore` patterns (small additions to the existing spec).
4. **Extend `patch-suggestions-v01` scope** to include `issue_header` + `end_line` fields.
5. **Implement everything else in the order already planned.**

Net deltas to the OpenSpec changes: small extensions to two specs, plus one new prompt-only change. ~30 minutes of openspec writing to capture; implementation effort grows by maybe 2-3 hours total.

## Sources

- [The-PR-Agent/pr-agent on GitHub](https://github.com/The-PR-Agent/pr-agent) (Apache 2.0)
- [pr_reviewer_prompts.toml](https://github.com/The-PR-Agent/pr-agent/blob/main/pr_agent/settings/pr_reviewer_prompts.toml) — the reviewer prompt
- [configuration.toml](https://github.com/The-PR-Agent/pr-agent/blob/main/pr_agent/settings/configuration.toml) — full config schema
- [token_handler.py](https://github.com/The-PR-Agent/pr-agent/blob/main/pr_agent/algo/token_handler.py) — token budget impl
- [pr_reviewer.py](https://github.com/The-PR-Agent/pr-agent/blob/main/pr_agent/tools/pr_reviewer.py) — orchestration
- [ignore.toml](https://github.com/The-PR-Agent/pr-agent/blob/main/pr_agent/settings/ignore.toml) + [generated_code_ignore.toml](https://github.com/The-PR-Agent/pr-agent/blob/main/pr_agent/settings/generated_code_ignore.toml) — noise patterns
- [.pr_agent.toml example](https://github.com/The-PR-Agent/pr-agent/blob/main/.pr_agent.toml) — root config
- [pr-agent.ai docs](https://pr-agent.ai) — product docs
