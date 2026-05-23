## ADDED Requirements

### Requirement: GoldSample is the canonical curated unit

The framework SHALL define a `GoldSample` Pydantic model with at minimum: `pr_url`, `pr_metadata` (title / body / head_sha / merged_at), `gold_defects` (list[GoldDefect]), `metadata` (raw_comment_count / defect_comment_count / review_depth / has_followup_bugfix / curation_source / spot_checked), and `curated_at` timestamp.

Each `GoldDefect` SHALL have: `path`, `line` (or `line_range`), `category` (from configured Taxonomy), `severity`, `description` (normalized — not the raw human wording), `source` (e.g., `human_reviewer:<login>`, `post_merge_correlation`, `llm_oracle`), `confidence` (`high|medium|low`), and an optional `original_comment_excerpt`.

#### Scenario: Round-trip through JSONL

- **WHEN** a `GoldSample` is written to a JSONL line and read back via `JSONLStorage`
- **THEN** all fields round-trip with identical content (including nested `GoldDefect` list)

#### Scenario: Validation rejects malformed records

- **WHEN** a JSONL file contains a line that doesn't validate against the `GoldSample` schema
- **THEN** the loader raises `InvalidGoldSample` with the line number and the validation error, rather than silently dropping or corrupting

### Requirement: RawSampleSource Protocol with GitHub default

The framework SHALL define a `RawSampleSource` Protocol with `fetch(pr_url: str) -> RawSample` and ship `GitHubInlineCommentSource` as the default implementation. `GitHubInlineCommentSource` SHALL filter bot accounts (heuristic: login contains `bot` or ends with `[bot]`; known bot login list includes `github-actions`, `dependabot`, `coderabbit`, `greptile`, `qodo-ai`, `graphite-app`, `codium`).

#### Scenario: Fetch a public PR

- **WHEN** `GitHubInlineCommentSource().fetch("https://github.com/django/django/pull/17147")` is called
- **THEN** the returned `RawSample` includes PR metadata + all non-bot inline review comments + all non-bot issue comments

#### Scenario: Custom source

- **WHEN** a user implements `class JiraSource: def fetch(self, ticket_url): return RawSample(...)`
- **THEN** that class satisfies the `RawSampleSource` Protocol and can be passed to `Curator(source=JiraSource())`

### Requirement: CommentClassifier Protocol with LLM-based default

The framework SHALL define a `CommentClassifier` Protocol with `classify(comment: RawComment, pr_context: PRContext) -> Classification` and ship `LLMCommentClassifier` as the default implementation. The default classifier SHALL use Haiku 4.5 (or configurable model), accept a `Taxonomy` instance, and return a `Classification` with `category`, `severity`, `reasoning`.

#### Scenario: Classify a defect comment

- **WHEN** `LLMCommentClassifier().classify(raw_comment_with_body="this will dereference None when x is empty", pr_context=...)` is called
- **THEN** the returned `Classification` has `category="defect-correctness"` with a non-empty reasoning string

#### Scenario: Classify a discussion comment

- **WHEN** the input comment body is `"What information should I pass as context here to this custom error func?"`
- **THEN** the returned `Classification` has `category="discussion"` (and SHALL therefore be dropped from gold during the conversion to `GoldDefect`)

#### Scenario: Cached classification

- **WHEN** the same `(repo, comment_id)` pair is classified twice with the same Taxonomy
- **THEN** the second call returns from cache without invoking the LLM

#### Scenario: Cache invalidation on Taxonomy change

- **WHEN** the Taxonomy version changes (e.g., new category added) between two classify calls on the same comment
- **THEN** the second call re-invokes the LLM and produces a fresh classification

### Requirement: Taxonomy is configurable with a sensible default

The framework SHALL define a `Taxonomy` dataclass with fields `categories: list[CategoryDef]`, `severities: list[str]`, `drop_categories: list[str]` (categories that get dropped during gold construction), `nit_only_categories: list[str]` (categories kept but forced to nit severity), and `version: str`.

A `DefaultTaxonomy` SHALL be exported with the 8 categories defined in `design.md` Decision 4 (six defect categories, one style-nit, one discussion).

#### Scenario: Using a custom Taxonomy

- **WHEN** a user constructs `MyTaxonomy = Taxonomy(categories=[CategoryDef("bug"), CategoryDef("not-bug")], severities=["blocker", "minor"], drop_categories=["not-bug"], version="my-team-v1")`
- **THEN** that Taxonomy can be passed to `LLMCommentClassifier(taxonomy=MyTaxonomy)` and to `Curator(taxonomy=MyTaxonomy)`; the classifier prompt is regenerated to reflect the custom categories

