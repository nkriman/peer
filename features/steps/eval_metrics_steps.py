"""Step definitions for features/eval_metrics.feature.

Covers eval-metrics-v01 user-facing behaviors. Uses a stub Reviewer + stub
match-pair logic so steps run in <100ms with no LLM calls.
"""

from __future__ import annotations

import io
import warnings
from contextlib import redirect_stdout
from dataclasses import dataclass, field
from typing import Optional
from unittest.mock import patch

from behave import given, then, when  # type: ignore[import-untyped]

from peer.dataset.types import GoldDefect, GoldSample
from peer.eval import (
    CommentsPerPR,
    DetectionRate,
    EvalReport,
    EvalRunner,
    MeanPerPRRecall,
    render_summary,
)
from peer.types import Comment, Review

# ---------------------------------------------------------------------------
# Stub Reviewer — deterministic, no LLM
# ---------------------------------------------------------------------------


@dataclass
class _StubReviewer:
    """Returns fixed Comments per pr_url. Set via context.fixtures['per_pr_comments']."""

    per_pr_comments: dict[str, list[Comment]] = field(default_factory=dict)
    model: str = "stub:test"

    def review(self, pr_url: str) -> Review:
        comments = self.per_pr_comments.get(pr_url, [])
        return Review(
            comments=list(comments),
            usage={"input_tokens": 0, "output_tokens": 0, "model": self.model},
        )


def _make_synthetic_dataset(
    spec: list[tuple[int, int, int]],
) -> tuple[list[GoldSample], dict[str, list[Comment]]]:
    """Build a synthetic dataset.

    spec is a list of (matched_count, gold_count, peer_comment_count). Each
    entry produces one GoldSample; peer comments are matchable up to
    matched_count (rest are novel).
    """
    samples: list[GoldSample] = []
    per_pr_comments: dict[str, list[Comment]] = {}
    for i, (matched, gold_n, peer_n) in enumerate(spec):
        pr_url = f"https://github.com/test/test/pull/{i + 1}"
        defects = [
            GoldDefect(
                path="src/foo.py",
                line=10 + j,
                category="defect-correctness",
                severity="important",
                description=f"gold defect {i}.{j}",
                source="test",
            )
            for j in range(gold_n)
        ]
        samples.append(
            GoldSample(
                pr_url=pr_url,
                pr_title=f"PR {i}",
                gold_defects=defects,
            )
        )
        comments: list[Comment] = []
        # First `matched` peer comments share path+line with the first gold defects
        for j in range(matched):
            comments.append(
                Comment(
                    path="src/foo.py",
                    line=10 + j,
                    severity="important",
                    body=f"peer comment for matching gold {i}.{j}",
                    rationale="r",
                )
            )
        # Remaining peer_n - matched are novel (different lines)
        for j in range(peer_n - matched):
            comments.append(
                Comment(
                    path="src/bar.py",
                    line=100 + j,
                    severity="minor",
                    body=f"novel peer comment {i}.{j}",
                    rationale="r",
                )
            )
        per_pr_comments[pr_url] = comments
    return samples, per_pr_comments


# Always-True judge — bypasses real LLM judging. Patched into the metrics module.
_TRUE_JUDGE = lambda peer, gold, client=None: (  # noqa: E731
    peer.path == gold.path and (peer.line == gold.line if peer.line and gold.line else True)
)


# ---------------------------------------------------------------------------
# Background
# ---------------------------------------------------------------------------


@given("a synthetic dataset of three GoldSamples covering varied gold-defect counts")
def step_synthetic_dataset(context) -> None:
    # Matched_count, gold_count, peer_comment_count per sample
    spec = [(1, 3, 2), (0, 1, 0), (2, 5, 3)]
    samples, per_pr = _make_synthetic_dataset(spec)
    context.fixtures["samples"] = samples
    context.fixtures["per_pr_comments"] = per_pr


