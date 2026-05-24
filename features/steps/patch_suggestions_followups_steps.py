"""Step definitions for features/patch_suggestions_followups.feature (peer-5is).

Covers tool-schema extension, default prompt language, CLI rendering, and
SuggestionRate joining the default metric set.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from behave import given, then, when  # type: ignore[import-untyped]

from peer import ClaudeReviewer, Comment, Review, TestReviewer
from peer.cli import _format_review_output
from peer.eval.runner import EvalRunner
from peer.types import Context, ContextHunk

# ---------------------------------------------------------------------------
# Tool schema
# ---------------------------------------------------------------------------


@when("I import _COMMENT_TOOL from peer.reviewers")
def step_import_tool(context) -> None:
    from peer.reviewers import _COMMENT_TOOL

    context.fixtures["tool"] = _COMMENT_TOOL


def _comment_item_props(tool: dict) -> dict:
    return tool["input_schema"]["properties"]["comments"]["items"]["properties"]


def _comment_item_required(tool: dict) -> list[str]:
    return tool["input_schema"]["properties"]["comments"]["items"]["required"]


@then('the tool schema\'s input properties include "{name}"')
def step_tool_has_prop(context, name: str) -> None:
    props = _comment_item_props(context.fixtures["tool"])
    assert name in props, f"{name!r} missing — have {list(props)}"


@then('the "{name}" property is described as nullable')
def step_prop_nullable(context, name: str) -> None:
    props = _comment_item_props(context.fixtures["tool"])
    spec = props[name]
    t = spec.get("type")
    if isinstance(t, list):
        assert "null" in t, f"{name!r} type={t!r} not nullable"
    else:
        # "string" alone is not nullable — fail unless format explicitly allows null
        raise AssertionError(f"{name!r} has type={t!r}; expected nullable list-of-types")


@then('the required fields list does NOT include "{name}"')
def step_not_required(context, name: str) -> None:
    req = _comment_item_required(context.fixtures["tool"])
    assert name not in req, f"{name!r} unexpectedly in required={req}"


# ---------------------------------------------------------------------------
# ClaudeReviewer parses new fields
# ---------------------------------------------------------------------------


@given(
    "a ClaudeReviewer whose client returns one tool-use comment with suggestion "
    '"{suggestion}" and issue_header "{header}" and end_line {end_line:d}'
)
def step_reviewer_returns_full(context, suggestion: str, header: str, end_line: int) -> None:
    # Construct without anthropic API key
    with patch("anthropic.Anthropic"):
        rv = ClaudeReviewer(model="anthropic:claude-sonnet-4-6")

    # Build a fake response with one tool_use block.
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "post_review_comments"
    decoded_suggestion = suggestion
    tool_block.input = {
        "comments": [
            {
                "path": "src/foo.py",
                "line": 10,
                "end_line": end_line,
                "severity": "minor",
                "body": "b",
                "rationale": "r",
                "issue_header": header,
                "suggestion": decoded_suggestion,
            }
        ]
    }
    resp = MagicMock()
    resp.content = [tool_block]
    resp.usage.input_tokens = 1
    resp.usage.output_tokens = 1
    rv.client.messages.create.return_value = resp  # type: ignore[attr-defined]
    context.fixtures["reviewer"] = rv


@when("I invoke the Reviewer on a synthetic Context")
def step_invoke_reviewer_full(context) -> None:
    ctx = Context(
        pr_url="x",
        owner="o",
        repo="r",
        number=1,
        title="t",
        body="",
        head_sha="s",
        hunks=[
            ContextHunk(
                path="src/foo.py",
                old_start=10,
                old_lines=2,
                new_start=10,
                new_lines=5,
                diff_text="@@ -10,2 +10,5 @@\n line\n line\n line\n line\n line",
            )
        ],
        prior_comments=[],
        token_estimate=0,
    )
    comments, _usage = context.fixtures["reviewer"].review(ctx, None)
    context.fixtures["parsed_comments"] = comments


@then("the returned Comment list has length {n:d}")
def step_comment_list_len(context, n: int) -> None:
    got = len(context.fixtures["parsed_comments"])
    assert got == n, f"expected {n}, got {got}"


@then('the first Comment\'s suggestion equals "{val}"')
def step_first_suggestion(context, val: str) -> None:
    got = context.fixtures["parsed_comments"][0].suggestion
    assert got == val, f"expected {val!r}, got {got!r}"


@then('the first Comment\'s issue_header equals "{val}"')
def step_first_header(context, val: str) -> None:
    got = context.fixtures["parsed_comments"][0].issue_header
    assert got == val, f"expected {val!r}, got {got!r}"


@then("the first Comment's end_line equals {n:d}")
def step_first_endline(context, n: int) -> None:
    got = context.fixtures["parsed_comments"][0].end_line
    assert got == n, f"expected {n}, got {got!r}"


# ---------------------------------------------------------------------------
# DEFAULT_SYSTEM_PROMPT
# ---------------------------------------------------------------------------


@when("I import DEFAULT_SYSTEM_PROMPT from peer.prompts")
def step_import_prompt(context) -> None:
    from peer.prompts import DEFAULT_SYSTEM_PROMPT

    context.fixtures["prompt"] = DEFAULT_SYSTEM_PROMPT


@then('the prompt mentions the word "{word}"')
def step_prompt_mentions(context, word: str) -> None:
    text = context.fixtures["prompt"]
    assert word in text, f"{word!r} not found in DEFAULT_SYSTEM_PROMPT"


@then('the prompt mentions "{word}"')
def step_prompt_mentions2(context, word: str) -> None:
    text = context.fixtures["prompt"]
    assert word in text, f"{word!r} not found in DEFAULT_SYSTEM_PROMPT"


@then(
    "the prompt describes when NOT to include a suggestion "
    '(e.g. "consider refactoring" / large rewrites)'
)
def step_prompt_describes_when_not(context) -> None:
    text = context.fixtures["prompt"]
    lower = text.lower()
    # Accept either of the listed cue phrases; the spirit is "negative guidance present".
    assert any(
        cue in lower for cue in ("consider refactoring", "large rewrites", "do not include")
    ), "DEFAULT_SYSTEM_PROMPT missing negative-guidance language about when NOT to suggest"


# ---------------------------------------------------------------------------
# CLI rendering
# ---------------------------------------------------------------------------


def _review_with_one(**comment_kwargs) -> Review:  # type: ignore[no-untyped-def]
    base = dict(
        path="src/foo.py",
        line=10,
        severity="minor",
        body="something is off here",
        rationale="because reasons",
    )
    base.update(comment_kwargs)
    return Review(
        comments=[Comment(**base)],
        usage={"input_tokens": 1, "output_tokens": 1, "model": "test"},
    )


@given('a Review with one Comment carrying a suggestion "{val}"')
def step_review_with_suggestion(context, val: str) -> None:
    context.fixtures["review"] = _review_with_one(suggestion=val)


@given("a Review with one Comment that has no suggestion")
def step_review_no_suggestion(context) -> None:
    context.fixtures["review"] = _review_with_one()


@given('a Review with one Comment with issue_header "{val}"')
def step_review_with_header(context, val: str) -> None:
    context.fixtures["review"] = _review_with_one(issue_header=val)


@when("I render the Review via _format_review_output")
def step_render_review(context) -> None:
    out = _format_review_output(context.fixtures["review"], "https://github.com/test/test/pull/1")
    context.fixtures["rendered"] = out


@then('the rendered output contains "{needle}"')
def step_rendered_contains(context, needle: str) -> None:
    assert needle in context.fixtures["rendered"], (
        f"{needle!r} not found in rendered output:\n{context.fixtures['rendered']}"
    )


@then('the rendered output does NOT contain "{needle}"')
def step_rendered_not_contains(context, needle: str) -> None:
    assert needle not in context.fixtures["rendered"], (
        f"{needle!r} unexpectedly found in rendered output"
    )


# ---------------------------------------------------------------------------
# Default metrics
# ---------------------------------------------------------------------------


@given("a minimal EvalRunner constructed with a TestReviewer and an empty dataset")
def step_minimal_runner(context) -> None:
    runner = EvalRunner(reviewer=TestReviewer(), dataset=[])
    context.fixtures["runner"] = runner


@then('the runner\'s default metrics list contains a metric named "{name}"')
def step_runner_metric_present(context, name: str) -> None:
    runner: EvalRunner = context.fixtures["runner"]
    names = [m.name for m in runner.metrics]
    assert name in names, f"{name!r} not in default metrics={names}"
