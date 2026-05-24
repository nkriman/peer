# v0.2 strategic posture — why all 8 changes are "catch-up" and how we stay differentiated

The adversarial review of v0.2 OpenSpec changes (`data/eval_runs/openspec_adversarial_review_v1.md`) made a sharp strategic call: **7 of 8 v0.2 changes are catch-up moves to competitors (Pydantic AI, Pydantic Evals, CodeRabbit, PR-Agent, Macroscope). The risk is that peer becomes a third-rate Pydantic AI clone with an eval framework attached, losing its distinctive eval-first positioning.**

This doc is the design author's response to that critique. Read it before implementing v0.2 to make sure the implementation choices serve the strategic intent, not just the local design.

## Honest assessment of the v0.2 scope

| Change | Source of inspiration | Is it differentiated? |
|---|---|---|
| `prompt-quality-v01` | PR-Agent's prompt language | No — direct lift. |
| `eval-metrics-v01` | Macroscope's metric trio | Mostly catch-up. |
| `peer-deps-v01` | Pydantic AI's deps_type pattern | Catch-up — peer reimplements PA's pattern verbatim. |
| `peer-config-v01` | CodeRabbit's `.coderabbit.yaml` | Catch-up — peer needs a config file. |
| `linter-context-v01` | CodeRabbit's 40+ linter approach | Partial — peer's Linter Protocol IS a real seam. |
| `patch-suggestions-v01` | CodeRabbit's suggestion blocks + PR-Agent's issue_header | Catch-up — table-stakes feature parity. |
| `benchmark-v01` | Macroscope benchmark | Catch-up — peer measures against an external yardstick. |
| `eval-v02` | Pydantic Evals patterns | Mostly catch-up. |

**The adversarial review is correct: this is a catch-up wave.** Pretending otherwise is dishonest.

## Why catch up now (the honest case)

1. **Table stakes for credibility.** A framework that can't run with `.peer.yaml`, doesn't integrate linters, doesn't output suggestion blocks, and ships a hand-rolled deps system instead of the Pydantic-AI standard isn't taken seriously by the production-AI-tools community. Even differentiated frameworks need the table stakes.

2. **Differentiation requires comparability.** peer's core pitch — "build your own AI PR reviewer + measure improvements quantitatively" — only works if a user can compare a peer-built reviewer to CodeRabbit, Greptile, etc. on the same dataset. `benchmark-v01` makes that comparison possible. **The number isn't the point; the comparability is.**

3. **The framework's value is the LOOP.** Without the configuration / linter / suggestion / benchmark features, peer's user can't *iterate* on a reviewer for their specific repo. The catch-up features unlock the differentiator.

4. **Cost of pure differentiation.** If we skipped these and shipped only "novel" features (the Reviewer Protocol, the GoldSample dataset, the EvalRunner), we'd have a research framework, not a tool teams adopt.

## How to stay differentiated despite the catch-up

The adversarial review's strategic concern is the right one to take seriously. Three commitments for the v0.2 implementation:

### 1. Keep the framework's "8 Protocols" pitch front-and-center

`docs/framework_overview.md` documents 8 extension-point Protocols: `Reviewer`, `RawSampleSource`, `CommentClassifier`, `Taxonomy`, `EnrichmentStep`, `GoldSampleStorage`, `EvalMetric`, `EvalReport`. v0.2 must NOT add new Protocols beyond what's necessary (Linter is the only one). The 8-Protocol shape is what differentiates peer from end-to-end products like CodeRabbit (one fixed reviewer; no eval-framework).

**Implementation check:** every spec's "What Changes" section should clarify whether it adds, modifies, or leaves Protocols alone. A v0.2 that bloats to 12 Protocols loses the differentiator.

### 2. The eval-first iteration loop is the headline use case

Most users adopt peer to **build + iterate**, not to use peer's defaults. The README quickstart should lead with the cycle: build a reviewer → eval against your gold dataset → see the delta → tweak → re-eval. Not "use peer's reviewer."

**Implementation check:** README updates from the v0.2 changes should foreground the iteration loop. Default-reviewer usage should be the SECONDARY narrative.

### 3. Defer features that pull peer toward "production tool, not framework"

Per adversarial review Section 6, several features push peer toward the "production AI PR review tool that happens to be open source" identity. These should remain low-priority OR live in a future `peer-tools` extension package:

- **`benchmark-v01`** — useful for credibility but NOT for users iterating on their own repo's reviewer. Could move to `peer-tools` after v0.2. For now: keep in core but emphasize "this is for industry-positioning comparison, not for everyday use" in docs.
- **`peer-config-v01`'s auto-detect of `.peer.yaml`** — convenient for end-users; signals "configurable product". For framework users, explicit `Agent(config=PeerConfig(...))` is more discoverable. Keep auto-detect but document the explicit pattern as preferred for framework usage.
- **`linter-context-v01`'s default RuffLinter being enabled** — opinionated default that helps end-users; framework users may want to choose explicitly. Acceptable as long as `PeerDeps(linters=[])` disables cleanly.

### 4. Reject the "pretend it's original" framing

