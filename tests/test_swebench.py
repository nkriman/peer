"""Unit tests for the SWE-bench_Verified -> GoldSample reconstruction (peer-4z5)."""

from __future__ import annotations

import json

from peer.dataset.swebench import (
    _parse_instance_id,
    swebench_jsonl_to_gold_samples,
    swebench_record_to_gold_sample,
    swebench_records_to_gold_samples,
)

_PATCH = (
    "diff --git a/src/foo.py b/src/foo.py\n"
    "--- a/src/foo.py\n"
    "+++ b/src/foo.py\n"
    "@@ -41,2 +41,2 @@ def handler():\n"
    " ctx\n"
    "-    return None\n"
    "+    return result\n"
)

_MULTI_FILE_PATCH = _PATCH + (
    "diff --git a/src/bar.py b/src/bar.py\n"
    "--- a/src/bar.py\n"
    "+++ b/src/bar.py\n"
    "@@ -10,1 +10,2 @@ class B:\n"
    " keep\n"
    "+    added = 1\n"
)


def _rec(instance_id="django__django-11099", patch=_PATCH, problem="It crashes on empty input."):
    return {
        "instance_id": instance_id,
        "repo": "django/django",
        "base_commit": "abc123",
        "patch": patch,
        "problem_statement": problem,
    }


# --------------------------------------------------------------------------
# instance_id parsing
# --------------------------------------------------------------------------


def test_parse_instance_id_simple():
    assert _parse_instance_id("django__django-11099") == ("django", "django", 11099)


def test_parse_instance_id_hyphenated_owner_and_repo():
    assert _parse_instance_id("sphinx-doc__sphinx-8721") == ("sphinx-doc", "sphinx", 8721)
    assert _parse_instance_id("scikit-learn__scikit-learn-10297") == (
        "scikit-learn",
        "scikit-learn",
        10297,
    )


def test_parse_instance_id_rejects_garbage():
    assert _parse_instance_id("nonsense") is None
    assert _parse_instance_id("no__number-here") is None


# --------------------------------------------------------------------------
# record -> GoldSample
# --------------------------------------------------------------------------


def test_record_to_gold_sample_basic():
    gs = swebench_record_to_gold_sample(_rec())
    assert gs is not None
    assert gs.pr_url == "https://github.com/django/django/pull/11099"
    assert gs.head_sha == "abc123"
    assert len(gs.gold_defects) == 1
    d = gs.gold_defects[0]
    assert d.path == "src/foo.py"
    assert d.line == 41  # source_start = buggy-file line
    assert d.source == "crbench-recon:swe-verified:django__django-11099"
    assert d.confidence == "high"
    assert gs.metadata.contamination_safe is False  # SWE-bench is in training data


def test_record_multi_file_yields_one_defect_per_file():
    gs = swebench_record_to_gold_sample(_rec(patch=_MULTI_FILE_PATCH))
    assert gs is not None
    paths = sorted(d.path for d in gs.gold_defects)
    assert paths == ["src/bar.py", "src/foo.py"]


def test_problem_statement_truncated():
    gs = swebench_record_to_gold_sample(_rec(problem="x" * 5000), max_desc_chars=100)
    assert gs is not None
    assert len(gs.gold_defects[0].description) == 100


def test_missing_patch_returns_none():
    rec = _rec()
    rec["patch"] = ""
    assert swebench_record_to_gold_sample(rec) is None


def test_missing_instance_id_returns_none():
    rec = _rec()
    del rec["instance_id"]
    assert swebench_record_to_gold_sample(rec) is None


def test_unparseable_patch_yields_no_sample():
    assert swebench_record_to_gold_sample(_rec(patch="this is not a diff")) is None


def test_unknown_instance_id_shape_uses_synthetic_url():
    gs = swebench_record_to_gold_sample(_rec(instance_id="weirdformat"))
    assert gs is not None
    assert gs.pr_url == "swebench://weirdformat"


# --------------------------------------------------------------------------
# batch + jsonl
# --------------------------------------------------------------------------


def test_records_to_gold_samples_skips_bad():
    recs = [_rec(), {"instance_id": "x", "patch": ""}, _rec(instance_id="sympy__sympy-2000")]
    out = swebench_records_to_gold_samples(recs)
    assert len(out) == 2


def test_jsonl_roundtrip(tmp_path):
    p = tmp_path / "swe.jsonl"
    p.write_text(
        json.dumps(_rec())
        + "\n"
        + "\n"
        + "{bad json\n"
        + json.dumps(_rec(instance_id="a__b-3"))
        + "\n"
    )
    out = swebench_jsonl_to_gold_samples(p)
    # 2 valid records; blank line + malformed line skipped.
    assert len(out) == 2
