"""Tests for peer.eval.runner.EvalRunner."""

from __future__ import annotations

import pytest

from peer.dataset.types import GoldDefect, GoldSample, GoldSampleMetadata
from peer.eval.runner import EvalRunner
from peer.eval.types import MetricResult
from peer.types import Comment, Review

# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class StubReviewer:
    """A reviewer that returns canned Reviews keyed on pr_url."""

    model = "claude-sonnet-4-6"
    system_prompt = "you are a code reviewer"

    def __init__(self, results: dict[str, Review]) -> None:
        self.results = results
        self.calls: list[str] = []

    def review(self, pr_url: str) -> Review:
        self.calls.append(pr_url)
        result = self.results[pr_url]
        if isinstance(result, Exception):
            raise result
        return result


class FailingThenOkReviewer:
    model = "claude-sonnet-4-6"
    system_prompt = None  # exercises the "no prompt hash" branch

    def __init__(self, fail_urls: set[str], good_review: Review) -> None:
        self.fail_urls = fail_urls
        self.good_review = good_review

    def review(self, pr_url: str) -> Review:
        if pr_url in self.fail_urls:
            raise RuntimeError(f"intentional failure on {pr_url}")
        return self.good_review


class FixedMetric:
    """A metric that always returns the same value (no LLM calls)."""

    def __init__(self, name: str, value: float | None = 0.5) -> None:
        self.name = name
        self._value = value

    def score(self, sample, review, client=None):
        return MetricResult(name=self.name, value=self._value)


class RaisingMetric:
    name = "exploding_metric"

    def score(self, sample, review, client=None):
        raise RuntimeError("metric exploded")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _sample(pr_url: str) -> GoldSample:
    return GoldSample(
        pr_url=pr_url,
        pr_title="t",
        head_sha="x",
        gold_defects=[
            GoldDefect(
                path="a.py",
                line=10,
                category="defect-correctness",
                severity="important",
                description="d",
                source="human_reviewer:x",
            )
        ],
        metadata=GoldSampleMetadata(),
    )


