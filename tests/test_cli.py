"""Tests for peer.cli._make_parser argument parsing only."""

from __future__ import annotations

from pathlib import Path

import pytest

from peer.cli import _make_parser


def test_parser_review_required_args():
    parser = _make_parser()
    args = parser.parse_args(["review", "https://github.com/o/r/pull/1"])
    assert args.cmd == "review"
    assert args.pr_url == "https://github.com/o/r/pull/1"
    assert args.model == "claude-sonnet-4-6"
    assert args.system_prompt_file is None


def test_parser_review_with_overrides():
    parser = _make_parser()
    args = parser.parse_args(
        [
            "review",
            "https://github.com/o/r/pull/1",
            "--model",
            "claude-opus-4-7",
            "--system-prompt-file",
            "prompts/foo.txt",
        ]
    )
    assert args.model == "claude-opus-4-7"
    assert args.system_prompt_file == Path("prompts/foo.txt")


def test_parser_review_missing_pr_url_fails():
    parser = _make_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["review"])


def test_parser_eval_defaults():
    parser = _make_parser()
    args = parser.parse_args(["eval"])
    assert args.cmd == "eval"
    assert isinstance(args.dataset, Path)
    assert args.model == "claude-sonnet-4-6"
    assert args.baseline is None
    assert args.out is None


def test_parser_eval_with_baseline_and_out():
    parser = _make_parser()
    args = parser.parse_args(
        [
            "eval",
            "--dataset",
            "my.jsonl",
            "--baseline",
            "old.json",
            "--out",
            "new.json",
        ]
    )
    assert args.dataset == Path("my.jsonl")
    assert args.baseline == Path("old.json")
    assert args.out == Path("new.json")


def test_parser_dataset_add_required():
    parser = _make_parser()
    args = parser.parse_args(["dataset", "add", "https://github.com/o/r/pull/1"])
    assert args.cmd == "dataset"
    assert args.ds_cmd == "add"
    assert args.pr_url == "https://github.com/o/r/pull/1"
    assert args.auto_accept is False


def test_parser_dataset_add_auto_accept():
    parser = _make_parser()
    args = parser.parse_args(["dataset", "add", "https://github.com/o/r/pull/1", "--auto-accept"])
    assert args.auto_accept is True


def test_parser_dataset_add_missing_pr_url_fails():
    parser = _make_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["dataset", "add"])


def test_parser_dataset_list_defaults():
    parser = _make_parser()
    args = parser.parse_args(["dataset", "list"])
    assert args.ds_cmd == "list"
    assert args.show_classifications is False


def test_parser_dataset_list_show_classifications():
    parser = _make_parser()
    args = parser.parse_args(["dataset", "list", "--show-classifications"])
    assert args.show_classifications is True


def test_parser_dataset_show_required():
    parser = _make_parser()
    args = parser.parse_args(["dataset", "show", "https://github.com/o/r/pull/2"])
    assert args.cmd == "dataset"
    assert args.ds_cmd == "show"
    assert args.pr_url == "https://github.com/o/r/pull/2"


def test_parser_dataset_show_missing_pr_url_fails():
    parser = _make_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["dataset", "show"])


def test_parser_missing_subcommand_fails():
    parser = _make_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_parser_unknown_subcommand_fails():
    parser = _make_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["bogus"])


def test_parser_dataset_missing_subcommand_fails():
    parser = _make_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["dataset"])


def test_parser_verbose_flag_global():
    parser = _make_parser()
    args = parser.parse_args(["-v", "review", "https://github.com/o/r/pull/1"])
    assert args.verbose is True
