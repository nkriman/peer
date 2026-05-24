"""Shared fixtures for peer test suite."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from peer.dataset.types import (
    Classification,
    GoldDefect,
    GoldSample,
    GoldSampleMetadata,
    PRContext,
    RawComment,
    RawSample,
)
from peer.types import Comment, Review

# ---------------------------------------------------------------------------
# Anthropic / external service mocks
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_anthropic_client():
    """A MagicMock standing in for anthropic.Anthropic()."""
    client = MagicMock()
    return client


# ---------------------------------------------------------------------------
# Dataset domain objects
# ---------------------------------------------------------------------------


@pytest.fixture
def raw_comment() -> RawComment:
    return RawComment(
        source_id="github:pulls/comments/1",
        author="alice",
        path="src/foo.py",
        line=10,
        body="This will null-deref when bar is None.",
        kind="inline_review",
        created_at=datetime(2026, 1, 1, 12, 0, 0),
    )


@pytest.fixture
def raw_sample(raw_comment) -> RawSample:
    return RawSample(
        pr_url="https://github.com/o/r/pull/1",
        pr_title="Add feature X",
        pr_body="Adds X.",
        head_sha="deadbeef",
        merged_at=datetime(2026, 1, 2, 12, 0, 0),
        comments=[raw_comment],
    )


@pytest.fixture
def pr_context() -> PRContext:
    return PRContext(
        pr_url="https://github.com/o/r/pull/1",
        title="Add feature X",
        body="Adds X.",
        diff_summary=None,
    )


@pytest.fixture
def classification_correctness() -> Classification:
    return Classification(
        category="defect-correctness",
        severity="important",
        reasoning="The comment flags a null-deref risk when bar is None.",
    )


def _make_gold_defect(
    path: str = "src/foo.py",
    line: int | None = 10,
    category: str = "defect-correctness",
    severity: str = "important",
    description: str = "Null deref risk when bar is None.",
) -> GoldDefect:
    return GoldDefect(
        path=path,
        line=line,
        category=category,
        severity=severity,  # type: ignore[arg-type]
        description=description,
        source="human_reviewer:alice",
    )


@pytest.fixture
def make_gold_defect():
    """Factory fixture for GoldDefect."""
    return _make_gold_defect


@pytest.fixture
def gold_sample(make_gold_defect) -> GoldSample:
    return GoldSample(
        pr_url="https://github.com/o/r/pull/1",
        pr_title="Add feature X",
        pr_body="body",
        head_sha="deadbeef",
        gold_defects=[make_gold_defect()],
        metadata=GoldSampleMetadata(
            raw_comment_count=1,
            defect_comment_count=1,
            review_depth="light",
            curation_source="default_pipeline",
            spot_checked=True,
            taxonomy_version="default-v1",
        ),
    )


# ---------------------------------------------------------------------------
# Reviewer / Review fixtures
# ---------------------------------------------------------------------------


def _make_comment(
    path: str = "src/foo.py",
    line: int | None = 10,
    severity: str = "important",
    body: str = "Null deref risk when bar is None.",
) -> Comment:
    return Comment(
        path=path,
        line=line,
        severity=severity,  # type: ignore[arg-type]
        body=body,
        rationale="r",
    )


@pytest.fixture
def make_comment():
    return _make_comment


@pytest.fixture
def review_with_one_match(make_comment) -> Review:
    return Review(
        comments=[_make_comment()],
        usage={"model": "claude-sonnet-4-6", "input_tokens": 1000, "output_tokens": 200},
    )


# Curator collaborator fakes are defined in test_curator.py to keep
# fixtures self-contained without requiring tests/ to be a package.
