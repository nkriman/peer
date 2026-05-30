"""Hybrid benchmark assembler + manifest (benchmark-the-field Phase 1, peer-4z5).

Merges GoldSample lists from any number of sources (the fresh revert holdout in
holdout.py, the SWE-bench reconstruction in swebench.py, future sources) into a
single deduplicated dataset and emits a manifest describing it: total count,
the contamination split (safe / contaminated / unassessed), per-source counts,
and the cutoff date the holdout was mined against.

The assembler is source-agnostic on purpose: it keys off `pr_url` for dedup and
`metadata.contamination_safe` / `metadata.curation_source` for the manifest, so
it never needs to know which miner produced a sample. The leaderboard leads with
the `contamination_safe=True` slice; the manifest makes that split auditable.

Dedup is first-wins by the order lists are passed: callers pass the fresh
holdout BEFORE the contaminated SWE-bench half so a PR present in both keeps its
contamination-safe label.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from .storage import GoldSampleStorage, JSONLStorage
from .types import GoldSample

logger = logging.getLogger(__name__)


class BenchmarkManifest(BaseModel):
    """Auditable description of an assembled hybrid benchmark."""

    total: int
    contamination_safe: int  # metadata.contamination_safe is True
    contaminated: int  # metadata.contamination_safe is False
    contamination_unassessed: int  # metadata.contamination_safe is None
    by_source: dict[str, int]  # curation_source -> count
    duplicates_skipped: int
    cutoff: datetime | None = None
    output_path: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))


def dedup_samples(
    sample_lists: list[list[GoldSample]],
) -> tuple[list[GoldSample], int]:
    """Flatten the lists in order, dropping any sample whose `pr_url` was already
    seen. Returns (kept, duplicates_skipped). First occurrence wins."""
    seen: set[str] = set()
    kept: list[GoldSample] = []
    duplicates = 0
    for samples in sample_lists:
        for s in samples:
            if s.pr_url in seen:
                duplicates += 1
                continue
            seen.add(s.pr_url)
            kept.append(s)
    return kept, duplicates


def build_manifest(
    samples: list[GoldSample],
    *,
    duplicates_skipped: int = 0,
    cutoff: datetime | None = None,
    output_path: str | None = None,
) -> BenchmarkManifest:
    """Summarize an assembled sample list into a manifest. Pure: no I/O."""
    safe = sum(1 for s in samples if s.metadata.contamination_safe is True)
    contaminated = sum(1 for s in samples if s.metadata.contamination_safe is False)
    unassessed = sum(1 for s in samples if s.metadata.contamination_safe is None)
    by_source = Counter(s.metadata.curation_source for s in samples)
    return BenchmarkManifest(
        total=len(samples),
        contamination_safe=safe,
        contaminated=contaminated,
        contamination_unassessed=unassessed,
        by_source=dict(by_source),
        duplicates_skipped=duplicates_skipped,
        cutoff=cutoff,
        output_path=output_path,
    )


def assemble_hybrid(
    sample_lists: list[list[GoldSample]],
    *,
    storage: GoldSampleStorage | None = None,
    cutoff: datetime | None = None,
    output_path: str | None = None,
) -> tuple[list[GoldSample], BenchmarkManifest]:
    """Merge + dedup the given GoldSample lists, optionally persist via
    `storage`, and return (kept_samples, manifest).

    `output_path` is recorded in the manifest for provenance; persistence
    itself is done through `storage` (inject a JSONLStorage to write a file).
    """
    kept, duplicates = dedup_samples(sample_lists)
    if storage is not None:
        for s in kept:
            storage.add(s)
    manifest = build_manifest(
        kept,
        duplicates_skipped=duplicates,
        cutoff=cutoff,
        output_path=output_path,
    )
    logger.info(
        "assembled hybrid benchmark: %d samples (%d safe / %d contaminated / %d unassessed), "
        "%d duplicates skipped",
        manifest.total,
        manifest.contamination_safe,
        manifest.contaminated,
        manifest.contamination_unassessed,
        manifest.duplicates_skipped,
    )
    return kept, manifest


def write_manifest(manifest: BenchmarkManifest, path: Path | str) -> None:
    """Write the manifest as pretty JSON (one file alongside the benchmark)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(manifest.model_dump(mode="json"), indent=2) + "\n")


def assemble_to_files(
    sample_lists: list[list[GoldSample]],
    *,
    dataset_path: Path | str,
    manifest_path: Path | str | None = None,
    cutoff: datetime | None = None,
) -> BenchmarkManifest:
    """Convenience: assemble, write the dataset JSONL via JSONLStorage, and write
    the manifest. `manifest_path` defaults to `<dataset_path>.manifest.json`."""
    dataset_path = Path(dataset_path)
    storage = JSONLStorage(dataset_path)
    _, manifest = assemble_hybrid(
        sample_lists,
        storage=storage,
        cutoff=cutoff,
        output_path=str(dataset_path),
    )
    mpath = (
        Path(manifest_path)
        if manifest_path
        else dataset_path.with_suffix(dataset_path.suffix + ".manifest.json")
    )
    write_manifest(manifest, mpath)
    return manifest
