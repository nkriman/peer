"""Step definitions for features/benchmark.feature."""

from __future__ import annotations

from behave import then, when  # type: ignore[import-untyped]
from pydantic import ValidationError

from peer.benchmark import (
    PUBLISHED_BASELINES,
    BenchmarkReport,
    BugLocation,
    BugSample,
)
from peer.eval.types import AgentConfig

# ---------------------------------------------------------------------------
# BugLocation
# ---------------------------------------------------------------------------


@when('I construct a BugLocation with path "{path}", start_line {s:d}, end_line {e:d}')
def step_construct_bug_location(context, path: str, s: int, e: int) -> None:
    context.fixtures["loc"] = BugLocation(path=path, start_line=s, end_line=e)


@then('the BugLocation\'s path equals "{path}"')
def step_loc_path(context, path: str) -> None:
    assert context.fixtures["loc"].path == path


@then("the BugLocation's start_line equals {n:d}")
def step_loc_start(context, n: int) -> None:
    assert context.fixtures["loc"].start_line == n


@then("the BugLocation's end_line equals {n:d}")
def step_loc_end(context, n: int) -> None:
    assert context.fixtures["loc"].end_line == n


# ---------------------------------------------------------------------------
# BugSample
# ---------------------------------------------------------------------------


@when('I construct a BugSample with bug_id "{bid}", language "{lang}", and two BugLocations')
def step_construct_bug_sample(context, bid: str, lang: str) -> None:
    context.fixtures["sample"] = BugSample(
        bug_id=bid,
        bug_paths=[
            BugLocation(path="src/foo.py", start_line=10, end_line=12),
            BugLocation(path="src/bar.py", start_line=20, end_line=22),
        ],
        root_cause="off-by-one in loop bound",
        language=lang,
    )


@when('I attempt to construct a BugSample with line_coordinate_system "{val}"')
def step_attempt_bad_coord(context, val: str) -> None:
    try:
        BugSample(
            bug_id="x",
            bug_paths=[BugLocation(path="src/foo.py", start_line=1, end_line=1)],
            root_cause="test",
            language="python",
            line_coordinate_system=val,  # type: ignore[arg-type]
        )
        context.error = None
    except Exception as e:
        context.error = e


@then('the BugSample\'s bug_id equals "{bid}"')
def step_sample_bug_id(context, bid: str) -> None:
    assert context.fixtures["sample"].bug_id == bid


@then("the BugSample has {n:d} bug_paths")
def step_sample_n_paths(context, n: int) -> None:
    got = len(context.fixtures["sample"].bug_paths)
    assert got == n, f"expected {n}, got {got}"


@then('the BugSample\'s line_coordinate_system equals "{val}"')
def step_sample_coord(context, val: str) -> None:
    got = context.fixtures["sample"].line_coordinate_system
    assert got == val, f"expected {val}, got {got}"


# Reuse the ValidationError step from patch_suggestions_steps (already defined).


# ---------------------------------------------------------------------------
# PUBLISHED_BASELINES
# ---------------------------------------------------------------------------


@when("I import PUBLISHED_BASELINES from peer.benchmark")
def step_import_baselines(context) -> None:
    context.fixtures["baselines"] = PUBLISHED_BASELINES


@then('PUBLISHED_BASELINES contains a key "{key}"')
def step_baselines_has_key(context, key: str) -> None:
    assert key in context.fixtures["baselines"], (
        f"missing key {key!r}; got {list(context.fixtures['baselines'].keys())}"
    )


@then('each baseline entry has a "detection_rate" field')
def step_each_baseline_has_detection_rate(context) -> None:
    for name, entry in context.fixtures["baselines"].items():
        assert "detection_rate" in entry, f"baseline {name!r} missing detection_rate"


# ---------------------------------------------------------------------------
# BenchmarkReport round-trip
# ---------------------------------------------------------------------------


@when("I construct a minimal BenchmarkReport")
def step_construct_minimal_report(context) -> None:
    context.fixtures["report"] = BenchmarkReport(
        agent_config=AgentConfig(
            model="anthropic:claude-sonnet-4-6", reviewer_class="TestReviewer"
        ),
        dataset_id="test-dataset-v0",
    )


@then("the BenchmarkReport round-trips through model_dump_json + model_validate_json")
def step_report_roundtrip(context) -> None:
    r = context.fixtures["report"]
    raw = r.model_dump_json()
    loaded = BenchmarkReport.model_validate_json(raw)
    assert loaded.dataset_id == r.dataset_id
    assert loaded.run_id == r.run_id


@then('the BenchmarkReport\'s dataset_id equals "{ds}"')
def step_report_dataset_id(context, ds: str) -> None:
    assert context.fixtures["report"].dataset_id == ds


# ---------------------------------------------------------------------------
# InvalidBugSample import
# ---------------------------------------------------------------------------


@when("I import InvalidBugSample from peer.exceptions")
def step_import_invalid_bug_sample(context) -> None:
    from peer.exceptions import InvalidBugSample

    context.fixtures["exc"] = InvalidBugSample


@then("InvalidBugSample is a subclass of PeerError")
def step_invalid_is_peer_error(context) -> None:
    from peer.exceptions import PeerError

    assert issubclass(context.fixtures["exc"], PeerError)
