# Pydantic review conventions

**Sources** (publicly published, *not* derived from the gold dataset):
- Pydantic contributing guide (mkdocs): https://docs.pydantic.dev/latest/contributing/
- Pydantic README and contributor templates
- Standard Python community practice (PEP 8, PEP 257)

Distilled broadly — includes conventions that may not appear in any specific PR.

## Code style

- **Tooling:** linting via `ruff`. Run `make format` to apply formatting + lint fixes.
- **Docstring linting:** `pydocstyle` enforces PEP 257.
- **Type annotations required.** All function signatures, public class attributes, and instance attributes must have type annotations. Types in docstrings are *inferred* from the code — don't restate them in the docstring.
- **Standard Python good practice:** avoid mutable default arguments; avoid private CPython internals (anything underscore-prefixed in stdlib like `typing._GenericAlias`, `functools._lru_cache_wrapper`); avoid `assert` for runtime validation (gets stripped with `python -O`).

## Docstrings

- **Google-style docstrings** formatted per PEP 257.
- **All modules, classes, functions, and module-level variables need docstrings.**
- **Include runnable, self-contained code examples** in docstrings where applicable.
- **Docstring code examples are tested** (`pytest tests/test_docs.py --update-examples`). Make sure examples actually run and produce the output they claim.

## Tests

- New features need tests. Run `make` to execute the full test + linting suite.
- Pydantic v1 (legacy) accepts only bug and security fixes — target the `1.10.X-fixes` branch.
- Tests should not be tightly coupled to internal implementation details (e.g., asserting on the exact shape of a private `core_schema` dict). These tests break on refactors and obstruct iteration.

## Documentation (mkdocs)

- Build locally with `make docs`.
- Out-of-cycle documentation updates target the `docs-update` branch.
- Concept pages live under `docs/concepts/`; API reference auto-generated from docstrings.
- Use `!!! note`, `!!! info`, `!!! warning` mkdocs admonitions to call out edge cases, performance considerations, and when-not-to-use scenarios — not just happy-path usage.

## PR / commit / release conventions

- Create an issue first unless the change is trivial (typo, minor docs update).
- Follow the pull request template — describe the change, link issues.
- PR description should auto-close fixed issues: use `Fix #NNNN` or `Fixes #NNNN` (not just a bare issue link).
- Comment `please review` when ready for maintainer review.
- Bug fixes need release notes — handled via PR labels (e.g., `relnotes-bug`) in the current flow.

## General Python practice (applies to any well-maintained library)

- Avoid private API access from other libraries / stdlib (anything starting with `_`).
- Avoid mutable default args.
- Prefer immutable types for defaults where the intent is "empty" (`()` not `[]` if it's an `Iterable`).
- Be explicit about expensive-to-construct objects — document construction cost and reuse pattern when relevant.
