"""Step definitions for features/benchmark_runner.feature (peer-10s)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from behave import given, then, when  # type: ignore[import-untyped]

from peer import Comment, Review
from peer.benchmark import (
    BugBenchmarkRunner,
    BugLocation,
    BugSample,
    MacroscopeLoader,
    judge_bug_caught,
)


def _bug(bug_id: str, language: str = "python") -> dict[str, Any]:
    return {
        "bug_id": bug_id,
        "repo_url": "https://example/r",
        "commit_sha": "abc",
        "bug_paths": [{"path": "src/foo.py", "start_line": 10, "end_line": 12}],
        "root_cause": "off-by-one",
        "language": language,
    }


# ---------------------------------------------------------------------------
# MacroscopeLoader
# ---------------------------------------------------------------------------


@given("a temp JSONL with two valid Macroscope-shaped bug rows")
def step_temp_jsonl_two(context) -> None:
    tmp = Path(tempfile.mkstemp(suffix=".jsonl")[1])
    rows = [_bug("bug-1"), _bug("bug-2")]
    with tmp.open("w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    context.fixtures["jsonl_path"] = tmp


@given("a temp JSONL with one python bug row and one go bug row")
def step_temp_jsonl_mixed(context) -> None:
    tmp = Path(tempfile.mkstemp(suffix=".jsonl")[1])
    rows = [_bug("py-bug", "python"), _bug("go-bug", "go")]
    with tmp.open("w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    context.fixtures["jsonl_path"] = tmp


@when("I construct a MacroscopeLoader pointing at that file")
def step_construct_loader(context) -> None:
    context.fixtures["loader"] = MacroscopeLoader(context.fixtures["jsonl_path"])


@when("I call MacroscopeLoader.load")
def step_call_load(context) -> None:
    context.fixtures["samples"] = context.fixtures["loader"].load()


@when('I call MacroscopeLoader.load with language "{lang}"')
def step_call_load_lang(context, lang: str) -> None:
    context.fixtures["samples"] = context.fixtures["loader"].load(language=lang)


@then("the returned BugSample list has length {n:d}")
def step_returned_len(context, n: int) -> None:
    got = len(context.fixtures["samples"])
    assert got == n, f"expected {n}, got {got}"


@then('the first BugSample\'s language equals "{lang}"')
def step_first_lang(context, lang: str) -> None:
    got = context.fixtures["samples"][0].language
    assert got == lang, f"expected {lang!r}, got {got!r}"


# ---------------------------------------------------------------------------
# judge_bug_caught
# ---------------------------------------------------------------------------


class _RecordingJudgeClient:
    def __init__(self, response_text: str = "CAUGHT — fine") -> None:
        self.response_text = response_text
        self.call_count = 0

        class _Block:
            def __init__(self, text: str) -> None:
                self.text = text

        class _Resp:
            def __init__(self, text: str) -> None:
                self.content = [_Block(text)]

        self._Resp = _Resp

    class _Messages:
        def __init__(self, parent: _RecordingJudgeClient) -> None:
            self._parent = parent

        def create(self, **kwargs: Any) -> Any:
            self._parent.call_count += 1
            return self._parent._Resp(self._parent.response_text)

    @property
    def messages(self) -> _Messages:
        return self._Messages(self)


@given('a fake judge client that always returns "{text}"')
def step_fake_judge_caught(context, text: str) -> None:
    context.fixtures["judge_client"] = _RecordingJudgeClient(response_text=text)


@given("a fake judge client that records call count")
def step_fake_judge_records(context) -> None:
    # Default response is CAUGHT — but in the prefilter scenarios the judge
    # should never be invoked, so the choice doesn't matter.
    context.fixtures["judge_client"] = _RecordingJudgeClient(response_text="CAUGHT")


@given('a BugSample at "{path}":{lo:d}-{hi:d} with root_cause "{rc}"')
def step_bugsample_at(context, path: str, lo: int, hi: int, rc: str) -> None:
    context.fixtures["bug"] = BugSample(
        bug_id="b",
        repo_url="https://example/r",
        commit_sha="abc",
        bug_paths=[BugLocation(path=path, start_line=lo, end_line=hi)],
        root_cause=rc,
        language="python",
    )


@given('a peer Comment at "{path}":{line:d}')
def step_peer_comment_at(context, path: str, line: int) -> None:
    context.fixtures["comment"] = Comment(
        path=path,
        line=line,
        severity="minor",
        body="b",
        rationale="r",
    )


@when("I call judge_bug_caught")
def step_call_judge(context) -> None:
    context.fixtures["judge_result"] = judge_bug_caught(
        context.fixtures["bug"],
        context.fixtures["comment"],
        client=context.fixtures["judge_client"],
    )


@then("the returned boolean is True")
def step_judge_true(context) -> None:
    assert context.fixtures["judge_result"] is True


@then("the returned boolean is False")
def step_judge_false(context) -> None:
    assert context.fixtures["judge_result"] is False


@then("the judge client was called {n:d} times")
@then("the judge client was called {n:d} time")
def step_judge_calls(context, n: int) -> None:
    got = context.fixtures["judge_client"].call_count
    assert got == n, f"expected {n}, got {got}"


# ---------------------------------------------------------------------------
# BugBenchmarkRunner
# ---------------------------------------------------------------------------


@given('a fake bug-judge that catches bug "{caught_id}" and misses bug "{miss_id}"')
def step_fake_judge_selective(context, caught_id: str, miss_id: str) -> None:
    def _fake_judge(
        bug: BugSample,
        peer_comment: Comment,
        *,
        client: Any = None,
        judge_model: str = "x",
        proximity: int = 10,
    ) -> bool:
        return bug.bug_id == caught_id

    context.fixtures["fake_judge"] = _fake_judge


@given("a stub PRReviewer that returns one Comment in proximity for both bugs")
def step_stub_pr_reviewer(context) -> None:
    class _Reviewer:
        model = "test:stub"

        def review(self, _pr_url: str) -> Review:
            return Review(
                comments=[
                    Comment(
                        path="src/foo.py",
                        line=11,
                        severity="minor",
                        body="b",
                        rationale="r",
                    )
                ],
                usage={"input_tokens": 0, "output_tokens": 0, "model": "test:stub"},
            )

    context.fixtures["pr_reviewer"] = _Reviewer()


@given('a 2-bug BugDataset with ids "{a}" and "{b}"')
def step_two_bug_dataset(context, a: str, b: str) -> None:
    samples = [
        BugSample(
            bug_id=a,
            repo_url="https://example/r",
            commit_sha="abc",
            bug_paths=[BugLocation(path="src/foo.py", start_line=10, end_line=12)],
            root_cause="off-by-one",
            language="python",
        ),
        BugSample(
            bug_id=b,
            repo_url="https://example/r",
            commit_sha="def",
            bug_paths=[BugLocation(path="src/foo.py", start_line=10, end_line=12)],
            root_cause="null deref",
            language="python",
        ),
    ]
    context.fixtures["bug_dataset"] = samples


@when("I run BugBenchmarkRunner.run")
def step_run_bench(context) -> None:
    runner = BugBenchmarkRunner(
        reviewer=context.fixtures["pr_reviewer"],
        dataset=context.fixtures["bug_dataset"],
        judge_client=object(),  # not used — judge_fn ignores it
        judge_fn=context.fixtures["fake_judge"],
    )
    context.fixtures["report"] = runner.run()


@then("the BenchmarkReport's n_bugs_total equals {n:d}")
def step_report_total(context, n: int) -> None:
    got = context.fixtures["report"].n_bugs_total
    assert got == n, f"expected {n}, got {got}"


@then("the BenchmarkReport's n_bugs_caught equals {n:d}")
def step_report_caught(context, n: int) -> None:
    got = context.fixtures["report"].n_bugs_caught
    assert got == n, f"expected {n}, got {got}"


@then("the BenchmarkReport's detection_rate equals {val:f}")
def step_report_dr(context, val: float) -> None:
    got = context.fixtures["report"].detection_rate
    assert abs((got or 0.0) - val) < 1e-9, f"expected {val}, got {got}"


@then("the BenchmarkReport's per_bug entries have length {n:d}")
def step_report_perbug_len(context, n: int) -> None:
    got = len(context.fixtures["report"].per_bug)
    assert got == n, f"expected {n}, got {got}"


@then('the per_bug result for "{bug_id}" has reason non-empty')
def step_perbug_reason(context, bug_id: str) -> None:
    report = context.fixtures["report"]
    match = next(r for r in report.per_bug if r.bug_id == bug_id)
    assert match.reason, f"reason for {bug_id} unexpectedly empty"


@then('the per_bug result for "{bug_id}" has caught equal to True')
def step_perbug_caught(context, bug_id: str) -> None:
    report = context.fixtures["report"]
    match = next(r for r in report.per_bug if r.bug_id == bug_id)
    assert match.caught is True, f"expected caught=True, got {match.caught!r}"


# ---------------------------------------------------------------------------
# CLI parsing
# ---------------------------------------------------------------------------
# Note: `I parse "..."` is provided by features/steps/eval_v02_followups_steps.py.


@then('the parsed args has ds_cmd equal to "{val}"')
def step_args_ds_cmd(context, val: str) -> None:
    args = context.fixtures["args"]
    assert args.ds_cmd == val, f"expected {val!r}, got {args.ds_cmd!r}"


@then("the parsed args has yes equal to True")
def step_args_yes_true(context) -> None:
    args = context.fixtures["args"]
    assert args.yes is True, f"expected True, got {args.yes!r}"


@then('the parsed args has dataset equal to "{val}"')
def step_args_dataset_eq(context, val: str) -> None:
    args = context.fixtures["args"]
    assert args.dataset == val, f"expected {val!r}, got {args.dataset!r}"
