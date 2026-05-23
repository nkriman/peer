# Dataset curation guide

> Methodology for building a gold dataset that's worth measuring against.
> If you skip this and just point `EvalRunner` at raw GitHub comments, you
> will get numbers that mean nothing. This doc explains why and how to do it
> right.
>
> Companion to [`docs/framework_overview.md`](framework_overview.md) (the
> architectural surface) and `openspec/changes/eval-v01/design.md` (the full
> rationale).

## Why curation matters

The MVP eval that shipped with the agent's first cut treated raw GitHub inline comments as ground truth: pull every reviewer comment on every PR, ask a judge LLM whether the agent's comments matched any of them, report a hit rate. That eval produced a **13% hit rate** across a 14-PR Django + Pydantic batch and the obvious conclusion was "the agent is bad."

The actual conclusion was that the eval was wrong. Two problems:

1. **6 of 14 PRs had zero defect-style human comments.** They were merged with approvals only, or with conversational comments like "looks good once you address this nit." Treating those PRs as 0/N misses is meaningless — there were no defects to catch.
2. **The remaining 8 PRs' comments were mostly conversational.** Roughly **4 of every 5 inline comments** on small OSS PRs are author-reviewer Q&A, clarification ("did you mean to remove this?"), discussion ("should we handle the empty case here or in the caller?"), approval ("LGTM after the rename"), or off-topic chatter. They are not defect reports.

If you don't separate those from real defects, your "ground truth" is 80% noise and a 13% hit rate against it tells you nothing about whether the reviewer is finding defects.

The fix is the curation pipeline this doc describes: classify every raw comment into a taxonomy that distinguishes defects from discussion, drop the discussion, and store the rest as a normalized `GoldSample`. Done well, the resulting dataset is small but clean, and a hit rate against it is interpretable.

## The default Taxonomy

`peer` ships an 8-category taxonomy designed to be broad enough to capture what real OSS PRs contain and narrow enough for a zero-shot Haiku classifier to choose reliably. Six categories are defects, one is a nit-only category, one is dropped.

The categories with examples drawn from the kinds of real comments the classifier was tuned against:

### `defect-correctness` (kept, classifier severity)

Bug, logic error, broken behavior, regression risk, off-by-one, None dereference, race condition, incorrect handling of edge cases.

> "This will raise `KeyError` if the user dict is empty — the existing code path returns `None` in that case, so this is a behavioral regression."

### `defect-security` (kept, classifier severity)

Security or privacy concern: injection, auth bypass, secret leak, unsafe deserialization, missing input validation that creates a vulnerability.

> "We're interpolating the user-supplied `query` directly into the SQL — needs to be a parameterized query."

### `defect-performance` (kept, classifier severity)

Performance concern with a concrete cost case: unnecessary work in a hot path, N+1 query, redundant allocation, missing index, blocking I/O on the wrong thread.

> "This `_get_user` is called inside the loop and hits the DB every time — pull it out and pass it in, or batch-fetch upfront."

### `defect-api-design` (kept, classifier severity)

Wrong abstraction layer, breaking API change, leaky abstraction, confusing naming that will mislead callers, mutable default arg.

> "Moving this to the `Schema` base class makes every subclass inherit the validator even when it doesn't make sense — should live on the concrete class that needs it."

### `defect-test-gap` (kept, classifier severity)

The change is untested, lacks coverage for an important branch, or breaks/disables existing tests without justification.

> "There's no test for the case where `extras` is empty — that's the path most likely to regress."

### `defect-doc-gap` (kept, classifier severity)

The change needs documentation it doesn't have: missing docstring on a new public API, missing changelog entry, outdated docs that the change now contradicts.

> "New public `from_orm` overload — needs a docstring and a changelog entry; users will hit this in autocomplete with no signal of what it does."

### `style-nit` (kept, forced `nit` severity)

Pure formatting, naming preference, import ordering, line length, trailing commas — anything a linter could catch. Kept in gold but forced to `nit` severity so it doesn't compete with real defects for the recall headline.

> "Could you rename `tmp` to `parsed_schema`? Hard to follow what `tmp` refers to two lines down."

### `discussion` (dropped from gold)

Implementation Q&A from author, reviewer suggesting a how-to, clarification chatter, "looks good", "please review", approval, praise, off-topic. **Not a defect; dropped from gold entirely.**

> "What information should we surface in the error message here — just the field path, or the whole context?"
>
> "LGTM, thanks for the quick turnaround."
>
> "Selected reviewer: @samuelcolvin"

The dropped `discussion` category is the single most important piece of the taxonomy. It's why curated `peer` datasets give interpretable hit rates and the raw-comments MVP didn't.

Severities are `critical / important / minor / nit`. The same scale the agent uses for its own output, deliberately — eval mismatches are interpretable because both sides are using the same vocabulary.

## The pipeline

Four stages, each a pluggable Protocol. Defaults documented; how to override below.

### 1. Source

