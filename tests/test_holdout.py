"""Unit tests for the fresh-holdout revert miner (peer-4z5).

All GitHub I/O is a stub `gh` runner — no network, no quota.
"""

from __future__ import annotations

from datetime import datetime, timezone

from peer.dataset.holdout import (
    RevertPair,
    _hunk_new_start,
    find_revert_pairs,
    mine_holdout,
    parse_revert_pr,
    revert_pair_to_gold_sample,
)

CUTOFF = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _dt(s: str) -> str:
    return s  # ISO strings as gh returns them


# --------------------------------------------------------------------------
# parse_revert_pr
# --------------------------------------------------------------------------


def test_parse_revert_title_with_number():
    pr = {"number": 50, "title": 'Revert "Add fast path" (#42)', "body": "", "mergedAt": None}
    pair = parse_revert_pr(pr, "o/r")
    assert pair is not None
    assert pair.fix_pr_number == 50
    assert pair.buggy_pr_number == 42


def test_parse_revert_title_canonical_squash_format():
    # GitHub's canonical squash-revert: the (#N) sits *inside* the closing quote.
    pr = {
        "number": 35346,
        "title": 'Revert "[compiler] Fix VariableDeclarator source location (#35129)"',
        "body": "This broke main.",
        "mergedAt": "2026-02-01T00:00:00Z",
    }
    pair = parse_revert_pr(pr, "facebook/react")
    assert pair is not None
    assert pair.buggy_pr_number == 35129


def test_parse_revert_body_commit_sha():
    pr = {
        "number": 51,
        "title": "Revert the broken cache change",
        "body": "This reverts commit a1b2c3d4e5f6.",
        "mergedAt": None,
    }
    pair = parse_revert_pr(pr, "o/r")
    assert pair is not None
    assert pair.reverted_sha == "a1b2c3d4e5f6"
    assert pair.buggy_pr_number is None


def test_parse_non_revert_returns_none():
    pr = {"number": 7, "title": "Add a feature", "body": "nothing here", "mergedAt": None}
    assert parse_revert_pr(pr, "o/r") is None


def test_parse_unlinkable_revert_returns_none():
    pr = {"number": 8, "title": "Revert something vague", "body": "no link", "mergedAt": None}
    assert parse_revert_pr(pr, "o/r") is None


# --------------------------------------------------------------------------
# find_revert_pairs (contamination cutoff + linkability filter)
# --------------------------------------------------------------------------


def test_find_revert_pairs_filters_by_cutoff_and_link():
    prs = [
        {
            "number": 100,
            "title": 'Revert "X" (#90)',
            "body": "",
            "mergedAt": "2026-03-01T00:00:00Z",
        },
        {  # before cutoff -> dropped
            "number": 101,
            "title": 'Revert "Y" (#91)',
            "body": "",
            "mergedAt": "2025-06-01T00:00:00Z",
        },
        {  # not a revert -> dropped
            "number": 102,
            "title": "Normal PR",
            "body": "",
            "mergedAt": "2026-03-01T00:00:00Z",
        },
        {  # revert but unlinkable -> dropped
            "number": 103,
            "title": "Revert stuff",
            "body": "no link",
            "mergedAt": "2026-03-01T00:00:00Z",
        },
    ]

    def gh(args):
        assert args[0] == "pr" and args[1] == "list"
        return prs

    pairs = find_revert_pairs("o/r", since=CUTOFF, gh=gh)
    assert [p.fix_pr_number for p in pairs] == [100]
    assert pairs[0].buggy_pr_number == 90


# --------------------------------------------------------------------------
# _hunk_new_start
# --------------------------------------------------------------------------


def test_hunk_new_start_parses_header():
    assert _hunk_new_start("@@ -10,3 +20,4 @@ def foo():\n+x") == 20


def test_hunk_new_start_none_when_absent():
    assert _hunk_new_start("") is None
    assert _hunk_new_start("no hunk header here") is None


# --------------------------------------------------------------------------
# revert_pair_to_gold_sample
# --------------------------------------------------------------------------


def _files_gh(meta: dict, files: list[dict]):
    def gh(args):
        if args[0] == "pr" and args[1] == "view":
            return meta
        if args[0] == "api":
            return files
        raise AssertionError(f"unexpected gh args: {args}")

    return gh


def test_revert_pair_to_gold_sample_builds_defects_and_contamination_flag():
    pair = RevertPair(
        repo="o/r",
        fix_pr_number=100,
        fix_merged_at=None,
        fix_title='Revert "X" (#90)',
        buggy_pr_number=90,
        reverted_sha=None,
    )
    meta = {
        "title": "Add fast path",
        "body": "speeds things up",
        "mergedAt": "2026-02-01T00:00:00Z",  # after cutoff
        "url": "https://github.com/o/r/pull/90",
    }
    files = [
        {"filename": "src/a.py", "patch": "@@ -1,2 +3,5 @@\n+bug"},
        {"filename": "src/b.py", "patch": "@@ -10,1 +10,2 @@\n+more"},
    ]
    gs = revert_pair_to_gold_sample(pair, cutoff=CUTOFF, gh=_files_gh(meta, files))
    assert gs is not None
    assert gs.pr_url == "https://github.com/o/r/pull/90"
    assert len(gs.gold_defects) == 2
    assert gs.gold_defects[0].path == "src/a.py"
    assert gs.gold_defects[0].line == 3
    assert gs.gold_defects[0].source == "fresh-holdout:revert:#100"
    assert gs.metadata.contamination_safe is True
    assert gs.metadata.has_followup_bugfix is True


def test_revert_pair_contamination_false_when_merged_before_cutoff():
    pair = RevertPair("o/r", 100, None, 'Revert "X" (#90)', 90, None)
    meta = {"title": "X", "body": "", "mergedAt": "2025-01-01T00:00:00Z", "url": "u"}
    files = [{"filename": "a.py", "patch": "@@ -1 +1 @@\n+x"}]
    gs = revert_pair_to_gold_sample(pair, cutoff=CUTOFF, gh=_files_gh(meta, files))
    assert gs is not None
    assert gs.metadata.contamination_safe is False


def test_revert_pair_no_files_returns_none():
    pair = RevertPair("o/r", 100, None, 'Revert "X" (#90)', 90, None)
    meta = {"title": "X", "body": "", "mergedAt": "2026-02-01T00:00:00Z", "url": "u"}
    gs = revert_pair_to_gold_sample(pair, cutoff=CUTOFF, gh=_files_gh(meta, []))
    assert gs is None


# --------------------------------------------------------------------------
# mine_holdout (end to end, mocked)
# --------------------------------------------------------------------------


def test_mine_holdout_end_to_end():
    list_resp = [
        {
            "number": 100,
            "title": 'Revert "X" (#90)',
            "body": "",
            "mergedAt": "2026-03-01T00:00:00Z",
        },
    ]
    meta = {
        "title": "Add X",
        "body": "",
        "mergedAt": "2026-02-01T00:00:00Z",
        "url": "https://github.com/o/r/pull/90",
    }
    files = [{"filename": "src/a.py", "patch": "@@ -1,1 +1,2 @@\n+bug"}]

    def gh(args):
        if args[0] == "pr" and args[1] == "list":
            return list_resp
        if args[0] == "pr" and args[1] == "view":
            return meta
        if args[0] == "api":
            return files
        raise AssertionError(args)

    samples = mine_holdout(["o/r"], cutoff=CUTOFF, gh=gh)
    assert len(samples) == 1
    assert samples[0].metadata.contamination_safe is True
    assert samples[0].gold_defects[0].source == "fresh-holdout:revert:#100"
