"""Pydantic schemas for the dataset-curation pipeline.

Eight-extension-point framework: this module defines the data shapes that
flow through RawSampleSource → CommentClassifier → EnrichmentStep →
GoldSampleStorage. Per design.md Decision 1, types are stable contracts
across all default and user-supplied implementations.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..types import Severity

# ---------------------------------------------------------------------------
# Raw side: what RawSampleSource produces
# ---------------------------------------------------------------------------


class RawComment(BaseModel):
    """A single comment as it appears in the source (GitHub inline, Jira, etc.)."""

    source_id: str  # e.g., "github:pulls/comments/1234567"
    author: str
    path: str | None = None  # for inline review comments; None for issue-level
    line: int | None = None
    body: str
    kind: Literal["inline_review", "issue_comment", "review_summary", "other"] = "inline_review"
    created_at: datetime | None = None


class RawSample(BaseModel):
    """Raw fetched data for one PR before classification."""

    pr_url: str
    pr_title: str
    pr_body: str
    head_sha: str
    merged_at: datetime | None = None
    comments: list[RawComment] = Field(default_factory=list)


class PRContext(BaseModel):
    """Minimal PR context passed to classifier / enrichment so they can
    reason about the PR (not just the comment in isolation)."""

    pr_url: str
    title: str
    body: str
    diff_summary: str | None = None  # truncated diff; populated when available


# ---------------------------------------------------------------------------
# Taxonomy: category and severity definitions
# ---------------------------------------------------------------------------


class CategoryDef(BaseModel):
    """One classification category."""

    name: str  # e.g., "defect-correctness"
    description: str
    is_defect: bool
    force_severity: Severity | None = (
        None  # if set, all comments in this category get this severity
    )


# Taxonomy itself lives in taxonomy.py so it can carry the default instance.


# ---------------------------------------------------------------------------
# Classification output
# ---------------------------------------------------------------------------


class Classification(BaseModel):
    """A classifier's decision about one raw comment."""

    category: str  # must match a CategoryDef.name in the active Taxonomy
    severity: Severity
    reasoning: str  # short rationale from the classifier (LLM or rule-based)


# ---------------------------------------------------------------------------
# Gold side: curated outputs
# ---------------------------------------------------------------------------


class GoldDefect(BaseModel):
    """One defect a good reviewer should have flagged on this PR."""

    path: str
    line: int | None = None
    line_range: tuple[int, int] | None = None  # for defects spanning multiple lines
    category: str  # from Taxonomy
    severity: Severity
    description: str  # normalized, not raw human wording
    source: str  # e.g., "human_reviewer:dmontagu", "post_merge_correlation", "llm_oracle"
    confidence: Literal["high", "medium", "low"] = "high"
    original_comment_excerpt: str | None = None  # verbatim source for audit


class GoldSampleMetadata(BaseModel):
    raw_comment_count: int = 0
    defect_comment_count: int = 0
    review_depth: Literal["none", "light", "normal", "thorough"] = "none"
    has_followup_bugfix: bool | None = None  # None = not checked
    curation_source: str = "default"  # e.g., "default_pipeline", "manual"
    spot_checked: bool = False
    taxonomy_version: str = ""


class GoldSample(BaseModel):
    """A curated PR with normalized defect labels — the eval-ground-truth unit."""

    pr_url: str
    pr_title: str
    pr_body: str = ""
    head_sha: str = ""
    merged_at: datetime | None = None
    gold_defects: list[GoldDefect] = Field(default_factory=list)
    metadata: GoldSampleMetadata = Field(default_factory=GoldSampleMetadata)
    curated_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    # eval-v02: case-specific Evaluators that apply only to this sample.
    # Held as Any so Pydantic doesn't try to schema-validate arbitrary
    # user-supplied EvalMetric impls; round-trips via MetricSpec is deferred
    # to a future change (peer doesn't need to serialize case-specific
    # evaluators in JSONL today — users construct them in code).
    evaluators: list[Any] = Field(default_factory=list, exclude=True)

    model_config = ConfigDict(arbitrary_types_allowed=True)


class ProposedSample(BaseModel):
    """What Curator.preview returns: the proposed GoldSample plus the raw
    classifications that produced it, so the operator can spot-check."""

    proposed: GoldSample
    classifications: list[tuple[RawComment, Classification]] = Field(default_factory=list)
    dropped_categories: list[str] = Field(
        default_factory=list
    )  # which categories were filtered out
