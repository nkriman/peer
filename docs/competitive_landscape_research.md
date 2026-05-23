# Competitive landscape: what existing AI PR reviewers do, and what peer should learn

Research date: 2026-05-23. Sources: vendor docs (CodeRabbit, Greptile, Graphite), the Macroscope Code Review Benchmark, and the independent 146-PR comparison published on dev.to.

## TL;DR

- Macroscope's benchmark (118 self-contained runtime bugs from 45 OSS repos): top **detection rate is 48% (Macroscope), 46% (CodeRabbit)**. Greptile got 24%, Graphite Diamond 18%, BugBot 42%.
- Independent 146-PR side-by-side (PHP/React backend SaaS): **93.4% unique catches** — tools rarely converge on the same finding. False-positive rates ranged 0–12%.
- All four commercial tools have some kind of **custom-rules / convention** mechanism. The pattern is plain-English markdown or YAML; some auto-discover.
- **Severity tiers calibrated to precision** is the consistent noise-reduction story (Seer: "critical → ship the fix"; Greptile: P1 tier most actionable).
- **Comment volume varies 18x** across tools: Graphite 0.62/PR → CodeRabbit 10.84/PR. peer is currently around 1–3/PR.
- peer's **`team_conventions` feature is industry-standard**. peer's **eval-driven iteration loop is unusual** — closest equivalent is Qodo's auto-rule discovery, but it's still embedded in a turnkey product, not a framework.

## What each tool actually does

### CodeRabbit
Context: hybrid AST Grep + RAG + LLM + 40+ integrated linters (ESLint, Semgrep, …). Custom rules via `.coderabbit.yaml` with per-path scoping, tone/depth settings, plain-English instructions. Learns from past feedback. Macroscope benchmark: **46% detection, 10.84 comments/PR** (only ~4.7 are runtime-relevant; rest is style/docs). Independent study: 281 findings on 146 PRs, **2.3% FPR**, 68.3% of findings were applyable unified-diff suggestions. Re-engages on every fix-push (5–6 review cycles per non-trivial PR).

### Greptile
Context: agentic indexing of the entire repo, follows nested calls multi-hop across files. Reviews take ~20 min. Custom rules: natural-language instructions + adapts from thumbs feedback. Macroscope: **24% detection** (tested on 72/118 — access was revoked mid-eval). Independent study: **0% FPR across 120 findings**, 92% bug-shaped catches (race conditions, null handling, N+1). Generates ASCII sequence diagrams by default ("unhelpful"). Pricing: $30/seat/mo + $1/extra review beyond 50.

### Graphite Diamond
Context: undisclosed in public docs. Templates for OWASP / Airbnb JS / PEP / Google Go style. Macroscope: **18% detection (21/115)**, <3% unhelpful. Lowest volume in benchmark at **0.62 comments/PR** — very conservative, prioritizes precision.

### Macroscope (the benchmark author, also a tool)
Context: AST-based codewalkers, language-specific parsers for 12 languages, builds complete reference graph. Best in own benchmark: **48% detection, 98% precision, 2.55 comments/PR**. Unique to Macroscope: closed-loop detect → fix → run CI → retry on failure → auto-merge. Custom rules via `.macroscope/*.md` markdown files; can block merges. Usage-based pricing ($0.05/KB) — aligns with AI-generated-PR volume growth.

### Cursor BugBot
Context: 8 parallel review passes with randomized diff ordering; detects issues in non-touched files via cross-interaction analysis. Macroscope: **42% detection, 70%+ precision, 0.91 comments/PR**. Independent study: **4.8% FPR**, 22 high-or-critical findings. Bundled exclusively with Cursor IDE seats — adoption blocker for non-Cursor teams.

### Sentry Seer
Independent study only. Severity tiers map cleanly to precision: "critical = ship the fix, high = evaluate, lower tiers = read carefully." 6/6 perfect at critical tier; 15% FPR at high. Prose-only (0% applyable suggestions). Status checks use `neutral` to signal "findings exist" — easy to miss.

### Qodo (formerly Codium)
Auto-discovers patterns from past reviews and auto-enforces them (Qodo 2.1 Rules System). Their own benchmark reports 60.1% F1 — non-comparable methodology. Heavy on auto-learning.

## The patterns everyone converges on

1. **Inject context beyond the diff.** Every tool reads more than the changed lines. AST/graph analysis is universal. Pure LLM-on-diff is not competitive.