@given("a stub Reviewer that returns deterministic Comments per sample")
def step_stub_reviewer(context) -> None:
    context.fixtures["reviewer"] = _StubReviewer(
        per_pr_comments=context.fixtures["per_pr_comments"]
    )


@given("a dataset where samples have matched_count [2, 0, 1] and total_gold [10, 0, 5]")
def step_specific_dataset(context) -> None:
    spec = [(2, 10, 2), (0, 0, 0), (1, 5, 1)]
    samples, per_pr = _make_synthetic_dataset(spec)
    context.fixtures["samples"] = samples
    context.fixtures["reviewer"] = _StubReviewer(per_pr_comments=per_pr)


@given("a dataset where the stub Reviewer emits [1, 3, 5, 2, 0] comments across five samples")
def step_dataset_with_comment_counts(context) -> None:
    counts = [1, 3, 5, 2, 0]
    spec = [(0, 0, n) for n in counts]
    samples, per_pr = _make_synthetic_dataset(spec)
    context.fixtures["samples"] = samples
    context.fixtures["reviewer"] = _StubReviewer(per_pr_comments=per_pr)


@given("an EvalReport produced from the default metric set")
def step_eval_report_default(context) -> None:
    # Reuse the synthetic dataset if present, else build one
    if "samples" not in context.fixtures:
        spec = [(1, 3, 2), (0, 1, 0), (2, 5, 3)]
        samples, per_pr = _make_synthetic_dataset(spec)
        context.fixtures["samples"] = samples
        context.fixtures["reviewer"] = _StubReviewer(per_pr_comments=per_pr)

    with patch("peer.eval.metrics.judge_match", _TRUE_JUDGE):
        runner = EvalRunner(
            reviewer=context.fixtures["reviewer"],
            dataset=context.fixtures["samples"],
        )
        context.fixtures["report"] = runner.run()


# ---------------------------------------------------------------------------
# When steps
# ---------------------------------------------------------------------------


@when("the EvalRunner runs against the synthetic dataset with default metrics")
def step_run_default_metrics(context) -> None:
    with patch("peer.eval.metrics.judge_match", _TRUE_JUDGE):
        runner = EvalRunner(
            reviewer=context.fixtures["reviewer"],
            dataset=context.fixtures["samples"],
        )
        context.fixtures["report"] = runner.run()


@when("the EvalRunner runs with only DetectionRate")
def step_run_only_detection(context) -> None:
    with patch("peer.eval.metrics.judge_match", _TRUE_JUDGE):
        runner = EvalRunner(
            reviewer=context.fixtures["reviewer"],
            dataset=context.fixtures["samples"],
            metrics=[DetectionRate()],
        )
        context.fixtures["report"] = runner.run()


@when("the EvalRunner runs with only CommentsPerPR")
def step_run_only_commentsperpr(context) -> None:
    runner = EvalRunner(
        reviewer=context.fixtures["reviewer"],
        dataset=context.fixtures["samples"],
        metrics=[CommentsPerPR()],
    )
    context.fixtures["report"] = runner.run()


@when("I instantiate DefectRecall directly")
def step_instantiate_defect_recall(context) -> None:
    from peer.eval import DefectRecall

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        context.fixtures["metric"] = DefectRecall()
        context.fixtures["warnings"] = list(caught)


@when("I render the summary as a string")
def step_render_summary(context) -> None:
    context.fixtures["rendered"] = render_summary(context.fixtures["report"])


@when('I construct an Agent with team_conventions="Some convention text"')
def step_construct_agent_with_conventions(context) -> None:
    from peer.agent import Agent

    context.fixtures["agent"] = Agent(
        model="claude-sonnet-4-6",
        team_conventions="Some convention text",
    )


# ---------------------------------------------------------------------------
# Then steps
# ---------------------------------------------------------------------------


@then('the resulting EvalReport\'s summary metric_values includes "detection_rate"')
def step_summary_has_detection_rate(context) -> None:
    keys = context.fixtures["report"].summary.metric_values.keys()
    assert "detection_rate" in keys, f"detection_rate not in {list(keys)}"


