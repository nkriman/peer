"""Assemble the hybrid benchmark from materialized sources (Phase 1, peer-4z5).

Reads the two materialized GoldSample datasets — the fresh revert holdout
(contamination_safe=True) and the SWE-bench reconstruction
(contamination_safe=False) — merges + dedups them (holdout first, so its
contamination-safe label wins any overlap), and writes
dataset/reference/benchmark_hybrid.jsonl plus a manifest.

Run: uv run python scripts/assemble_benchmark.py
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from peer.dataset.assemble import assemble_to_files
from peer.dataset.storage import JSONLStorage

REF = Path("dataset/reference")
HOLDOUT = REF / "benchmark_holdout.jsonl"
SWEBENCH = REF / "benchmark_swebench.jsonl"
HYBRID = REF / "benchmark_hybrid.jsonl"
CUTOFF = datetime(2026, 1, 1, tzinfo=timezone.utc)


def main() -> None:
    holdout = JSONLStorage(HOLDOUT).load_all()
    swebench = JSONLStorage(SWEBENCH).load_all()
    # Holdout first: first-wins dedup keeps its contamination_safe=True label.
    if HYBRID.exists():
        HYBRID.unlink()
    manifest = assemble_to_files(
        [holdout, swebench],
        dataset_path=HYBRID,
        cutoff=CUTOFF,
    )
    print(f"HYBRID_TOTAL={manifest.total}")
    print(f"HYBRID_SAFE={manifest.contamination_safe}")
    print(f"HYBRID_CONTAMINATED={manifest.contaminated}")
    print(f"HYBRID_UNASSESSED={manifest.contamination_unassessed}")
    print(f"HYBRID_DUPES_SKIPPED={manifest.duplicates_skipped}")
    print(f"HYBRID_BY_SOURCE={manifest.by_source}")


if __name__ == "__main__":
    main()