2. **Custom rules in plain English / YAML / markdown.** No tool ships without it. The pattern is one of:
   - YAML config file at repo root (CodeRabbit's `.coderabbit.yaml`)
   - Markdown rule files in a directory (Macroscope's `.macroscope/*.md`)
   - Natural-language instructions stored per-team (Greptile)
   - Auto-discovered from past behavior (Qodo)

3. **Per-path scoping.** Style rules for `tests/`, perf rules for `src/`, security rules for `auth/`. Without this, rules either over- or under-apply.

4. **Severity tiers calibrated to precision.** The whole point of severity is "should I act now or skim later." The best tools make severity-tier == precision-tier so a user can trust "critical".

5. **Learn from feedback.** All four major tools either remember feedback (CodeRabbit), train on thumbs (Greptile), or auto-discover patterns (Qodo). One-time prompt engineering doesn't scale to a team's evolving style.

6. **High novelty across tools.** The dev.to study's 93.4% unique-catch result means **the right setup is stacking reviewers**, not picking one. peer's high novelty rate (97%) puts it in the same regime: it's a complementary reviewer, not a replacement.

## Where they diverge — the precision/volume/detection trade-off

| Tool | Comments/PR | Detection | Precision | Position |
|---|---|---|---|---|
| Graphite Diamond | 0.62 | 18% | <3% unhelpful | Conservative, high-trust |
| Cursor BugBot | 0.91 | 42% | 70%+ | High-signal, low-volume |
| Macroscope | 2.55 | 48% | 98% | Best of benchmark |
| Greptile | 3.08 | 24% | 0% FPR (independent) | Precision-first |
| CodeRabbit | 10.84 | 46% | 2.3% FPR | Volume-first |

There's no Pareto winner. CodeRabbit catches the most issues but creates 4x the noise of Macroscope on the same benchmark. Greptile's 0% FPR is enviable but only catches half what CodeRabbit does. The user-meaningful question is: how many comments per PR can your team tolerate?

## How they evaluate themselves

Two methodologies are used in the wild:

1. **Macroscope's:** 118 self-contained *runtime bugs* from 45 real OSS repos, 8 languages. Each tool detects against ground-truth bug labels. Scoring: detection rate + precision (% of findings deemed actionable by review). Reproducible, third-party-runnable.

2. **Independent (dev.to):** Run N tools on your own merged PRs for ~3 weeks; track verdicts ("Fixed in [commit]" → valid; "Not applicable" → false positive). Reproducible per team but slow.

Neither uses "human inline comment matching" the way peer's eval does. Their stance is: humans miss things; human comments are not a gold standard; **a real bug fix or a "fixed in commit" reply is the only honest signal**.

## What peer should learn from all this

### 1. Fix the eval metric (immediate)

Mean-of-per-PR-rates is misleading when gold counts vary across PRs. The industry uses:
- **Detection rate** = sum-of-sums (% of gold defects caught across all samples)
- **Precision** = % of agent comments that humans would call actionable
- **Comments/PR** = noise indicator

Adopting this trio makes peer's numbers comparable to Macroscope's benchmark (46% CodeRabbit, 24% Greptile, etc.) so users can position their custom-built reviewer in the landscape.

### 2. Reframe the gold dataset (medium-term)

Human inline comments are the wrong gold standard — they're noisy with Q&A, they miss things, and they're not stable. Better gold:
- **Runtime bugs** discovered via post-merge bugfix correlation (peer's existing `PostMergeBugfixCorrelation` is on the right idea — should be promoted to a default in some scenarios).
- **Test failures** post-merge that should have been pre-flagged.
- **"Fixed in commit" replies** to peer's own past comments on PRs the team accepted into the eval loop.

The framework should support all three; the default `GitHubInlineCommentSource` is just one option.

### 3. Custom rules need YAML + per-path scoping (medium-term)

`Agent(team_conventions=...)` is the right primitive. Make the default loader read from `.peer.yaml` (CodeRabbit-style) and support per-path scoping:

```yaml
# .peer.yaml
conventions:
  - path: "src/auth/**"
    rules: "docs/security_review.md"
    severity_floor: important
  - path: "tests/**"
    rules: "docs/test_conventions.md"
    severity_cap: minor
  - path: "**"
    rules: "docs/general_style.md"
```

This addresses the calibration-flip we saw in our conventions experiment: the severity instruction was a global blunt-force; per-path scoping with explicit floors/caps is what the industry does.

### 4. Severity tiers must map to precision (high-impact change)

The conventions experiment showed peer's severity went from over-severing (+0.75) to under-severing (-0.33) with one prompt tweak. Without calibration, severity is meaningless. Adopt the Seer pattern:

- `critical` = "we are >95% sure this is a real bug a senior would block on"
- `important` = "we are 70%+ sure this needs attention before merge"
- `minor` = "noticeable, may be wrong, worth a glance"
- `nit` = "style preference, may not even be an issue"

Eval should measure **precision per severity tier** — if `critical` isn't ~100% precise, the severity is broken.

### 5. Auto-learning is the long-game (v0.3+)

Qodo's "Rules System discovers patterns from past reviews" is what peer's eval framework is uniquely positioned to enable. Concrete: after each eval run, look at high-novelty + low-acceptance peer comments and ask "is this a systematic pattern we should add to the conventions doc, or systematically remove from?" Output proposed `team_conventions` updates as a diff.

Nobody else has this because nobody else has the framework shape: eval-as-first-class drives auto-learning naturally.

### 6. The depth gap is real but bounded

Greptile takes 20 min per review with multi-hop indexing; peer takes 15s with single-hop tree-sitter. Greptile's detection is *lower* (24% vs CodeRabbit's 46%), so depth alone isn't winning. peer's middle position (tree-sitter symbols + ast-grep call sites + test discovery) looks roughly right — closer to Macroscope's architecture than Greptile's.

Where peer is genuinely behind:
- **No linter integration.** CodeRabbit's 40+ linters cover huge ground cheaply. peer should consider running ruff / mypy / pylint output as additional context.
- **No cross-file reference graph.** peer sees symbols modified + their call sites, but not "what does the calling function actually do." Greptile-style multi-hop is heavy; a lighter "follow callers 1 level" would help.
- **No patch generation.** Peer flags issues; competitors propose `\`\`\`suggestion` blocks. 68% of CodeRabbit's findings are applyable diffs — that's a usability gap.

### 7. peer's unique pitch — the framework, not the reviewer

What no commercial tool offers:

1. **Build your own reviewer** tuned to your repo (model, prompt, conventions, context-depth, severity rubric — all swappable Protocols).
2. **Eval your own reviewer** against your own gold (runtime bugs / past reviews / hand-curated samples).
3. **Iterate** with quantitative deltas between runs.

Closest commercial parallel: Qodo's auto-learning, but you can't observe the loop or override its decisions. peer can.

The competitive landscape clarifies peer's position: **not a CodeRabbit competitor; a meta-tool that helps you build something CodeRabbit-shaped (or BugBot-shaped, or Graphite-shaped) for your specific repo and team.**

## Concrete next-step recommendations, ranked

1. **Switch primary recall metric to sum-of-sums** + report comments/PR as noise indicator. Makes numbers comparable to industry. ~1 hour.

2. **Add per-tier precision metric** (precision-among-critical, precision-among-important, etc.). Quantifies severity calibration. ~2 hours.

3. **Soften the conventions-doc severity instruction** that caused the calibration flip. Remove "treat as nit or minor for pure style"; let the agent infer severity from the convention's own importance. ~30 min.

4. **`.peer.yaml` config file** with per-path conventions scoping. Adopt the CodeRabbit pattern. ~3–4 hours. Use it to re-test the conventions experiment with appropriate per-path severity caps.

5. **Sketch `benchmark-v01`**: use Macroscope's published 118-bug dataset (it's MIT-licensed at `github.com/vlad-ko/pr-review-bench`) plus a peer-built smaller bug dataset, and run peer vs CodeRabbit/Greptile/Macroscope adapters. This is the SOTA-credibility move you flagged earlier in the session.

6. **Add ruff/mypy linter integration to codebase context.** Cheap; matches CodeRabbit's 40+ linter pattern. ~3 hours.

7. **Patch-suggestion output.** Allow Comment to optionally include a `\`\`\`suggestion` block. ~2 hours. Bigger lift if we want it to actually apply cleanly.

## Sources

- [CodeRabbit docs](https://docs.coderabbit.ai/)
- [Greptile homepage](https://www.greptile.com/)
- [Best AI Code Review Tools 2026 — Macroscope (with 118-bug benchmark methodology and per-tool detection/precision numbers)](https://macroscope.com/content/best-ai-code-review-tools-github-2026)
- [Best AI Code Reviewer in 2026 — Independent 146-PR / 679-findings comparison (dev.to)](https://dev.to/_vjk/best-ai-code-reviewer-in-2026-we-ran-4-in-parallel-for-3-weeks-146-prs-679-findings-1c0f) — full anonymized dataset at `github.com/vlad-ko/pr-review-bench`
- [Best AI Code Review Tools — Qodo blog](https://www.qodo.ai/blog/best-ai-code-review-tools-2026/)
