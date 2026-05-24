## ADDED Requirements

### Requirement: Strategy registry resolves built-in and dotted-path strategies

The framework SHALL define `peer.strategies.registry` with:

- `register_strategy(name: str, cls: type) -> None` — registers a Reviewer-shaped class under a short name
- `resolve_strategy(name_or_path: str) -> type` — returns the class for a short name (registry lookup) OR for a dotted Python path (importlib). On miss, raises `UnknownStrategy` (subclass of `PeerError`).

Built-in strategies SHALL pre-register at import: `draft_critique`, `two_model_pipeline`, `self_filter`.

#### Scenario: registry resolves a short name

- **WHEN** `resolve_strategy("draft_critique")` is called
- **THEN** the returned class is `peer.strategies.DraftCritiqueReviewer`

#### Scenario: registry resolves a dotted path

- **WHEN** `resolve_strategy("peer.strategies.SelfFilterReviewer")` is called
- **THEN** the returned class is `peer.strategies.SelfFilterReviewer`

#### Scenario: unknown name raises UnknownStrategy

- **WHEN** `resolve_strategy("not_a_real_strategy")` is called
- **THEN** `UnknownStrategy` is raised with a message listing the available short names

### Requirement: DraftCritiqueReviewer composes draft and critique passes

The `peer.strategies.DraftCritiqueReviewer` SHALL accept an `inner: Reviewer` (any Reviewer-Protocol-shaped object) and a `critique: Reviewer` (defaults to the same instance) plus `n_critique_rounds: int = 1`. On `review(...)`:

1. Call `inner.review(ctx, cc)` to produce a draft list of Comments.
2. For each critique round: pass the draft Comments + the ctx into a critique prompt; the critique pass returns a filtered/rewritten list. Strategy drops Comments the critique explicitly rejects; keeps Comments the critique passes through.
3. Return the final list + a merged `usage` dict (sum of input/output tokens; `model` set to "draft_critique").

The strategy SHALL surface `extra_user_message` + `run_context` kwargs from the outer call by forwarding them to the inner reviewer's first pass only (critique rounds use freshly-built prompts).

#### Scenario: DraftCritiqueReviewer drops comments the critique rejects

- **GIVEN** an inner TestReviewer that returns 3 fixed Comments and a critique reviewer that returns 1 of them
- **WHEN** `DraftCritiqueReviewer(inner=inner, critique=critique, n_critique_rounds=1).review(...)` is called
- **THEN** the returned Comments list has length 1

#### Scenario: usage aggregates input/output across passes

- **GIVEN** inner usage `{"input_tokens": 100, "output_tokens": 50}` and critique usage `{"input_tokens": 200, "output_tokens": 30}`
- **WHEN** DraftCritique returns
- **THEN** the merged usage's `input_tokens` is 300 and `output_tokens` is 80

### Requirement: TwoModelPipelineReviewer chains screen + detail passes

The `peer.strategies.TwoModelPipelineReviewer` SHALL accept a `screen: Reviewer` (cheap pass) and `detail: Reviewer` (expensive pass). On `review(...)`:

1. Call `screen.review(ctx, cc)` to produce a list of "candidate locations" — each screen Comment's `path`+`line`.
2. For each candidate, invoke `detail.review(...)` on a Context narrowed to that file/hunk. The detail pass produces the final Comment.
3. Return the union of detail-pass Comments; usage is the sum of screen + all detail calls.

When the screen returns an empty list, the strategy SHALL skip detail entirely (an empty Review with reason="screen pass produced no candidates").

#### Scenario: zero screen candidates skips detail

- **GIVEN** a screen reviewer that returns an empty Comments list
- **WHEN** TwoModelPipelineReviewer.review is called
- **THEN** the detail reviewer is never invoked
- **AND** the returned Review has `reason="screen pass produced no candidates"` and an empty comments list

### Requirement: SelfFilterReviewer drops low-confidence comments

The `peer.strategies.SelfFilterReviewer` SHALL accept an `inner: Reviewer`, an `inner_judge: Reviewer | LLMJudge` (defaults to constructing an `LLMJudge` over the inner's same model), and a `min_confidence: float = 0.5`. On `review(...)`:

1. Call `inner.review(ctx, cc)` for a draft.
2. For each draft Comment, score its "reputational confidence" via the judge (prompt asks "0.0–1.0: would you stake your reputation on this comment being correct?").
3. Drop Comments whose score < `min_confidence`. Return the kept list + summed usage.

The strategy SHALL log INFO when a Comment is dropped, including its path/line/severity and the judge's score.

#### Scenario: SelfFilter drops a Comment below the threshold

- **GIVEN** an inner returning 2 Comments and a stub judge returning scores [0.9, 0.3]
- **WHEN** SelfFilterReviewer(min_confidence=0.5).review is called
- **THEN** the returned Comments list has length 1
- **AND** the surviving Comment is the one with score 0.9

### Requirement: Recipe wires a strategy via reviewer_dotted_path + reviewer_kwargs

The `Recipe` SHALL gain two new fields:

- `reviewer_dotted_path: str | None = None` — when set, the recipe resolves this via `resolve_strategy(...)` and instantiates it via `cls(**reviewer_kwargs)`.
- `reviewer_kwargs: dict[str, Any] = {}` — kwargs forwarded to the strategy constructor. Values may include strings like `"inner: peer.reviewers.ClaudeReviewer"` that the recipe loader recursively resolves before construction.

When `reviewer_dotted_path` is `None`, the recipe constructs a bare `ClaudeReviewer` as before. The two fields SHALL round-trip through YAML cleanly.

#### Scenario: Recipe applies a strategy via short name

- **GIVEN** `Recipe(reviewer_dotted_path="draft_critique", reviewer_kwargs={"n_critique_rounds": 2})`
- **WHEN** the recipe is applied to a fresh Agent
- **THEN** `agent.reviewer` is an instance of `DraftCritiqueReviewer` with `n_critique_rounds == 2`
