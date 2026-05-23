## Why

We shipped `curate.py` (the data-collection script for gold-standard PR review data) but the framework has no actual review agent yet — `Agent.review()` is a `NotImplementedError` stub. To validate any of the eval methodology, we need a working agent that takes a PR and produces structured review comments. This is the minimum-viable proof that `peer`'s core abstraction holds.

## What Changes

- Implement `Agent.review(pr_url)` end-to-end: gathers context for the PR, calls the chosen LLM, parses structured review output, returns a `Review`.
- Implement PR context gathering: fetch the diff, surrounding code snippets, PR description, and prior discussion from a GitHub PR URL.
- Define canonical Pydantic schemas: `Review`, `Comment`, severity taxonomy (`critical`, `important`, `minor`, `nit`).
- Multi-LLM dispatch from day 1: Claude (Anthropic SDK) and OpenAI as initial backends, with the seam clean for adding local models.
- Optional CLI entry point: `python -m peer.review <pr_url>` to run a single review for smoke-testing.

## Capabilities

### New Capabilities
- `pr-review-agent`: the orchestrating agent that reads a PR's context, calls an LLM, and returns a structured `Review` with severity-tagged inline comments.
- `pr-context`: context-gathering layer that pulls diff, surrounding code, PR description, and prior discussion for any GitHub PR URL.

### Modified Capabilities
<!-- None — `specs/` is empty at this point; this proposal seeds the first specs. -->

## Impact

- **Code**: `src/peer/agent.py`, `src/peer/context.py` (currently stubs) get real implementations. New `src/peer/types.py` for shared Pydantic schemas. New `src/peer/review.py` for the CLI entry.
- **Dependencies**: `anthropic`, `openai`, `PyGithub` (already declared in `pyproject.toml`, not yet imported) get exercised.
- **No changes** to `curate.py`, README, or repo public surface yet. The CLI shape and README updates will follow once v0.1 is proven.
- **Out of scope for this change**: eval implementation (separate proposal), GitHub Action / webhook deployment, GitLab/Bitbucket support, observability integration.
