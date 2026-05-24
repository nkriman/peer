## Context

This change ships the SOTA-credibility comparison flagged in `eval-v01` design Decision 14 and refined by the competitive landscape research. The framework's eval surface (gold-defect matching) is the right shape for *your own repo's reviewer iteration*; it's not the right shape for *industry positioning* because human inline comments aren't a stable ground truth. Macroscope's runtime-bug methodology (real bugs, objective "did the tool catch it") is the standard the industry uses.

We piggyback on the published Macroscope dataset rather than building our own. Two reasons: (a) it's already vendor-neutral and has published baselines for 5+ tools; (b) building a comparable runtime-bug dataset from scratch is a multi-month research effort.

## Goals / Non-Goals

**Goals:**
- A peer user can run `peer benchmark --dataset macroscope` and get a number directly comparable to "Macroscope 48% / CodeRabbit 46%".
- The benchmark output renders a leaderboard with published baseline numbers visible, so peer's number is contextualized.
- Bug-detection judging is its own concern, separate from the human-comment judge in `eval-v01` — bugs have objective root causes that don't need semantic interpretation of reviewer chatter.
- Bring-your-own-dataset: users can pass a custom `BugDataset` JSONL for their own internal bug benchmarks.
- Cost transparency: a full benchmark run shows total $ spent.

**Non-Goals:**
- Run commercial reviewers (CodeRabbit / Greptile / etc.) against the dataset live. They don't expose programmatic APIs in v0.1; the published numbers are the comparison.
- Build peer's own runtime-bug dataset (could be a v0.2 change inspired by Macroscope's methodology).
- Multi-language coverage (peer is Python-only for codebase-context until `linter-context-v01` lands more languages).
- Closed-loop validation (peer flags the bug → applies the fix → runs tests). Macroscope's differentiator; matching it is a future change.

## Decisions

### 0. Unit of review + line-number coordinate system (PREREQUISITE)

Before the rest of the design holds, the benchmark must nail down two coordinate-system questions the original v1 spec left open:

**Q1: What does peer review for a bug?**
- The PR that *introduced* the bug (so peer "should have caught it pre-merge")?
- The commit that contains the bug (post-mortem review)?
- A synthetic PR derived from the bug's commit?

**Decision:** for Macroscope's dataset, each `BugSample` carries `pr_url` (the introducing PR, where known) AND `commit_sha` (the buggy commit). Peer reviews `pr_url` when present; falls back to a synthetic PR from `commit_sha` (using `gh api compare/<parent>...<commit>` to produce a diff that `Agent.run` can consume). Samples lacking both `pr_url` and a valid parent commit are SKIPPED from the run with an explicit "skipped: no reviewable diff" entry in the per-bug breakdown.

**Q2: How do `BugLocation.line` and `peer_comment.line` line up?**

`BugLocation.start_line` / `end_line` are line numbers in the FILE at the BUGGY COMMIT. `peer_comment.line` is the new-file line number in the PR DIFF that peer reviewed. For the same logical bug, these may differ if the PR's diff has unrelated changes above the bug location.

