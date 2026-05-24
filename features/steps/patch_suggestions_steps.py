"""Step definitions for features/patch_suggestions.feature."""

from __future__ import annotations

from behave import given, then, when  # type: ignore[import-untyped]
from pydantic import ValidationError

from peer.eval import SuggestionRate
from peer.types import Comment, Review

# ---------------------------------------------------------------------------
# Comment field extensions
# ---------------------------------------------------------------------------


@when("I construct a Comment without a suggestion")
def step_construct_comment_no_sugg(context) -> None:
    context.fixtures["comment"] = Comment(
        path="src/foo.py",
        line=10,
        severity="minor",
        body="b",
        rationale="r",
    )


@when('I construct a Comment with suggestion "{sugg}", issue_header "{hdr}", end_line {el:d}')
def step_construct_comment_full(context, sugg: str, hdr: str, el: int) -> None:
    context.fixtures["comment"] = Comment(
        path="src/foo.py",
        line=10,
        end_line=el,
        severity="important",
        body="b",
        rationale="r",
        suggestion=sugg,
        issue_header=hdr,
    )


@when("I attempt to construct a Comment with line {line:d} and end_line {el:d}")
def step_attempt_comment_invalid(context, line: int, el: int) -> None:
    try:
        Comment(
            path="src/foo.py",
            line=line,
            end_line=el,
            severity="minor",
            body="b",
            rationale="r",
        )
        context.error = None
    except Exception as e:
        context.error = e


@then("the Comment's suggestion is None")
def step_comment_sugg_none(context) -> None:
    assert context.fixtures["comment"].suggestion is None


@then("the Comment's issue_header is None")
def step_comment_hdr_none(context) -> None:
    assert context.fixtures["comment"].issue_header is None


@then("the Comment's end_line is None")
def step_comment_el_none(context) -> None:
    assert context.fixtures["comment"].end_line is None


@then('the Comment\'s suggestion equals "{val}"')
def step_comment_sugg_equals(context, val: str) -> None:
    assert context.fixtures["comment"].suggestion == val


@then('the Comment\'s issue_header equals "{val}"')
def step_comment_hdr_equals(context, val: str) -> None:
    assert context.fixtures["comment"].issue_header == val


@then("the Comment's end_line equals {n:d}")
def step_comment_el_equals(context, n: int) -> None:
    assert context.fixtures["comment"].end_line == n


@then("the Comment round-trips through model_dump_json + model_validate_json")
def step_comment_roundtrip(context) -> None:
    cmt = context.fixtures["comment"]
    raw = cmt.model_dump_json()
    loaded = Comment.model_validate_json(raw)
    assert loaded == cmt


@then("a ValidationError is raised")
def step_validation_error_raised(context) -> None:
    assert isinstance(context.error, ValidationError), (
        f"expected ValidationError, got {type(context.error).__name__}: {context.error!r}"
    )


# ---------------------------------------------------------------------------
# SuggestionRate
# ---------------------------------------------------------------------------


@given("a Review with 4 comments — 2 with suggestion, 2 without")
def step_given_review_4_2_2(context) -> None:
    comments = [
        Comment(path="a.py", line=1, severity="minor", body="b", rationale="r", suggestion="x = 1"),
        Comment(path="b.py", line=1, severity="minor", body="b", rationale="r"),
        Comment(path="c.py", line=1, severity="minor", body="b", rationale="r", suggestion="y = 2"),
        Comment(path="d.py", line=1, severity="minor", body="b", rationale="r"),
    ]
    context.fixtures["review"] = Review(comments=comments)


@given("a Review with 0 comments")
def step_given_review_empty(context) -> None:
    context.fixtures["review"] = Review(comments=[])


@when("I score with SuggestionRate")
def step_score_suggestion_rate(context) -> None:
    from peer.dataset.types import GoldSample

    sample = GoldSample(pr_url="https://example/pr/1", pr_title="t")
    metric = SuggestionRate()
    context.fixtures["result"] = metric.score(sample, context.fixtures["review"])


@then("the per-sample value equals {v:f}")
def step_per_sample_value_equals(context, v: float) -> None:
    got = context.fixtures["result"].value
    assert got is not None and abs(got - v) < 1e-9, f"expected {v}, got {got}"


@then("the per-sample value is None")
def step_per_sample_value_none(context) -> None:
    assert context.fixtures["result"].value is None