### Requirement: EnrichmentStep Protocol with NoEnrichment default and named non-default impls

The framework SHALL define an `EnrichmentStep` Protocol with `enrich(sample: GoldSample, pr_context: PRContext) -> GoldSample`. The default implementation `NoEnrichment` SHALL pass the sample through unchanged. The module SHALL also export named non-default implementations: `PostMergeBugfixCorrelation` and `LLMOracleEnrichment`.

#### Scenario: Default is no-op

- **WHEN** `Curator()` is constructed without specifying enrichment
- **THEN** the curator uses `NoEnrichment`; resulting gold samples contain only human-derived defects

#### Scenario: PostMergeBugfixCorrelation adds defects

- **WHEN** `Curator(enrichment=PostMergeBugfixCorrelation()).add(pr_url)` is called for a PR that had a follow-up bugfix PR within 30 days touching the same files
- **THEN** the resulting `GoldSample` includes additional `GoldDefect` entries derived from the follow-up's diff with `source="post_merge_correlation"` and `confidence="medium"`

#### Scenario: LLMOracleEnrichment adds defects

- **WHEN** `Curator(enrichment=LLMOracleEnrichment(model="claude-opus-4-7")).add(pr_url)` is called
- **THEN** the strong model produces a defect list; only `confidence="high"` defects are added to gold with `source="llm_oracle"`

### Requirement: GoldSampleStorage Protocol with JSONL default

The framework SHALL define a `GoldSampleStorage` Protocol with at minimum `add(sample)`, `load_all() -> list[GoldSample]`, `find(pr_url) -> Optional[GoldSample]`, `delete(pr_url)`. The default implementation `JSONLStorage(path)` SHALL store one `GoldSample` per JSONL line, append-only for `add`, with deduplication-on-write (if `pr_url` exists, overwrite the prior line).

#### Scenario: Append and load

- **WHEN** two distinct samples are added via `storage.add(...)` and `storage.load_all()` is called
- **THEN** both samples are returned in insertion order with identical content

#### Scenario: Overwrite on duplicate add

- **WHEN** a sample is added, then a sample with the same `pr_url` (but different `gold_defects`) is added
- **THEN** `load_all()` returns one sample, with the contents of the second `add`

### Requirement: Curator orchestrates fetch -> classify -> enrich -> store

The framework SHALL provide a `Curator` class that composes a `RawSampleSource`, `CommentClassifier`, `EnrichmentStep`, `Taxonomy`, and `GoldSampleStorage` and exposes:

- `Curator.add(pr_url, auto_accept=False) -> GoldSample` — runs the pipeline for one PR
- `Curator.add_batch(pr_urls, auto_accept=False) -> list[GoldSample]`
- `Curator.preview(pr_url) -> ProposedSample` — runs fetch + classify + enrich but does NOT store, returns a preview for inspection

#### Scenario: Interactive add prompts for spot-check

- **WHEN** `Curator(...).add(pr_url, auto_accept=False)` is called and the classifier produced 3 defects + 2 dropped comments
- **THEN** the framework prints the proposed `GoldSample` and prompts the operator to accept/reject/edit; only on accept is the sample stored

#### Scenario: Auto-accept skips prompt

- **WHEN** `Curator(...).add(pr_url, auto_accept=True)` is called
- **THEN** the proposed `GoldSample` is stored directly without operator prompt, and the returned sample's `metadata.spot_checked` is `False`

#### Scenario: Preview without storing

- **WHEN** `Curator(...).preview(pr_url)` is called
- **THEN** the returned `ProposedSample` contains the classified comments and proposed gold defects but no write to storage has occurred

### Requirement: Curation never invents content

The classifier and enrichment steps SHALL only emit `GoldDefect.description` text grounded in either (a) the original human comment body, (b) the PR diff, or (c) the enrichment source (e.g., follow-up bugfix diff). The framework SHALL NOT generate hypothetical defects or rephrase comments to add information not present in sources.

#### Scenario: Description preserves human intent

- **WHEN** a raw human comment "this will dereference None when x is empty" is classified into a `GoldDefect`
- **THEN** the `description` is a normalized restatement that preserves the original technical claim; `original_comment_excerpt` carries the verbatim source for audit

#### Scenario: No hallucinated defects

- **WHEN** a PR has zero defect-class comments after classification and `NoEnrichment` is used
- **THEN** the resulting `GoldSample.gold_defects` is empty; the framework does NOT fabricate defects to fill the gap