**Decision:** the matching uses TWO line-number maps:
1. For comments on files that were modified in the PR diff: line numbers map directly (PR's new-file line = file-at-PR-head line).
2. For comments referencing lines OUTSIDE the PR diff (rare for peer, common for benchmarks): SKIP the match — peer cannot "catch" a bug it never saw in the diff.

`BugLocation.line` numbers are translated from "buggy commit" to "PR head" via `git blame --reverse` only if a PR-context exists. Otherwise they're assumed to be in the synthetic PR's diff coordinates (which we just constructed).

`BugLocation` schema extended (vs the v1 spec): `start_line`, `end_line`, AND `line_coordinate_system: Literal["bug_commit", "pr_head", "synthetic"]` so the runner knows what frame each location is in.

**Decision:** for the v1 Macroscope vendoring, ALL `BugLocation`s are tagged `line_coordinate_system="bug_commit"`; the loader translates to `pr_head` when peer reviews the PR introducing the bug, or uses them as-is when the run is on a synthetic PR derived from the bug commit. Documented in `MACROSCOPE_PROVENANCE.md`.

If a particular bug cannot be reliably translated (no PR, no parent commit), it's SKIPPED from the run with an explicit reason — better to exclude than to falsely report "missed".

### 1. Use the Macroscope MIT-licensed dataset as the default

We vendor a snapshot of `github.com/vlad-ko/pr-review-bench` into `dataset/benchmark/macroscope_v1.jsonl`. Provenance file (`dataset/benchmark/MACROSCOPE_PROVENANCE.md`) records: upstream commit SHA, fetch date, license (MIT), schema mapping notes.

**Why vendor:** the upstream dataset structure may change; we want stable numbers that don't shift under us. A vendored snapshot is reproducible; users can re-fetch / update via a CLI helper.

**Trade-off:** snapshot will lag upstream. We add a `peer benchmark update-dataset` helper that re-fetches and runs a diff so users can see what changed.

### 2. BugSample schema is distinct from GoldSample

```python
class BugSample(BaseModel):
    bug_id: str              # e.g., "macroscope-bug-042"
    repo_url: str            # upstream repo
    pr_url: Optional[str]    # the PR that introduced the bug (if available)
    commit_sha: str          # the buggy commit
    bug_paths: list[BugLocation]  # files + line ranges where the bug lives
    root_cause: str          # ground-truth description of the bug
    suggested_fix: Optional[str]
    severity: Severity       # ground-truth severity per dataset
    language: str            # "python", "go", "java", ...
    bug_category: Optional[str]  # "null-deref", "race-condition", "off-by-one", ...
    metadata: dict           # provenance: upstream issue link, fix-commit SHA, etc.

class BugLocation(BaseModel):
    path: str
    start_line: int
    end_line: int
```

**Why a separate schema (not GoldSample):** bug benchmarks have different metadata than human-comment-derived gold (`root_cause`, `bug_category`, no `original_comment_excerpt`, etc.). Trying to fold them into GoldSample would either inflate the schema with optional bug fields or under-specify both.

### 3. BugBenchmarkRunner uses bug-detection judging, not gold-match judging

The judge prompt asks: "Given the bug location and root cause description below, did this reviewer comment identify the bug?" Returns CAUGHT or NOT_CAUGHT. Different from `eval/judging.py:judge_match` which asks "Same issue or different issue?" semantically.

The bug judge runs once per (bug, peer-comment) pair where the peer comment's path overlaps any `BugLocation.path` AND its line is within `[start_line - 10, end_line + 10]` (loose proximity, to allow peer to comment near but not exactly on the bug line).

**Why looser line range:** real bug fixes often shift line numbers; a reviewer commenting on the function that contains the bug, even at a different line, is a valid catch.

### 4. BenchmarkReport includes published-baseline comparison

```python
class BenchmarkReport(BaseModel):
    report_schema_version: str = "1.0"
    run_id: str
    timestamp: datetime
    agent_config: AgentConfig
    dataset_id: str           # "macroscope-v1.jsonl"
    dataset_size: int
    n_bugs_caught: int
    n_bugs_total: int
    detection_rate: float     # n_bugs_caught / n_bugs_total — THE headline
    comments_per_pr: float
    cost_usd_total: float
    latency_p50_seconds: float
    per_bug: list[BugBenchmarkResult]
    published_baselines: dict[str, dict]  # {tool: {detection, comments_per_pr, source_url}}
```

`published_baselines` is a hand-maintained dict (in `src/peer/benchmark/baselines.py`) updated when new benchmark data is released. v0.1 ships with the Macroscope numbers from `docs/competitive_landscape_research.md`.

### 5. Vendored dataset, not live fetch

`peer benchmark --dataset macroscope` reads from `dataset/benchmark/macroscope_v1.jsonl` (vendored). A separate `peer benchmark update-dataset --source vlad-ko/pr-review-bench` helper fetches fresh, diffs against vendored, prompts before overwriting.

**Why:** reproducibility. Users running benchmark in CI shouldn't have it silently change because upstream evolved.

### 6. Leaderboard rendering is the default output

CLI output for `peer benchmark`:

```
=== peer benchmark: macroscope-v1 (118 bugs, 8 languages) ===
peer (this run)              42 / 118    35.6%   2.1 comments/PR   $7.42   p50 18.2s
                                                                            
Published baselines (from docs/competitive_landscape_research.md):
  Macroscope                  57 / 118    48.3%   2.55 comments/PR
  CodeRabbit                  54 / 118    45.8%   10.84 comments/PR (~4.7 runtime-relevant)
  Cursor BugBot               50 / 118    42.4%   0.91 comments/PR
  Greptile                    17 / 72     23.6%   3.08 comments/PR (tested on partial dataset)
  Graphite Diamond            21 / 115    18.3%   0.62 comments/PR

Report saved to data/benchmark_runs/<run_id>.json
```

Side-by-side numbers make the comparison concrete. Users see exactly where their peer-built reviewer sits.

### 7. Per-bug breakdown for forensics

The JSON report includes per-bug detail: which bugs peer caught, which it missed, why (loose-proximity comments exist but didn't pass judge, no comment in proximity at all, etc.). Lets users drill into specific misses to inform prompt / convention tuning.

### 8. Cost guardrails

`peer benchmark` prints estimated cost before launch and prompts confirmation when > $5:

```
About to run 118 reviews + ~250 judge calls.
Estimated cost: $7.40 (Sonnet 4.6 default reviewer + Haiku judge).
Proceed? [y/N]
```

`--yes` flag skips prompt for CI use.

## Risks / Trade-offs

- **[Risk]** Macroscope's published numbers used their proprietary tool with proprietary context — apples-to-apples comparison isn't perfect. **Mitigation:** explicit "published baselines" framing makes the source clear; users decide whether the comparison is fair for their context.
- **[Risk]** The vendored dataset goes stale as the upstream evolves. **Mitigation:** `peer benchmark update-dataset` helper + provenance file.
- **[Risk]** Bug benchmark cost compounds — 118 reviews × $0.05 = $7 per run; users running this in CI on every PR would burn money. **Mitigation:** cost-prompt + `--yes` opt-in; document recommended usage (one-off per prompt iteration, not per PR).
- **[Risk]** Bug-detection judging may be too strict (peer comments near but not at the bug line, judge says NOT_CAUGHT). **Mitigation:** the proximity range (`±10 lines`) is generous; judge prompt includes the bug location AND root cause so it can match semantically even if peer's exact line is off.
- **[Risk]** peer's detection number on Macroscope dataset will likely be lower than CodeRabbit / Macroscope (we're a default-config single-pass reviewer; they're tuned products). Users may interpret this as "peer is worse." **Mitigation:** docs framing: peer is the framework; the number is the *default-configuration* baseline a user starts from and iterates upward. The whole point is the iteration loop.
- **[Risk]** Dataset coverage is 8 languages; peer's codebase-context is Python-only. **Mitigation:** filter Macroscope dataset to Python-only for v0.1 numbers; report both "Python-subset" and "full" numbers as the language-coverage gap closes.

## Open Questions

None blocking. Deferred:
- Live commercial-baseline runs (would need API access + ToS clearance). When/if feasible, a new `live-baselines-v01` change.
- Building peer's own internal-bug-database (using a team's Jira / Sentry / postmortem data as ground truth). A natural follow-on for production users.
- Continuous benchmark CI runs with regression detection. After this change ships and gets used.
