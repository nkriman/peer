"""Step definitions for features/dataset_split.feature (peer-iaj)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from behave import given, then, when  # type: ignore[import-untyped]

from peer.dataset import load_split


def _write_dataset(path: Path, n: int) -> None:
    with path.open("w") as fh:
        for i in range(n):
            row = {
                "pr_url": f"https://example/p{i}",
                "pr_title": "t",
                "pr_body": "",
                "gold_defects": [],
            }
            fh.write(json.dumps(row) + "\n")


@given(
    'a temp dataset "{base}" with {n_base:d} samples and a sibling "{sib}" with {n_sib:d} samples'
)
def step_temp_with_sibling(context, base: str, n_base: int, sib: str, n_sib: int) -> None:
    tmpdir = Path(tempfile.mkdtemp())
    base_path = tmpdir / base
    sib_path = tmpdir / sib
    _write_dataset(base_path, n_base)
    _write_dataset(sib_path, n_sib)
    context.fixtures["base_path"] = base_path
    context.fixtures["sib_path"] = sib_path


@given('a temp dataset "{base}" with {n:d} samples and no sibling test file')
def step_temp_no_sibling(context, base: str, n: int) -> None:
    tmpdir = Path(tempfile.mkdtemp())
    base_path = tmpdir / base
    _write_dataset(base_path, n)
    context.fixtures["base_path"] = base_path


@given('a temp dataset "{base}" with {n:d} samples')
def step_temp_only(context, base: str, n: int) -> None:
    tmpdir = Path(tempfile.mkdtemp())
    base_path = tmpdir / base
    _write_dataset(base_path, n)
    context.fixtures["base_path"] = base_path


@when('I call load_split with base_path "{base}" and split "{split}"')
def step_call_load_split(context, base: str, split: str) -> None:
    try:
        samples = load_split(context.fixtures["base_path"], split)
        context.fixtures["samples"] = samples
        context.fixtures["findings"] = samples  # reuse linter_context's length-check step
        context.fixtures["error"] = None
    except Exception as e:
        context.fixtures["samples"] = None
        context.fixtures["error"] = e


# Note: `the returned list has length N` is provided by
# features/steps/linter_context_steps.py — it reads context.fixtures["findings"].
# We mirror our "samples" into "findings" in the When-step.


@then("ValueError is raised")
def step_value_error(context) -> None:
    err = context.fixtures.get("error")
    assert isinstance(err, ValueError), f"expected ValueError, got {type(err)!r}"
