"""Tests for peer.eval.metrics."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from peer.dataset.types import GoldDefect, GoldSample, GoldSampleMetadata
from peer.eval.metrics import DefectRecall, NoveltyRate, SeverityCalibration
from peer.types import Comment, Review


def _gold(
    path: str = "a.py",
    line: int = 10,
    category: str = "defect-correctness",
    severity: str = "important",
    description: str = "x",
) -> GoldDefect:
    return GoldDefect(
        path=path,
        line=line,
        category=category,
        severity=severity,  # type: ignore[arg-type]
        description=description,
        source="human_reviewer:alice",
    )


def _peer(
    path: str = "a.py",
    line: int = 10,
    severity: str = "important",
    body: str = "x",
) -> Comment:
    return Comment(
        path=path,
        line=line,
        severity=severity,  # type: ignore[arg-type]
        body=body,
        rationale="r",
    )


def _sample(defects):
    return GoldSample(
        pr_url="https://github.com/o/r/pull/1",
        pr_title="t",
        head_sha="x",
        gold_defects=defects,
        metadata=GoldSampleMetadata(),
    )


# ---------------------------------------------------------------------------
# DefectRecall
# ---------------------------------------------------------------------------


def test_defect_recall_no_gold_returns_none():
    sample = _sample([])
    review = Review(comments=[_peer()])
    with patch("peer.eval.metrics.judge_match", return_value=True):
        result = DefectRecall().score(sample, review)
    assert result.value is None
    assert "no gold defects" in result.notes


def test_defect_recall_full_hit():
    gold = [_gold(line=10), _gold(line=20)]
    sample = _sample(gold)
    review = Review(comments=[_peer(line=10), _peer(line=20)])
    with patch("peer.eval.metrics.judge_match", return_value=True):
        result = DefectRecall().score(sample, review)
    assert result.value == 1.0
    assert result.per_sample_detail["matched_count"] == 2
    assert result.per_sample_detail["total_gold"] == 2


def test_defect_recall_full_miss_wrong_path():
    gold = [_gold(path="a.py", line=10), _gold(path="b.py", line=20)]
    sample = _sample(gold)
    # Peer comments on a totally unrelated file
    review = Review(comments=[_peer(path="z.py", line=999)])
    with patch("peer.eval.metrics.judge_match", return_value=True):
        result = DefectRecall().score(sample, review)
    assert result.value == 0.0
    assert result.per_sample_detail["matched_count"] == 0


def test_defect_recall_partial_hit():
    gold = [_gold(line=10), _gold(line=100)]
    sample = _sample(gold)
    # Only first matches line range
    review = Review(comments=[_peer(line=10)])
    with patch("peer.eval.metrics.judge_match", return_value=True):
        result = DefectRecall().score(sample, review)
    assert result.value == 0.5
    assert result.per_sample_detail["matched_count"] == 1


def test_defect_recall_line_proximity_window():
    # Defect at line 50; peer at line 53 should still match (within 5)
    gold = [_gold(line=50)]
    sample = _sample(gold)
    review = Review(comments=[_peer(line=53)])
    with patch("peer.eval.metrics.judge_match", return_value=True):
        result = DefectRecall().score(sample, review)
    assert result.value == 1.0


def test_defect_recall_line_proximity_exceeded():
    gold = [_gold(line=50)]
    sample = _sample(gold)
    # 100 is way outside the +-5 proximity window
    review = Review(comments=[_peer(line=100)])
    with patch("peer.eval.metrics.judge_match", return_value=True):
        result = DefectRecall().score(sample, review)
    assert result.value == 0.0


def test_defect_recall_judge_says_different():
    gold = [_gold(line=10)]
    sample = _sample(gold)
    review = Review(comments=[_peer(line=10)])
    with patch("peer.eval.metrics.judge_match", return_value=False):
        result = DefectRecall().score(sample, review)
    assert result.value == 0.0


def test_defect_recall_per_severity_counts():
    gold = [
        _gold(line=10, severity="critical"),
        _gold(line=20, severity="critical"),
        _gold(line=30, severity="minor"),
    ]
    sample = _sample(gold)
    # Only line 10 matches
    review = Review(comments=[_peer(line=10)])
    with patch("peer.eval.metrics.judge_match", return_value=True):
        result = DefectRecall().score(sample, review)
    per_sev = result.per_sample_detail["per_severity"]
    assert per_sev["critical"]["total"] == 2
    assert per_sev["critical"]["hit"] == 1
    assert per_sev["critical"]["miss"] == 1
    assert per_sev["minor"]["total"] == 1
    assert per_sev["minor"]["miss"] == 1


# ---------------------------------------------------------------------------
# NoveltyRate
# ---------------------------------------------------------------------------


def test_novelty_rate_no_peer_comments_returns_none():
    sample = _sample([_gold()])
    review = Review(comments=[])
    with patch("peer.eval.metrics.judge_match", return_value=True):
        result = NoveltyRate().score(sample, review)
    assert result.value is None


def test_novelty_rate_all_match_is_zero():
    sample = _sample([_gold(line=10), _gold(line=20)])
    review = Review(comments=[_peer(line=10), _peer(line=20)])
    with patch("peer.eval.metrics.judge_match", return_value=True):
        result = NoveltyRate().score(sample, review)
    assert result.value == 0.0


def test_novelty_rate_none_match_is_one():
    sample = _sample([_gold(line=10)])
    review = Review(comments=[_peer(path="z.py", line=10)])
    with patch("peer.eval.metrics.judge_match", return_value=True):
        result = NoveltyRate().score(sample, review)
    assert result.value == 1.0
    assert result.per_sample_detail["peer_unmatched_count"] == 1


def test_novelty_rate_partial():
    sample = _sample([_gold(line=10)])
    review = Review(
        comments=[_peer(line=10), _peer(path="z.py", line=99)]
    )
    with patch("peer.eval.metrics.judge_match", return_value=True):
        result = NoveltyRate().score(sample, review)
    assert result.value == 0.5


# ---------------------------------------------------------------------------
# SeverityCalibration
# ---------------------------------------------------------------------------


def test_severity_calibration_no_matches_returns_none():
    sample = _sample([_gold(line=10)])
    review = Review(comments=[_peer(path="z.py", line=10)])
    with patch("peer.eval.metrics.judge_match", return_value=True):
        result = SeverityCalibration().score(sample, review)
    assert result.value is None


def test_severity_calibration_exact_match_delta_zero():
    sample = _sample([_gold(line=10, severity="important")])
    review = Review(comments=[_peer(line=10, severity="important")])
    with patch("peer.eval.metrics.judge_match", return_value=True):
        result = SeverityCalibration().score(sample, review)
    assert result.value == 0.0


def test_severity_calibration_peer_less_severe_positive_delta():
    # Peer marks nit (3), gold marks critical (0) -> delta = +3
    sample = _sample([_gold(line=10, severity="critical")])
    review = Review(comments=[_peer(line=10, severity="nit")])
    with patch("peer.eval.metrics.judge_match", return_value=True):
        result = SeverityCalibration().score(sample, review)
    assert result.value == 3.0


def test_severity_calibration_peer_more_severe_negative_delta():
    # Peer marks critical (0), gold marks minor (2) -> delta = -2
    sample = _sample([_gold(line=10, severity="minor")])
    review = Review(comments=[_peer(line=10, severity="critical")])
    with patch("peer.eval.metrics.judge_match", return_value=True):
        result = SeverityCalibration().score(sample, review)
    assert result.value == -2.0


def test_severity_calibration_confusion_matrix_populated():
    sample = _sample(
        [_gold(line=10, severity="critical"), _gold(line=20, severity="minor")]
    )
    review = Review(
        comments=[
            _peer(line=10, severity="important"),
            _peer(line=20, severity="minor"),
        ]
    )
    with patch("peer.eval.metrics.judge_match", return_value=True):
        result = SeverityCalibration().score(sample, review)
    conf = result.per_sample_detail["confusion"]
    assert conf["critical"]["important"] == 1
    assert conf["minor"]["minor"] == 1
    assert result.per_sample_detail["n_pairs"] == 2
