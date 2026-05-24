"""Build dataset/reference/django_pydantic_v2.jsonl from manual classifications.

The keys of MANUAL are PR URLs; the values are lists of (comment_idx, category,
severity, description) tuples — comments not listed are DROPPED from gold.

If description is None, a normalized version of the original comment body is
used. Otherwise the supplied description is used verbatim.

Source: scripts/build_v2_dataset.py (this file, hand-curated 2026-05-23
based on inspection of /tmp/raw_30prs.txt).

Run: .venv/bin/python scripts/build_v2_dataset.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from peer.dataset import GitHubInlineCommentSource, JSONLStorage
from peer.dataset.types import (
    GoldDefect,
    GoldSample,
    GoldSampleMetadata,
    RawSample,
)

logging.basicConfig(level=logging.WARNING)

# (category, severity, optional_description_override)
Classification = tuple[str, str, str | None]

MANUAL: dict[str, list[tuple[int, str, str, str | None]]] = {
    # PRs with all comments dropped are absent from this dict OR map to [].
    # ------------------------- pydantic ------------------------------
    "https://github.com/pydantic/pydantic/pull/7625": [],
    "https://github.com/pydantic/pydantic/pull/7528": [],
    "https://github.com/pydantic/pydantic/pull/7677": [
        (
            4,
            "defect-correctness",
            "important",
            "Reviewer suggests adding a check for whether the root field has a default value; the current logic may not handle the no-default case correctly.",
        ),
    ],
    "https://github.com/pydantic/pydantic/pull/7527": [
        (
            0,
            "defect-doc-gap",
            "minor",
            "Reviewer requests an explanatory comment for the winding logic so future readers can follow the motivation.",
        ),
    ],
    "https://github.com/pydantic/pydantic/pull/7415": [],
    "https://github.com/pydantic/pydantic/pull/7566": [],
    "https://github.com/pydantic/pydantic/pull/7435": [
        (
            1,
            "defect-correctness",
            "important",
            "Type refs do not reflect generic parameters, so two different schemas can share the same ref and produce incorrect parameter resolution.",
        ),
    ],
    "https://github.com/pydantic/pydantic/pull/7589": [
        (
            0,
            "style-nit",
            "nit",
            "Use an empty tuple in place of the current Iterable initialization for clarity / minimal overhead.",
        ),
    ],
    "https://github.com/pydantic/pydantic/pull/7979": [],
    "https://github.com/pydantic/pydantic/pull/8190": [],
    "https://github.com/pydantic/pydantic/pull/7626": [
        (
            1,
            "defect-test-gap",
            "important",
            "New config flag should have at least one test; please add coverage before merging.",
        ),
        (
            7,
            "defect-doc-gap",
            "nit",
            "PR description should reference the fixed issue with `Fix #6498` so the issue auto-closes on merge.",
        ),
    ],
    "https://github.com/pydantic/pydantic/pull/7900": [
        (
            0,
            "defect-doc-gap",
            "important",
            "Docstring describes the `type` parameter as a Python type but TypeAdapter also accepts pydantic models, TypedDicts, etc. Docstring should reflect that.",
        ),
        (
            1,
            "defect-doc-gap",
            "important",
            "Docstring should mention that `config` cannot be used when the type already has its own config (e.g. a BaseModel).",
        ),
    ],
    "https://github.com/pydantic/pydantic/pull/8059": [
        (
            0,
            "style-nit",
            "nit",
            "Grammar fix: remove the 'needing to create a' fragment for cleaner sentence flow.",
        ),
        (
            1,
            "defect-doc-gap",
            "minor",
            "Rename example variable from `UserListValidator` to `UserListAdapter` so the docs convey TypeAdapter's broader capability beyond validation.",
        ),
        (
            2,
            "defect-doc-gap",
            "important",
            "Add a !!! note clarifying that TypeAdapter should not be used as a type annotation for BaseModel fields, to avoid misuse.",
        ),
        (3, "style-nit", "nit", "Capitalization: 'Type Adapter' (with space) for nav consistency."),
        (
            5,
            "defect-doc-gap",
            "important",
            "Add a !!! info block on performance considerations: TypeAdapter construction is expensive, callers should reuse instances.",
        ),
    ],
    "https://github.com/pydantic/pydantic/pull/7889": [],
    "https://github.com/pydantic/pydantic/pull/8012": [
        (2, "defect-doc-gap", "minor", "Add a small release-note entry for this bug fix."),
    ],
    "https://github.com/pydantic/pydantic/pull/8442": [
        (
            0,
            "defect-correctness",
            "important",
            "Behavior issue: SecretStr('') prints as '' rather than being masked. Reviewer's suggested example documents this, but the underlying redaction behavior for empty secrets should be verified or fixed.",
        ),
    ],
    # ------------------------- django --------------------------------
    "https://github.com/django/django/pull/17280": [],
    "https://github.com/django/django/pull/17223": [],
    "https://github.com/django/django/pull/17314": [
        (
            1,
            "defect-test-gap",
            "minor",
            "Reviewer suggests reusing the existing model in the test for `test_db_type_parameters` rather than creating a new fixture, reducing test redundancy.",
        ),
    ],
    "https://github.com/django/django/pull/17171": [
        (
            0,
            "defect-correctness",
            "important",
            "Third-party DB backends may still implement field_cast_sql(); the code should call it when present and emit a deprecation warning instead of unconditionally skipping it.",
        ),
    ],
    "https://github.com/django/django/pull/17182": [],
    "https://github.com/django/django/pull/17147": [
        (
            0,
            "defect-api-design",
            "minor",
            "If this is a single-pass design, prefer defining a local async function over adding another method on self.",
        ),
        (
            7,
            "defect-correctness",
            "important",
            "ResourceWarning: unclosed SpooledTemporaryFile in asgi tests on Python 3.12. The test infrastructure is leaking the temporary body file.",
        ),
        (
            8,
            "defect-test-gap",
            "minor",
            "Added tests pass without the patch under review; extra test coverage should land as a separate commit/PR.",
        ),
        (
            9,
            "style-nit",
            "nit",
            "Typo in test comment — 'forces' should be 'force' to match the plural subject.",
        ),
        (
            10,
            "style-nit",
            "nit",
            "Django style: omit prefixes like 'This test', 'Ensure', 'Test' in test docstrings.",
        ),
        (11, "style-nit", "nit", "Remove the orphan documentation code block."),
        (
            12,
            "style-nit",
            "nit",
            "Wrap documentation text at 79 characters per project convention.",
        ),
        (13, "style-nit", "nit", "Django docs convention: omit semicolons."),
        (14, "style-nit", "nit", "Django comment style: omit 'We' in comments."),
        (
            15,
            "style-nit",
            "nit",
            "Django doesn't use typing annotations, so the type-ignore suppression comment can be removed.",
        ),
        (
            17,
            "defect-correctness",
            "important",
            "ResourceWarning: unclosed SpooledTemporaryFile in `test_assert_in_listen_for_disconnect` on Python 3.12. Same root cause as the other ResourceWarning above.",
        ),
    ],
    "https://github.com/django/django/pull/17637": [
        (
            0,
            "defect-test-gap",
            "minor",
            "Test should assert `repr(OGRGeomType('point')) == '<OGRGeomType: Point>'` to verify the actual output format being added.",
        ),
        (
            1,
            "style-nit",
            "nit",
            "Use `self.__class__.__qualname__` instead of `__name__` for more precise class representation in __repr__.",
        ),
    ],
    "https://github.com/django/django/pull/17312": [],
    "https://github.com/django/django/pull/17256": [
        (
            0,
            "defect-doc-gap",
            "minor",
            "Docs should make it explicit that functools.cache decorator support is intentionally supported, not implicit, to help readers understand the design intent.",
        ),
        (
            1,
            "style-nit",
            "nit",
            "Release-notes wording: drop the redundant 'Migrations now' prefix since the section title already specifies Migrations context.",
        ),
        (
            3,
            "defect-doc-gap",
            "important",
            "Nested items in the migrations docs are rendering incorrectly (visible in the linked screenshot). Fix the RST nesting.",
        ),
        (
            6,
            "defect-doc-gap",
            "minor",
            "Release-notes line has malformed markdown — unclosed backtick in 'Migrations now support serialization of functions...'.",
        ),
        (
            9,
            "style-nit",
            "nit",
            "Django release-notes convention: use present tense, not past tense.",
        ),
    ],
    "https://github.com/django/django/pull/16746": [
        (
            1,
            "defect-doc-gap",
            "minor",
            "New docs are nearly identical to the existing forms-fields error-messages docs; reduce duplication or unify.",
        ),
        (
            2,
            "style-nit",
            "nit",
            "Use shorter dict keys (e.g. 'invalid_page') for cleaner, more maintainable code.",
        ),
        (
            3,
            "defect-doc-gap",
            "important",
            "Missing `versionadded:: 5.0` annotation. Also document the available error_messages keys and add release notes for the new customization feature.",
        ),
        (
            4,
            "style-nit",
            "nit",
            "Test refactor: extract the expected error message into a variable for readability.",
        ),
    ],
    "https://github.com/django/django/pull/16603": [
        (
            2,
            "defect-correctness",
            "minor",
            "Reviewer indicates this line does not appear to be needed.",
        ),
        (
            3,
            "defect-api-design",
            "minor",
            "Simplify control flow: prefer a `pass` and falling through to the next code rather than nesting everything under the except block.",
        ),
        (
            4,
            "defect-performance",
            "important",
            "Pausing 0.05s on every request adds significant latency to the happy path (no disconnect) to detect the deviant case. Prefer get_nowait() or restructure so the pause only happens on the disconnect branch.",
        ),
        (
            7,
            "defect-correctness",
            "important",
            "RequestAborted is raised and the function returns None, but the expected TimeoutError is never raised — the send_response task is still pending when RequestAborted fires, so the test does not actually exercise the timeout path.",
        ),
        (
            8,
            "defect-api-design",
            "important",
            "Architectural redirection: the current structure still runs the view synchronously and only checks for disconnect before sending. The reviewer wants the view itself wrapped in a concurrent task so disconnects can interrupt a long-running request.",
        ),
        (
            9,
            "defect-correctness",
            "important",
            "asyncio.wait() is non-deterministic about which task runs first; forcing signal_to_start_request to await sleep is being used as a workaround. The race condition needs a proper fix, not a sleep-based workaround.",
        ),
        (
            11,
            "defect-api-design",
            "minor",
            "`disconnect_and_get_response` can just be inlined here — it's not reused elsewhere and the extra function obscures the flow.",
        ),
        (
            12,
            "defect-correctness",
            "important",
            "Loop is unnecessary per ASGI spec: only a single http.disconnect event is allowed after body processing, so at most one event will arrive. Simplify to a single receive.",
        ),
        (
            13,
            "defect-api-design",
            "important",
            "Code structure is too complex: the `zip(...)` is overkill. Use `asyncio.create_task(...)` instead of `ensure_future(...)`, and write the tasks list directly without the zip.",
        ),
        (
            14,
            "defect-test-gap",
            "important",
            "Pending task may need to be cancelled. There should be a test that exercises a view cleaning up after itself on disconnect; this is also user-facing documentation material.",
        ),
        (
            16,
            "defect-test-gap",
            "important",
            "Refactor the test: put the slow `time.sleep(...)` inside a view function in urls.py, not inline in the test, so the test can send the disconnect before the view finishes (matching the real disconnect-during-long-view scenario).",
        ),
        (
            19,
            "defect-api-design",
            "minor",
            "Design choice: prefer letting the assertion-style programming error propagate uncaught (re-raised) rather than catching it as RequestAborted, since this would only happen on a buggy protocol server.",
        ),
        (21, "style-nit", "nit", "Format the docstring on a single line per Django style."),
        (
            22,
            "defect-correctness",
            "important",
            "Use a proper exception (ProgrammingError / ValueError) for runtime validation rather than `assert`, which is stripped when Python runs with -O.",
        ),
        (
            23,
            "style-nit",
            "nit",
            "Django style guideline: f-strings should use only plain variable and property access, not complex expressions.",
        ),
        (24, "style-nit", "nit", "Comment wording fix per Django style."),
        (
            25,
            "style-nit",
            "nit",
            "Section heading: use 'Handling disconnects' per project convention.",
        ),
        (
            26,
            "defect-doc-gap",
            "important",
            "Documentation missing `versionadded:: 5.0` directive for the new feature.",
        ),
        (27, "style-nit", "nit", "Docs wording fix to improve flow."),
        (
            28,
            "defect-doc-gap",
            "important",
            "Release notes should reference this docs section so readers can find the full explanation.",
        ),
        (
            29,
            "style-nit",
            "nit",
            "Test docstring convention: state the expected behavior, omit prefixes like 'Test a' / 'Check'.",
        ),
        (30, "style-nit", "nit", "Use an f-string for the response string per Django style."),
        (
            33,
            "defect-doc-gap",
            "important",
            "Add an explicit RST anchor (`.. _async-handling-disconnect:`) to this section and reference it via `:ref:` in the release notes.",
        ),
    ],
    "https://github.com/django/django/pull/16637": [],
    "https://github.com/django/django/pull/17218": [
        (
            0,
            "defect-correctness",
            "minor",
            "Reviewer confirms OSError handling is still relevant (per linked colorama source and Django ticket #32740), implying the current code's broader exception handling shouldn't be narrowed.",
        ),
    ],
    "https://github.com/django/django/pull/16870": [
        (
            1,
            "defect-doc-gap",
            "nit",
            "Commit message is missing the `#` prefix on the issue reference; convention is `Refs #34343 -- ...`.",
        ),
    ],
}


def _normalize_description(body: str) -> str:
    """Trim whitespace + collapse multiple newlines + cap length."""
    text = " ".join(body.split())
    if len(text) > 400:
        text = text[:400] + "..."
    return text


def build_sample(
    raw: RawSample,
    classifications: list[tuple[int, str, str, str | None]],
) -> GoldSample:
    gold_defects: list[GoldDefect] = []
    for idx, category, severity, desc_override in classifications:
        if idx >= len(raw.comments):
            print(f"WARN: comment index {idx} out of range for {raw.pr_url}", file=sys.stderr)
            continue
        c = raw.comments[idx]
        # Issue comments have no anchor — store with empty path/line=0 so the
        # schema accepts them, but they'll match poorly against peer comments.
        # Skip issue comments unless explicitly marked.
        if not c.path and category != "defect-doc-gap":
            # If a defect must be anchored to a file and there's no path,
            # we have no honest way to anchor — skip.
            print(
                f"WARN: dropping idx {idx} for {raw.pr_url} (no path, category {category})",
                file=sys.stderr,
            )
            continue
        description = desc_override if desc_override else _normalize_description(c.body)
        gold_defects.append(
            GoldDefect(
                path=c.path or "(pr-metadata)",
                line=c.line,
                category=category,
                severity=severity,
                description=description,
                source=f"human_reviewer:{c.author}",
                confidence="high",
                original_comment_excerpt=c.body[:300],
            )
        )
    return GoldSample(
        pr_url=raw.pr_url,
        pr_title=raw.pr_title,
        pr_body=raw.pr_body,
        head_sha=raw.head_sha,
        merged_at=raw.merged_at,
        gold_defects=gold_defects,
        metadata=GoldSampleMetadata(
            raw_comment_count=len(raw.comments),
            defect_comment_count=len(gold_defects),
            review_depth=(
                "thorough"
                if len(raw.comments) > 8
                else "normal"
                if len(raw.comments) > 2
                else "light"
                if len(raw.comments) > 0
                else "none"
            ),
            curation_source="manual_orchestrator_v2",
            spot_checked=True,
            taxonomy_version="default-v1",
        ),
    )


def main() -> int:
    out_path = Path("dataset/reference/django_pydantic_v2.jsonl")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Overwrite cleanly
    if out_path.exists():
        out_path.unlink()
    storage = JSONLStorage(out_path)
    source = GitHubInlineCommentSource()

    pr_urls = list(MANUAL.keys())
    print(f"Building v2 dataset from {len(pr_urls)} PRs...")

    summary = {"prs": 0, "defects": 0, "by_category": {}}
    for url in pr_urls:
        try:
            raw = source.fetch(url)
        except Exception as e:
            print(f"FAIL fetch {url}: {e}", file=sys.stderr)
            continue
        sample = build_sample(raw, MANUAL[url])
        storage.add(sample)
        summary["prs"] += 1
        summary["defects"] += len(sample.gold_defects)
        for d in sample.gold_defects:
            summary["by_category"][d.category] = summary["by_category"].get(d.category, 0) + 1

    print(f"\n=== v2 dataset built at {out_path} ===")
    print(f"  PRs:     {summary['prs']}")
    print(f"  Defects: {summary['defects']}")
    print("  By category:")
    for k, v in sorted(summary["by_category"].items(), key=lambda x: -x[1]):
        print(f"    {k:25s} {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