def _review() -> Review:
    return Review(
        comments=[
            Comment(
                path="a.py",
                line=10,
                severity="important",
                body="bad code",
                rationale="r",
            )
        ],
        usage={
            "model": "claude-sonnet-4-6",
            "input_tokens": 1000,
            "output_tokens": 200,
        },
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_eval_runner_basic_happy_path():
    sample = _sample("https://github.com/o/r/pull/1")
    reviewer = StubReviewer({sample.pr_url: _review()})
    runner = EvalRunner(
        reviewer=reviewer,
        dataset=[sample],
        metrics=[FixedMetric("defect_recall", 1.0)],
        dataset_path="test.jsonl",
    )
    report = runner.run()
    assert report.dataset_size == 1
    assert report.summary.n_samples_total == 1
    assert report.summary.n_samples_succeeded == 1
    assert report.summary.n_samples_failed == 0
    assert report.summary.metric_values["defect_recall"] == 1.0
    assert report.agent_config.model == "claude-sonnet-4-6"
    assert report.agent_config.system_prompt_hash is not None
    assert report.dataset_path == "test.jsonl"


def test_eval_runner_reports_cost_and_latency():
    sample = _sample("https://github.com/o/r/pull/1")
    reviewer = StubReviewer({sample.pr_url: _review()})
    runner = EvalRunner(
        reviewer=reviewer,
        dataset=[sample],
        metrics=[FixedMetric("m", 1.0)],
    )
    report = runner.run()
    # Cost: 1000/1M * 3 + 200/1M * 15 = 0.003 + 0.003 = 0.006
    assert report.summary.cost_usd_total == pytest.approx(0.006)
    assert report.summary.cost_usd_p50 == pytest.approx(0.006)
    assert report.per_sample[0].cost_usd == pytest.approx(0.006)
    assert report.per_sample[0].latency_seconds is not None
    assert report.per_sample[0].latency_seconds >= 0


def test_eval_runner_per_sample_failure_isolated():
    s1 = _sample("https://github.com/o/r/pull/1")
    s2 = _sample("https://github.com/o/r/pull/2")
    reviewer = FailingThenOkReviewer(fail_urls={s1.pr_url}, good_review=_review())
    runner = EvalRunner(
        reviewer=reviewer,
        dataset=[s1, s2],
        metrics=[FixedMetric("m", 0.5)],
    )
    report = runner.run()
    assert report.summary.n_samples_total == 2
    assert report.summary.n_samples_succeeded == 1
    assert report.summary.n_samples_failed == 1
    # The first sample has an error set; second has a metric value
    by_url = {r.pr_url: r for r in report.per_sample}
    assert by_url[s1.pr_url].error is not None
    assert "intentional failure" in by_url[s1.pr_url].error
    assert by_url[s2.pr_url].error is None
    assert by_url[s2.pr_url].metrics["m"].value == 0.5


def test_eval_runner_metric_failure_does_not_abort():
    sample = _sample("https://github.com/o/r/pull/1")
    reviewer = StubReviewer({sample.pr_url: _review()})
    runner = EvalRunner(
        reviewer=reviewer,
        dataset=[sample],
        metrics=[FixedMetric("ok_metric", 0.7), RaisingMetric()],
    )
    report = runner.run()
    assert report.summary.n_samples_failed == 0
    assert report.summary.metric_values["ok_metric"] == 0.7
    # Failing metric still appears with value=None
    assert report.summary.metric_values["exploding_metric"] is None
    failing = report.per_sample[0].metrics["exploding_metric"]
    assert failing.value is None
    assert "metric raised" in (failing.notes or "")


def test_eval_runner_unknown_model_cost_unavailable():
    sample = _sample("https://github.com/o/r/pull/1")
    rev = Review(
        comments=[],
        usage={
            "model": "mystery-model",
            "input_tokens": 1000,
            "output_tokens": 100,
        },
    )
    reviewer = StubReviewer({sample.pr_url: rev})
    runner = EvalRunner(
        reviewer=reviewer,
        dataset=[sample],
        metrics=[FixedMetric("m", 0.0)],
    )
    report = runner.run()
    assert report.per_sample[0].cost_usd is None
    assert report.summary.cost_unavailable_reason is not None
    assert "mystery-model" in report.summary.cost_unavailable_reason


def test_eval_runner_aggregates_means_across_samples():
    s1 = _sample("https://github.com/o/r/pull/1")
    s2 = _sample("https://github.com/o/r/pull/2")
    reviewer = StubReviewer({s1.pr_url: _review(), s2.pr_url: _review()})

    # Different values per sample via a stateful metric
    class AlternatingMetric:
        name = "alt"

        def __init__(self) -> None:
            self.i = 0

        def score(self, sample, review, client=None):
            v = [0.2, 0.8][self.i]
            self.i += 1
            return MetricResult(name=self.name, value=v)

    runner = EvalRunner(
        reviewer=reviewer,
        dataset=[s1, s2],
        metrics=[AlternatingMetric()],
    )
    report = runner.run()
    # mean(0.2, 0.8) = 0.5
    assert report.summary.metric_values["alt"] == pytest.approx(0.5)


def test_eval_runner_review_summary_records_severity_distribution():
    sample = _sample("https://github.com/o/r/pull/1")
    rev = Review(
        comments=[
            Comment(path="a.py", line=1, severity="critical", body="b", rationale="r"),
            Comment(path="a.py", line=2, severity="critical", body="b", rationale="r"),
            Comment(path="a.py", line=3, severity="minor", body="b", rationale="r"),
        ],
        usage={"model": "claude-sonnet-4-6", "input_tokens": 100, "output_tokens": 50},
    )
    reviewer = StubReviewer({sample.pr_url: rev})
    runner = EvalRunner(reviewer=reviewer, dataset=[sample], metrics=[FixedMetric("m", 0.5)])
    report = runner.run()
    sev = report.per_sample[0].review_summary["severity_distribution"]
    assert sev["critical"] == 2
    assert sev["minor"] == 1
    assert report.per_sample[0].review_summary["n_comments"] == 3