@then('the summary metric_values includes "comments_per_pr"')
def step_summary_has_commentsperpr(context) -> None:
    keys = context.fixtures["report"].summary.metric_values.keys()
    assert "comments_per_pr" in keys, f"comments_per_pr not in {list(keys)}"


@then('the summary metric_values includes "precision_per_severity"')
def step_summary_has_precision_per_severity(context) -> None:
    keys = context.fixtures["report"].summary.metric_values.keys()
    assert "precision_per_severity" in keys, f"precision_per_severity not in {list(keys)}"


@then('the summary metric_values includes "mean_per_pr_recall"')
def step_summary_has_mean_per_pr(context) -> None:
    keys = context.fixtures["report"].summary.metric_values.keys()
    assert "mean_per_pr_recall" in keys, f"mean_per_pr_recall not in {list(keys)}"


@then("the aggregate detection_rate value equals 0.2")
def step_detection_rate_equals(context) -> None:
    val = context.fixtures["report"].summary.metric_values["detection_rate"]
    assert val is not None and abs(val - 0.2) < 1e-9, f"detection_rate = {val}, expected 0.2"


@then("the aggregate comments_per_pr value equals 2.2")
def step_commentsperpr_equals(context) -> None:
    val = context.fixtures["report"].summary.metric_values["comments_per_pr"]
    assert val is not None and abs(val - 2.2) < 1e-9, f"comments_per_pr = {val}, expected 2.2"


@then("a DeprecationWarning is emitted referencing MeanPerPRRecall")
def step_deprecation_warning(context) -> None:
    caught = context.fixtures["warnings"]
    dep_warnings = [
        w
        for w in caught
        if issubclass(w.category, DeprecationWarning) and "MeanPerPRRecall" in str(w.message)
    ]
    assert dep_warnings, (
        f"expected DeprecationWarning naming MeanPerPRRecall; got {[str(w.message) for w in caught]}"
    )


@then('the instantiated metric reports under the name "defect_recall"')
def step_metric_name_defect_recall(context) -> None:
    name = context.fixtures["metric"].name
    assert name == "defect_recall", f"expected name 'defect_recall', got {name!r}"


@then('the output contains a "Headline:" section before any "Secondary:" section')
def step_headline_before_secondary(context) -> None:
    text = context.fixtures["rendered"]
    head_idx = text.find("Headline:")
    sec_idx = text.find("Secondary:")
    assert head_idx >= 0, f"no 'Headline:' section in:\n{text}"
    assert sec_idx >= 0, f"no 'Secondary:' section in:\n{text}"
    assert head_idx < sec_idx, "'Headline:' must come before 'Secondary:'"


@then('the "Secondary:" section\'s "mean_per_pr_recall" line includes a Simpson\'s-paradox caveat')
def step_mean_per_pr_caveat(context) -> None:
    text = context.fixtures["rendered"]
    sec_idx = text.find("Secondary:")
    secondary_section = text[sec_idx:]
    # find the mean_per_pr_recall line in the secondary section
    lines = secondary_section.splitlines()
    mean_line: str | None = None
    for line in lines:
        if "mean_per_pr_recall" in line:
            mean_line = line
            break
    assert mean_line is not None, f"no mean_per_pr_recall line in Secondary:\n{secondary_section}"
    assert "Simpson" in mean_line, (
        f"expected Simpson's-paradox caveat in mean_per_pr_recall line; got: {mean_line!r}"
    )


@then('the agent\'s system_prompt contains "Some convention text"')
def step_agent_prompt_contains_text(context) -> None:
    prompt = context.fixtures["agent"].system_prompt
    assert "Some convention text" in prompt, "convention text not injected into system_prompt"


@then('the agent\'s system_prompt does NOT contain the phrase "nit or minor"')
def step_agent_prompt_no_nit_or_minor(context) -> None:
    prompt = context.fixtures["agent"].system_prompt
    assert "nit or minor" not in prompt, (
        "conventions wrapper still contains the 'nit or minor' severity prescription"
    )
