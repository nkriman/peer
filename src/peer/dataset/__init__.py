"""peer.dataset — pipeline for transforming raw (PR, comments) into curated
gold samples for eval. Eight extension-point Protocols with one default impl
per Protocol, composable via the `Curator` class.

See `openspec/changes/eval-v01/specs/dataset-curation/spec.md` for the
requirements and `openspec/changes/eval-v01/design.md` for the rationale.
"""

from .classifier import CommentClassifier, LLMCommentClassifier
from .curation import Curator
from .enrichment import (
    EnrichmentStep,
    LLMOracleEnrichment,
    NoEnrichment,
    PostMergeBugfixCorrelation,
)
from .sources import GitHubInlineCommentSource, RawSampleSource
from .storage import GoldSampleStorage, JSONLStorage
from .taxonomy import DefaultTaxonomy, Taxonomy
from .types import (
    CategoryDef,
    Classification,
    GoldDefect,
    GoldSample,
    GoldSampleMetadata,
    PRContext,
    ProposedSample,
    RawComment,
    RawSample,
)

__all__ = [
    "CategoryDef",
    "Classification",
    "CommentClassifier",
    "Curator",
    "DefaultTaxonomy",
    "EnrichmentStep",
    "GitHubInlineCommentSource",
    "GoldDefect",
    "GoldSample",
    "GoldSampleMetadata",
    "GoldSampleStorage",
    "JSONLStorage",
    "LLMCommentClassifier",
    "LLMOracleEnrichment",
    "NoEnrichment",
    "PRContext",
    "PostMergeBugfixCorrelation",
    "ProposedSample",
    "RawComment",
    "RawSample",
    "RawSampleSource",
    "Taxonomy",
]