`RawSampleSource.fetch(pr_url)` returns a `RawSample` containing the PR metadata + every comment posted on it. The default `GitHubInlineCommentSource` shells out to `gh api` for PR details and inline review comments, then drops bot accounts (`coderabbitai`, `dependabot`, `github-actions`, etc.) so they don't pollute the gold pool.

If your team's review history lives somewhere other than GitHub inline comments — Jira tickets, internal review databases, an Excel dump of past audit findings — implement your own `RawSampleSource` against the Protocol and the rest of the pipeline runs unchanged.

### 2. Classify

`CommentClassifier.classify(comment, pr_context)` returns a `Classification(category, severity, reasoning)`. The default `LLMCommentClassifier` makes one Haiku 4.5 call per raw comment with a prompt generated from the active `Taxonomy` — so a custom taxonomy works without writing a custom classifier.

Results are disk-cached at `~/.cache/peer/classifier_cache.jsonl`, keyed on `sha256(repo + comment_id + taxonomy.version)`. Re-running curation on the same PR is free. Changing the taxonomy version invalidates the cache automatically.

Misclassifications happen — Haiku's classification isn't perfect and this is the point at which the spot-check matters (see below). The classifier is "good enough" by design, not state-of-the-art; users who need sharper classification override the `CommentClassifier` Protocol with a few-shot or fine-tuned version.

### 3. Enrich (optional)

`EnrichmentStep.enrich(sample, pr_context)` returns a `GoldSample` with possibly-added defects from sources other than human reviewer comments. Default is `NoEnrichment` (passthrough). Two opt-in alternatives ship in `peer.dataset.enrichment`:

- **`PostMergeBugfixCorrelation`** — looks for follow-up PRs that mention the original PR (by SHA or PR number) with a title containing `fix|fixes|fixed|regression|bug|bugfix|hotfix`, and converts their diffs into "should have been caught" defects on the original. Tagged `source=post_merge_correlation`.
- **`LLMOracleEnrichment`** — runs a strong model (Opus 4.7 by default) over the PR with a "be a senior reviewer" prompt and adds its high-confidence defects to gold, tagged `source=llm_oracle`.

Enrichment is conservative by construction: it only adds defects, never deletes or rewrites human-derived ones, and always tags the source so downstream consumers can filter.

### 4. Store

`GoldSampleStorage.append(sample)` persists the curated sample. Default `JSONLStorage` writes one `.jsonl` file per dataset, one `GoldSample` per line. Inspectable via `jq`, diffable via git, append-only friendly.

Override path: implement `SQLiteStorage`, `PostgresStorage`, `S3Storage` against the same Protocol for teams with larger datasets or multi-user editing needs. The Protocol exposes `append`, `load_all`, `find(pr_url)`, `delete(pr_url)` — that's the full contract.

## Defining a custom Taxonomy

You give up `DefaultTaxonomy` when:

- Your team's notion of "defect" is narrower (e.g., only security counts; everything else is noise).
- Your severity scale doesn't fit `critical / important / minor / nit`.
- You have categories that aren't in the default (e.g., `accessibility`, `i18n`, `wontfix-tech-debt`).

The construction is straightforward — a list of `CategoryDef`, a list of severities, the drop rules, and a version string for cache invalidation:

```python
from peer.dataset import Taxonomy, CategoryDef, LLMCommentClassifier

acme_taxonomy = Taxonomy(
    categories=[
        CategoryDef(
            name="security",
            description="Auth bypass, injection, secret leak, unsafe deserialization.",
            is_defect=True,
        ),
        CategoryDef(
            name="other",
            description="Anything that isn't a security defect.",
            is_defect=False,
        ),
    ],
    severities=["blocker", "warning"],
    drop_categories=["other"],
    nit_only_categories=[],
    version="acme-security-v1",
)

classifier = LLMCommentClassifier(taxonomy=acme_taxonomy)
```

Pass `acme_taxonomy` into `LLMCommentClassifier`, the classifier regenerates its prompt from the new categories, and the disk cache invalidates because `taxonomy.version` changed. Nothing else in the pipeline needs to know.

If your team is iterating on the taxonomy itself, bump the `version` string each change so old classifications don't leak across taxonomy revisions.

## Enrichment trade-offs

Enrichment is conservative-by-default for a reason. Here's when to flip each one on.

### Stay with `NoEnrichment` (the default) when

- You're bootstrapping your dataset and want to see what your humans actually flagged.
- You're not sure yet what "good defects" look like for your repo — let the human-reviewed sample guide that intuition first.
- Your reviewers are senior enough that you trust their comments as ground truth.

This is the right starting point for almost everyone. Enrichment is an upgrade, not a default.

### Use `PostMergeBugfixCorrelation` when

- Your repo has a clear pattern of "follow-up PR that fixes a bug introduced in PR N." Most mature OSS projects do.
- You want to catch the class of defects that humans *missed* during review but were caught in production. These are exactly the defects an AI reviewer should be valued for catching.
- You're willing to accept that bugfix-correlation occasionally misattributes (a follow-up fix might be for a long-standing bug, not the recent PR). Conservative cutoffs in the default impl mitigate this but don't eliminate it.

