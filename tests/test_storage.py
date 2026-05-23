"""Tests for peer.dataset.storage.JSONLStorage."""

from __future__ import annotations

import pytest

from peer.dataset.storage import JSONLStorage
from peer.dataset.types import GoldSample, GoldSampleMetadata
from peer.exceptions import InvalidGoldSample


def _sample(pr_url: str, defect_count: int = 0) -> GoldSample:
    return GoldSample(
        pr_url=pr_url,
        pr_title=f"Title {pr_url}",
        pr_body="",
        head_sha="abc",
        gold_defects=[],
        metadata=GoldSampleMetadata(
            raw_comment_count=defect_count,
            defect_comment_count=defect_count,
        ),
    )


def test_load_all_returns_empty_when_file_missing(tmp_path):
    storage = JSONLStorage(tmp_path / "ds.jsonl")
    assert storage.load_all() == []


def test_add_then_load_roundtrip(tmp_path):
    path = tmp_path / "ds.jsonl"
    storage = JSONLStorage(path)
    s1 = _sample("https://github.com/o/r/pull/1")
    s2 = _sample("https://github.com/o/r/pull/2")
    storage.add(s1)
    storage.add(s2)

    loaded = storage.load_all()
    assert len(loaded) == 2
    assert {s.pr_url for s in loaded} == {s1.pr_url, s2.pr_url}


def test_add_overwrites_existing_pr_url(tmp_path):
    path = tmp_path / "ds.jsonl"
    storage = JSONLStorage(path)
    s_v1 = _sample("https://github.com/o/r/pull/1", defect_count=1)
    s_v2 = _sample("https://github.com/o/r/pull/1", defect_count=5)
    storage.add(s_v1)
    storage.add(s_v2)

    loaded = storage.load_all()
    assert len(loaded) == 1, "duplicate pr_url must overwrite, not append"
    assert loaded[0].metadata.defect_comment_count == 5


def test_find_returns_matching_sample(tmp_path):
    storage = JSONLStorage(tmp_path / "ds.jsonl")
    s = _sample("https://github.com/o/r/pull/42")
    storage.add(s)
    found = storage.find("https://github.com/o/r/pull/42")
    assert found is not None
    assert found.pr_url == s.pr_url


def test_find_returns_none_when_missing(tmp_path):
    storage = JSONLStorage(tmp_path / "ds.jsonl")
    assert storage.find("https://github.com/o/r/pull/999") is None


def test_delete_removes_sample(tmp_path):
    storage = JSONLStorage(tmp_path / "ds.jsonl")
    storage.add(_sample("https://github.com/o/r/pull/1"))
    storage.add(_sample("https://github.com/o/r/pull/2"))
    storage.delete("https://github.com/o/r/pull/1")
    remaining = storage.load_all()
    assert len(remaining) == 1
    assert remaining[0].pr_url == "https://github.com/o/r/pull/2"


def test_delete_noop_when_missing(tmp_path):
    storage = JSONLStorage(tmp_path / "ds.jsonl")
    storage.add(_sample("https://github.com/o/r/pull/1"))
    storage.delete("https://github.com/o/r/pull/999")
    assert len(storage.load_all()) == 1


def test_load_all_raises_on_malformed_json(tmp_path):
    path = tmp_path / "ds.jsonl"
    path.write_text("{not json}\n")
    storage = JSONLStorage(path)
    with pytest.raises(InvalidGoldSample) as exc_info:
        storage.load_all()
    # Line number should appear in the message
    assert ":1:" in str(exc_info.value)


def test_load_all_raises_on_schema_violation(tmp_path):
    path = tmp_path / "ds.jsonl"
    # valid JSON but not a valid GoldSample (missing pr_url)
    path.write_text('{"foo": "bar"}\n')
    storage = JSONLStorage(path)
    with pytest.raises(InvalidGoldSample):
        storage.load_all()


def test_load_all_skips_blank_lines(tmp_path):
    storage = JSONLStorage(tmp_path / "ds.jsonl")
    storage.add(_sample("https://github.com/o/r/pull/1"))
    # Append a blank line manually
    with storage.path.open("a") as fh:
        fh.write("\n\n")
    loaded = storage.load_all()
    assert len(loaded) == 1


def test_storage_creates_parent_dirs(tmp_path):
    nested = tmp_path / "a" / "b" / "ds.jsonl"
    JSONLStorage(nested)
    assert nested.parent.exists()