The adversarial review item 3.6 is right: the "Why" sections of `peer-deps-v01` and `eval-v02` invoke the Pydantic AI / Pydantic Evals research docs and claim "inspired by" while reimplementing verbatim. This creates legal and credit risk. Each change's design.md SHOULD include an explicit Attribution section listing what's directly lifted and what's adapted, in the same way `prompt-quality-v01` attributes PR-Agent.

**Implementation check:** before implementing `peer-deps-v01` and `eval-v02`, add Attribution sections to their respective `design.md` files.

### 5. The benchmark number isn't a marketing asset; it's a calibration signal

Per adversarial review's strongest strategic critique: when `benchmark-v01` produces peer's number on the Macroscope dataset and it's lower than CodeRabbit's 46% or Macroscope's 48%, the urge will be to defensively frame it ("peer is the framework; the number is the default-config baseline"). This is a losing PR position.

**Better framing:** the benchmark capability is for USERS to measure THEIR peer-built reviewer against published baselines. peer-the-default's number is incidental. The README should NOT lead with peer's default benchmark number; it should lead with "here's how to use `peer benchmark` to compare YOUR custom reviewer."

**Implementation check:** `benchmark-v01`'s docs and CLI output should de-emphasize peer's default number. The published_baselines comparison should show "your run vs published baselines," with peer's default row clearly labeled as "peer (out-of-the-box; iterate to improve)."

## The 6-month regret check

The adversarial review predicted 6 regrets. For each, the v0.2 implementation should validate (during the build, not after) that we're avoiding it:

1. **"The benchmark number didn't move the conversation in our favor."** → Validation: before publishing peer's default benchmark number anywhere, make sure the README + CLI output frame it correctly per the principle above. If we can't, downgrade the visibility.

2. **"eval-v02 + peer-deps-v01 together blow up the eval surface area."** → Validation: after both land, count the Protocols + their parameters. If it grows past 10 with required-vs-optional confusion, refactor before publishing.

3. **"Validation retries doubled some users' API bill on day one."** → Validation: default `retries={"output": 0}` (per adversarial 2.2 — done). Users explicitly opt in.

4. **"No one is asking for 4 ways to inject conventions."** → Validation: peer-config-v01 design Decision 6b consolidates to 3 (system_prompt full-replace, extra_instructions short-tweak, per-path conventions_file). Deprecates team_conventions. Done.

5. **"RationaleGrounding caught no real hallucinations and was expensive."** → Validation: default OFF per adversarial 1.5/5.1 (done). Empirical validation: if RationaleGrounding never fires in the first 3 months of opt-in usage, deprecate it.

6. **"Pydantic AI ships 1.0 and our parallel implementation feels silly."** → Validation: build a `peer-pydantic-ai-v01` adapter change AS THE FIRST v0.3 priority. Don't let the parallel implementation outlive its strategic moment.

## What the v0.2 implementation should NOT do

- Don't add Protocols beyond what's specced. The temptation to add `Cache`, `RetryPolicy`, `Authentication`, `Telemetry` Protocols will be strong — resist.
- Don't extend Comment beyond `issue_header` + `end_line` + `suggestion`. The slippery slope to `tags`, `links`, `attachments`, `priority`, `assignee` is real.
- Don't promote the default reviewer over user-customized reviewers in any doc. The framework pitch fails if users think peer = "use this reviewer."
- Don't ship a default `.peer.yaml` template that's heavily opinionated. The example file is for showing the format, not for users to copy verbatim.

## Implementation order (with these constraints)

Per the adversarial review + this strategic posture:

1. `prompt-quality-v01` — done.
2. `eval-metrics-v01` — finish (in progress).
3. **`peer-deps-v01`** — foundational; implement with Attribution section + the scope corrections per adversarial review (no `instructions`, no `metadata` on RunContext, default `retries=0`).
4. `peer-config-v01` — slot into PeerDeps; consolidate conventions injection (Decision 6b); severity = most-restrictive.
5. `linter-context-v01` — RuffLinter only as default; MypyLinter to `examples/`.
6. `patch-suggestions-v01` — keep all 3 schema additions; drop IssueHeaderDistribution Metric class (make derived stat).
7. **`eval-v02`** — implement with EvalMetric.score back-compat + async-safe capture per-task + RationaleGrounding opt-in.
8. **`benchmark-v01`** — implement with the nailed-down coordinate system (Decision 0); de-emphasize peer's default number.
9. Defer: `peer-pydantic-ai-v01` (adapter) — schedule for v0.3.

## Net

Yes, v0.2 is a catch-up wave. That's fine. It's the table-stakes layer that unlocks the differentiator. The implementation just needs to be honest about it (Attribution sections, defensive framing of benchmark numbers, conservative Protocol additions). And v0.3 needs to be back to differentiation — `peer-pydantic-ai-v01` adapter + the next round of eval-first capabilities (case-specific evaluators in production use, RationaleGrounding empirical validation, etc.).

The adversarial review's deepest critique — *"in 6 months the regret will be that peer turned into a third-rate Pydantic AI clone with an eval framework attached"* — is averted IF:

1. v0.2 ships the catch-up but maintains the eval-first framework pitch.
2. v0.3 doubles down on differentiation (no more catch-up).
3. The README + docs lead with the iteration loop, not the default reviewer.
4. The benchmark number is a user tool, not a peer marketing asset.

All four are choices we make in the implementation, not in the specs.