Cost: a few extra `gh api` calls per PR to find follow-up PRs and read their diffs. No LLM cost.

### Use `LLMOracleEnrichment` when

- Your gold dataset is too sparse — many PRs with zero defects flagged, and you suspect there were defects humans missed.
- You're willing to accept a known noise source (the oracle hallucinates sometimes) in exchange for broader coverage.
- You have budget for Opus calls (roughly $0.10–$0.30 per PR, depending on PR size).
- You're going to spot-check the oracle's additions before accepting them — never use `--auto-accept` with `LLMOracleEnrichment` for a dataset you'll publish.

Both opt-in enrichments tag the `source` field on each `GoldDefect` so downstream consumers (or eval-time filters) can include or exclude them.

## The spot-check workflow

The spot-check is the single most important quality lever in the pipeline. The classifier will misclassify some comments — usually conversational ones it tags as defects, or the reverse. The spot-check is your chance to fix that before it pollutes the dataset.

### Interactive (default)

```bash
peer dataset add https://github.com/owner/repo/pull/N
```

Without `--auto-accept`, the workflow:

1. Fetches the PR + comments.
2. Classifies each comment.
3. Prints the proposed `GoldSample` (kept defects, dropped categories, original comment excerpts) for your review.
4. Prompts you to accept, edit, or reject.
5. On accept, stores via the configured `GoldSampleStorage`.

Use interactive for at least the first 20–30 samples in any new dataset, to build trust in the classifier's accuracy on *your* repo's comment style. The classifier's defaults are tuned against the OSS Python tone; your team's house style may need calibration.

### Batch with `--auto-accept`

```bash
peer dataset add https://github.com/owner/repo/pull/N --auto-accept
```

Skips the prompt. Use once you've built trust through interactive runs.

Recommended workflow for batch ingestion:

```bash
# Build a list of PRs to ingest (e.g., one per line in pr_urls.txt)
while read url; do
    peer dataset add "$url" --auto-accept --dataset dataset/my_team.jsonl
done < pr_urls.txt

# Then sanity-check what came out
peer dataset list --dataset dataset/my_team.jsonl --show-classifications
```

`peer dataset list --show-classifications` prints every defect's path, line, category, severity, and the first 80 chars of its description. Skimming the output for "this looks like discussion, not a defect" or "this is mis-severed" is much faster than running interactive on the whole batch.

For larger fixes, `peer dataset show <pr_url>` prints the full JSON record of a single sample for hand-editing.

## Cost notes

The default `LLMCommentClassifier` uses Haiku 4.5 with a single zero-shot call per raw comment. Order-of-magnitude:

- **Classifier:** ~$0.001 per raw comment with Haiku 4.5 (typical comment ~200 tokens in + ~100 out).
- **Full 30-sample reference dataset curation:** ~$0.20 end-to-end (and most of that is in the longer comments — the median is much cheaper).
- **`PostMergeBugfixCorrelation`:** no LLM cost; a few extra `gh api` calls per PR.
- **`LLMOracleEnrichment`:** ~$0.10–$0.30 per PR with Opus 4.7 (varies with PR size).

The disk cache (`~/.cache/peer/classifier_cache.jsonl`) means re-curating the same PR is free, so iteration on the dataset itself doesn't keep ringing up Haiku calls. Cache invalidates on taxonomy version change.

For a team-size dataset (say, 200–500 PRs), expect:

- Classification: $1–$5 with Haiku at default settings.
- Curation time: roughly 1–2 minutes per PR interactive, seconds per PR with `--auto-accept`.

The cost ceiling is dominated by `LLMOracleEnrichment` if you turn it on. Without it, dataset curation is roughly the cost of running a few cheap LLM calls per PR.

## What "done" looks like

A useful gold dataset for a real team is:

- **30–200 samples** across PRs that span the modules you care about
- **Spot-checked** — every defect was reviewed by a human at least once, even if the classifier proposed it
- **Versioned** — checked into git so you can `git log dataset/my_team.jsonl` to see how it's evolved
- **Tagged with `taxonomy_version`** in each `GoldSampleMetadata` so cross-version comparisons are honest
- **Mostly stable** between iterations — if every `peer eval` run gives wildly different numbers, the dataset is too small or too noisy

You'll never have a "complete" dataset. The point is to have one that's stable enough to detect signal in your reviewer iterations. Start small, spot-check rigorously for the first batch, then grow the dataset as you find PRs whose results in eval surprise you (those are the most valuable to add — they tell you where your reviewer's coverage is thinnest).

## Where to go next

- **The framework that consumes this dataset:** [`docs/framework_overview.md`](framework_overview.md)
- **Design rationale for every curation decision:** `openspec/changes/eval-v01/design.md` (Decisions 4, 5, 6, 13)
- **The shipped reference dataset for inspection:** `dataset/reference/django_pydantic_v1.jsonl` (`peer dataset list --dataset dataset/reference/django_pydantic_v1.jsonl --show-classifications`)
