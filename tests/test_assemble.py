"""Unit tests for the hybrid benchmark assembler + manifest (peer-4z5)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from peer.dataset.assemble import (
    BenchmarkManifest,
    assemble_hybrid,
    assemble_to_files,
    build_manifest,
    dedup_samples,
    write_manifest,
)
from peer.dataset.storage import JSONLStorage
from peer.dataset.types import GoldDefect, GoldSample, GoldSampleMetadata


def _sample(pr_url: str, *, safe: bool | None, source: str) -> GoldSample:
    return GoldSample(
        pr_url=pr_url,
        pr_title=f"sample {pr_url}",
        gold_defects=[
            GoldDefect(
                path="a.py",
                line=1,
                category="defect-correctness",
                severity="important",
                description="x",
                source=source,
            )
        ],
        metadata=GoldSampleMetadata(contamination_safe=safe, curation_source=source),
    )


def _holdout():
    return [
        _sample("https://github.com/o/r/pull/1", safe=True, source="fresh-holdout:revert"),
        _sample("https://github.com/o/r/pull/2", safe=True, source="fresh-holdout:revert"),
    ]


def _swebench():
    return [
        _sample("https://github.com/d/d/pull/100", safe=False, source="crbench-recon:swe-verified"),
        _sample("https://github.com/d/d/pull/101", safe=False, source="crbench-recon:swe-verified"),
        _sample("https://github.com/d/d/pull/102", safe=False, source="crbench-recon:swe-verified"),
    ]


# --------------------------------------------------------------------------
# dedup
# --------------------------------------------------------------------------


def test_dedup_no_overlap():
    kept, dupes = dedup_samples([_holdout(), _swebench()])
    assert len(kept) == 5
    assert dupes == 0


def test_dedup_first_wins_keeps_holdout_label():
    dup_url = "https://github.com/o/r/pull/1"
    contaminated_dup = _sample(dup_url, safe=False, source="crbench-recon:swe-verified")
    kept, dupes = dedup_samples([_holdout(), [contaminated_dup]])
    assert dupes == 1
    match = [s for s in kept if s.pr_url == dup_url]
    assert len(match) == 1
    # holdout came first, so the contamination-safe label survives
    assert match[0].metadata.contamination_safe is True


def test_dedup_within_single_list():
    s = _sample("https://github.com/o/r/pull/9", safe=True, source="x")
    kept, dupes = dedup_samples([[s, s]])
    assert len(kept) == 1
    assert dupes == 1


# --------------------------------------------------------------------------
# manifest
# --------------------------------------------------------------------------


def test_build_manifest_counts_contamination_split():
    kept, _ = dedup_samples([_holdout(), _swebench()])
    m = build_manifest(kept)
    assert m.total == 5
    assert m.contamination_safe == 2
    assert m.contaminated == 3
    assert m.contamination_unassessed == 0


def test_build_manifest_by_source():
    kept, _ = dedup_samples([_holdout(), _swebench()])
    m = build_manifest(kept)
    assert m.by_source == {
        "fresh-holdout:revert": 2,
        "crbench-recon:swe-verified": 3,
    }


def test_build_manifest_unassessed():
    s = _sample("https://github.com/o/r/pull/5", safe=None, source="legacy")
    m = build_manifest([s])
    assert m.contamination_unassessed == 1
    assert m.contamination_safe == 0
    assert m.contaminated == 0


# --------------------------------------------------------------------------
# assemble_hybrid (with storage)
# --------------------------------------------------------------------------


def test_assemble_hybrid_persists_via_storage(tmp_path):
    storage = JSONLStorage(tmp_path / "hybrid.jsonl")
    cutoff = datetime(2026, 1, 1, tzinfo=timezone.utc)
    kept, manifest = assemble_hybrid([_holdout(), _swebench()], storage=storage, cutoff=cutoff)
    assert len(kept) == 5
    assert manifest.cutoff == cutoff
    reloaded = storage.load_all()
    assert len(reloaded) == 5
    assert {s.pr_url for s in reloaded} == {s.pr_url for s in kept}


def test_assemble_hybrid_no_storage_is_pure(tmp_path):
    kept, manifest = assemble_hybrid([_holdout()], storage=None)
    assert len(kept) == 2
    assert manifest.total == 2
    # nothing written
    assert not any(tmp_path.iterdir())


# --------------------------------------------------------------------------
# write_manifest + assemble_to_files
# --------------------------------------------------------------------------


def test_write_manifest_roundtrip(tmp_path):
    m = build_manifest(_holdout(), duplicates_skipped=2)
    p = tmp_path / "m.json"
    write_manifest(m, p)
    loaded = BenchmarkManifest.model_validate_json(p.read_text())
    assert loaded.total == 2
    assert loaded.duplicates_skipped == 2


def test_assemble_to_files_writes_dataset_and_manifest(tmp_path):
    ds = tmp_path / "benchmark_hybrid.jsonl"
    manifest = assemble_to_files(
        [_holdout(), _swebench()],
        dataset_path=ds,
        cutoff=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert ds.exists()
    default_manifest = ds.with_suffix(ds.suffix + ".manifest.json")
    assert default_manifest.exists()
    on_disk = json.loads(default_manifest.read_text())
    assert on_disk["total"] == 5
    assert on_disk["contamination_safe"] == 2
    assert on_disk["output_path"] == str(ds)
    assert manifest.total == 5
    # dataset round-trips
    assert len(JSONLStorage(ds).load_all()) == 5


def test_assemble_to_files_custom_manifest_path(tmp_path):
    ds = tmp_path / "bench.jsonl"
    mpath = tmp_path / "custom_manifest.json"
    assemble_to_files([_holdout()], dataset_path=ds, manifest_path=mpath)
    assert mpath.exists()
    assert not ds.with_suffix(ds.suffix + ".manifest.json").exists()
