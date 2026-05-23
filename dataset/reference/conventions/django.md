# Django review conventions

**Sources** (publicly published, *not* derived from the gold dataset):
- Django coding style: https://docs.djangoproject.com/en/dev/internals/contributing/writing-code/coding-style/
- Django docs writing guide: https://docs.djangoproject.com/en/dev/internals/contributing/writing-documentation/
- Standard Python community practice (PEP 8, PEP 257)

Distilled broadly — includes conventions that may not appear in any specific PR. A team adopting peer for Django would write something like this from the same sources.

## Python code style

- **Line length:** code up to 88 chars (black default), docs/comments/docstrings 79 chars.
- **F-strings: plain variable and property access only.** `f"{user.name}"` is fine; `f"{get_user()}"`, `f"{user.age * 365.25}"`, `f"{d['key']}"` are not — bind to a local variable first.
- **Never use f-strings for translatable strings** (error messages, logging messages — they break translation extraction).
- **Naming:** `snake_case` for variables / functions / methods; `InitialCaps` for classes.
- **No `assert` for runtime validation.** `assert` is stripped under `python -O`. Raise a proper exception (`ValueError`, `ProgrammingError`, etc.) for runtime checks; reserve `assert` for tests.
- **Imports** organized by `black` + `isort`: stdlib, third-party, Django, app-local. `try/except` imports go as a separate group.

## Comments and docstrings

- **Avoid "we" in comments.** Use imperative: "Loop over" not "We loop over". "Check the status" not "We check the status".
- **PEP 257** for docstring style.
- **Comments should be complete sentences.** Don't leave thoughts trailing off.
- **Reserve ticket references for obscure context.** Include at the end of the docstring sentence: `"""A short description (#123456)."""`

## Tests

- **Use Django-specific assertion helpers** over their stdlib equivalents:
  - `self.assertRaisesMessage(Exc, msg)` over `self.assertRaises(Exc)` + manual message check
  - `self.assertWarnsMessage(W, msg)` over `self.assertWarns(W)`
  - `self.assertRaisesRegex` / `assertWarnsRegex` only when regex match is needed
  - `self.assertIs(x, True)` / `self.assertIs(x, False)` over `assertTrue` / `assertFalse` when checking exact boolean values
- **Test docstrings state the expected behavior directly.** Drop preambles like "Tests that", "Ensures that", "Test that". The fact that it's a test is implicit.
- **Tests added to a PR should be in scope for that PR.** Unrelated coverage improvements belong in a separate commit / PR.

## Documentation (ReST / `.txt`)

- **Wrap at 79–80 chars.** Exceptions allowed only when wrapping a code example would significantly hurt readability.
- **Sentence case for headings.** Capitalize only the first word and proper nouns.
- **Heading hierarchy:** `===` (1), `===` (2), `---` (3), `~~~` (4), `^^^` (5) underline characters.
- **Use semantic ReST roles**, not plain backticks:
  - `:mod:` `~django.contrib.auth` → "auth"
  - `:setting:` `INSTALLED_APPS`
  - `:ttag:`, `:tfilter:`, `:lookup:`, `:djadmin:` for templates / lookups / commands
  - `:doc:` `/ref/settings` for inter-doc links
  - `:ref:` `anchor-name` for section anchors
- **Code blocks:** `.. code-block:: <lang>` or `::` (shorter form for adjacent block).
- **Admonitions:** `.. admonition:: Title` preferred over `.. note::`.
- **`.. versionadded:: X.Y` / `.. versionchanged:: X.Y`** required for any new or changed public feature. Place at the *end* of the section, write self-contained content so the block could be removed in a future version without reflowing surrounding text.
- **No specific Django versions in prose outside versionadded / versionchanged blocks.**

## Release notes

- Use `versionadded` / `versionchanged` directives in docs to flag the change; release notes summarize.
- Assume readers run the latest release (not the development version).
- Reference relevant docs sections from release notes via `:ref:` — add anchors (`.. _section-name:`) to docs sections that release notes link to.

## Commit / PR conventions

- Commit message header: `Refs #NNNNN -- description` for cross-references, `Fixed #NNNNN -- description` for closing fixes. The `#` and `--` are required.
- One-line summary + optional body.

## Tooling (used by reviewers to mechanically check the above)

- `black` (code formatting), `isort` (imports), `flake8` (linting), `pre-commit` (hooks).
- Review comments often point to violations that the tooling would otherwise catch — treat tool failures as the same kind of feedback.
