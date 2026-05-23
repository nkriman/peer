"""Curator: orchestrates source -> classifier -> enrichment -> storage.

Default-everything path is one constructor call (storage is the only argument
that must be supplied explicitly — there is no global default dataset path).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from ..exceptions import CurationRejected
from .classifier import CommentClassifier, LLMCommentClassifier
from .enrichment import EnrichmentStep, NoEnrichment
from .sources import GitHubInlineCommentSource, RawSampleSource
from .storage import GoldSampleStorage, JSONLStorage
from .taxonomy import DefaultTaxonomy, Taxonomy
from .types import (
    Classification,
    GoldDefect,
    GoldSample,
    GoldSampleMetadata,
    PRContext,
    ProposedSample,
    RawComment,
    RawSample,
)

logger = logging.getLogger(__name__)


def _review_depth(raw_count: int) -> str:
    if raw_count == 0:
        return "none"
    if raw_count <= 2:
        return "light"
    if raw_count <= 8:
        return "normal"
    return "thorough"


def _normalize_description(comment: RawComment, classification: Classification) -> str:
    """Prefer classifier reasoning when it preserves the technical claim.
    Falls back to a truncated restatement of the comment body. Never invents
    information not present in the inputs."""
    reasoning = (classification.reasoning or "").strip()
    body = (comment.body or "").strip()
    if reasoning and len(reasoning) >= 15 and not reasoning.lower().startswith(
        "(no reasoning"
    ):
        return reasoning
    # Fallback: first ~300 chars of the actual comment body.
    if len(body) <= 300:
        return body
    return body[:297].rstrip() + "..."


def _build_proposed(
    raw: RawSample,
    classifications: list[tuple[RawComment, Classification]],
    taxonomy: Taxonomy,
) -> tuple[GoldSample, list[str]]:
    defects: list[GoldDefect] = []
    dropped: list[str] = []

    for comment, cls in classifications:
        if not taxonomy.is_kept(cls.category):
            dropped.append(cls.category)
            continue

        # Apply Taxonomy severity overrides where applicable.
        forced = taxonomy.force_severity_for(cls.category)
        severity = forced if forced is not None else cls.severity

        # Inline-review comments carry path/line; issue comments may not.
        path = comment.path or ""
        if not path:
            # Issue comments without a path can't anchor to a defect location.
            # Drop them — we can't honestly call them a GoldDefect on a file.
            dropped.append(cls.category)
            continue

        defects.append(
            GoldDefect(
                path=path,
                line=comment.line,
                line_range=None,
                category=cls.category,
                severity=severity,
                description=_normalize_description(comment, cls),
                source=f"human_reviewer:{comment.author}",
                confidence="high",
                original_comment_excerpt=comment.body[:500],
            )
        )

    metadata = GoldSampleMetadata(
        raw_comment_count=len(raw.comments),
        defect_comment_count=len(defects),
        review_depth=_review_depth(len(raw.comments)),  # type: ignore[arg-type]
        has_followup_bugfix=None,
        curation_source="default_pipeline",
        spot_checked=False,
        taxonomy_version=taxonomy.version,
    )

    sample = GoldSample(
        pr_url=raw.pr_url,
        pr_title=raw.pr_title,
        pr_body=raw.pr_body,
        head_sha=raw.head_sha,
        merged_at=raw.merged_at,
        gold_defects=defects,
        metadata=metadata,
    )
    return sample, dropped


def _summarize_for_operator(proposed: ProposedSample) -> str:
    s = proposed.proposed
    lines = [
        f"PR: {s.pr_url}",
        f"Title: {s.pr_title}",
        f"Raw comments: {s.metadata.raw_comment_count} | "
        f"Gold defects: {len(s.gold_defects)} | "
        f"Dropped (category): {len(proposed.dropped_categories)}",
        "",
        "Proposed gold defects:",
    ]
    if not s.gold_defects:
        lines.append("  (none)")
    for i, d in enumerate(s.gold_defects, 1):
        loc = f"{d.path}:{d.line}" if d.line is not None else d.path
        lines.append(
            f"  [{i}] {d.severity:<9} {d.category:<22} {loc}"
        )
        lines.append(f"      desc: {d.description[:200]}")
        lines.append(f"      source: {d.source} (confidence={d.confidence})")
    if proposed.dropped_categories:
        lines.append("")
        lines.append(f"Dropped categories: {sorted(set(proposed.dropped_categories))}")
    return "\n".join(lines)


def _edit_in_editor(sample: GoldSample) -> GoldSample:
    editor = os.environ.get("EDITOR")
    if not editor:
        for cand in ("vim", "nano", "vi"):
            if shutil.which(cand):
                editor = cand
                break
    if not editor:
        logger.warning("No $EDITOR and no vim/nano available; returning unchanged.")
        return sample

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, prefix="peer-gold-"
    ) as tmp:
        tmp.write(json.dumps(json.loads(sample.model_dump_json()), indent=2))
        tmp_path = Path(tmp.name)

    try:
        subprocess.run([editor, str(tmp_path)], check=False)
        edited = tmp_path.read_text()
        try:
            return GoldSample.model_validate_json(edited)
        except Exception as e:
            logger.error("Edited JSON failed to validate: %s", e)
            logger.error("Returning the pre-edit sample unchanged.")
            return sample
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass


class Curator:
    """Composes source -> classifier -> enrichment -> storage. Storage MUST
    be passed explicitly; there is no global default dataset path."""

    def __init__(
        self,
        storage: GoldSampleStorage,
        source: Optional[RawSampleSource] = None,
        classifier: Optional[CommentClassifier] = None,
        enrichment: Optional[EnrichmentStep] = None,
        taxonomy: Taxonomy = DefaultTaxonomy,
    ) -> None:
        self.storage = storage
        self.source = source if source is not None else GitHubInlineCommentSource()
        self.classifier = (
            classifier
            if classifier is not None
            else LLMCommentClassifier(taxonomy=taxonomy)
        )
        self.enrichment = enrichment if enrichment is not None else NoEnrichment()
        self.taxonomy = taxonomy

    # ----------------------------------------------------------------- core

    def _classify_all(
        self, raw: RawSample, pr_context: PRContext
    ) -> list[tuple[RawComment, Classification]]:
        out: list[tuple[RawComment, Classification]] = []
        for c in raw.comments:
            try:
                cls = self.classifier.classify(c, pr_context)
                out.append((c, cls))
            except Exception as e:
                logger.warning(
                    "Classifier failed on comment %s by @%s: %s",
                    c.source_id, c.author, e,
                )
        return out

    def preview(self, pr_url: str) -> ProposedSample:
        raw = self.source.fetch(pr_url)
        pr_context = PRContext(
            pr_url=raw.pr_url,
            title=raw.pr_title,
            body=raw.pr_body,
            diff_summary=None,
        )
        classifications = self._classify_all(raw, pr_context)
        sample, dropped = _build_proposed(raw, classifications, self.taxonomy)
        sample = self.enrichment.enrich(sample, pr_context)
        return ProposedSample(
            proposed=sample,
            classifications=classifications,
            dropped_categories=dropped,
        )

    # ------------------------------------------------------------------ add

    def add(self, pr_url: str, auto_accept: bool = False) -> GoldSample:
        proposed = self.preview(pr_url)
        sample = proposed.proposed

        if auto_accept:
            self.storage.add(sample)
            return sample

        # Interactive prompt loop.
        while True:
            print()
            print(_summarize_for_operator(proposed))
            print()
            choice = input("[a]ccept / [r]eject / [e]dit > ").strip().lower()
            if choice in ("a", "accept", "y", "yes"):
                sample = sample.model_copy(
                    update={
                        "metadata": sample.metadata.model_copy(
                            update={"spot_checked": True}
                        )
                    }
                )
                self.storage.add(sample)
                return sample
            if choice in ("r", "reject", "n", "no"):
                raise CurationRejected(
                    f"Operator rejected proposed sample for {pr_url}"
                )
            if choice in ("e", "edit"):
                sample = _edit_in_editor(sample)
                proposed = ProposedSample(
                    proposed=sample,
                    classifications=proposed.classifications,
                    dropped_categories=proposed.dropped_categories,
                )
                continue
            print(f"Unknown choice: {choice!r}. Use a / r / e.")

    def add_batch(
        self, pr_urls: list[str], auto_accept: bool = False
    ) -> list[GoldSample]:
        out: list[GoldSample] = []
        for url in pr_urls:
            try:
                out.append(self.add(url, auto_accept=auto_accept))
            except CurationRejected as e:
                logger.warning("Skipping %s: %s", url, e)
            except Exception as e:
                logger.warning("Failed to curate %s: %s", url, e)
        return out
