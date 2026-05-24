"""Step definitions for features/peer_config.feature."""

from __future__ import annotations

import tempfile
from pathlib import Path

from behave import given, then, when  # type: ignore[import-untyped]

from peer.config import (
    PeerConfig,
    ResolvedRule,
    Rule,
    apply_severity_bounds,
    load_config,
)
from peer.types import Comment, Context, ContextHunk


def _make_context(paths: list[str]) -> Context:
    hunks = [
        ContextHunk(
            path=p,
            old_start=10,
            old_lines=2,
            new_start=10,
            new_lines=2,
            diff_text="@@ -10,2 +10,2 @@\n line\n line",
        )
        for p in paths
    ]
    return Context(
        pr_url="https://example/test/pull/1",
        owner="test",
        repo="test",
        number=1,
        title="t",
        body="",
        head_sha="sha",
        hunks=hunks,
        prior_comments=[],
        token_estimate=0,
    )


# ---------------------------------------------------------------------------
# Empty PeerConfig
# ---------------------------------------------------------------------------


@when("I construct a PeerConfig with no arguments")
def step_construct_peerconfig_empty(context) -> None:
    context.fixtures["cfg"] = PeerConfig()


@then("the PeerConfig's rules list is empty")
def step_rules_empty(context) -> None:
    assert context.fixtures["cfg"].rules == []


@then("the PeerConfig's ignore.glob is the empty list")
def step_ignore_glob_empty(context) -> None:
    assert context.fixtures["cfg"].ignore.glob == []


# ---------------------------------------------------------------------------
# for_path
# ---------------------------------------------------------------------------


@given("a PeerConfig with no rules")
def step_given_peerconfig_no_rules(context) -> None:
    context.fixtures["cfg"] = PeerConfig()


@when('I call for_path on "{path}"')
def step_call_for_path(context, path: str) -> None:
    context.fixtures["resolved"] = context.fixtures["cfg"].for_path(path)


@then("the resolved rule has no conventions_text")
def step_resolved_no_conventions(context) -> None:
    assert context.fixtures["resolved"].conventions_texts == []


@then("the resolved rule has no severity_floor")
def step_resolved_no_floor(context) -> None:
    assert context.fixtures["resolved"].severity_floor is None


@then("the resolved rule has no severity_cap")
def step_resolved_no_cap(context) -> None:
    assert context.fixtures["resolved"].severity_cap is None


@given('a PeerConfig with rule A matching "{path_a}" with conventions "{text_a}"')
def step_given_two_rule_a(context, path_a: str, text_a: str) -> None:
    context.fixtures["_rule_a"] = Rule(paths=[path_a], conventions_text=text_a)


@given('rule B matching "{path_b}" with conventions "{text_b}"')
def step_given_two_rule_b(context, path_b: str, text_b: str) -> None:
    context.fixtures["_rule_b"] = Rule(paths=[path_b], conventions_text=text_b)
    # Now build PeerConfig with both rules in order A, B
    context.fixtures["cfg"] = PeerConfig(
        rules=[context.fixtures["_rule_a"], context.fixtures["_rule_b"]]
    )


@then('the resolved rule\'s conventions_texts equals ["{a}", "{b}"]')
def step_resolved_conventions_two(context, a: str, b: str) -> None:
    got = context.fixtures["resolved"].conventions_texts
    assert got == [a, b], f"expected [{a!r}, {b!r}], got {got!r}"


# ---------------------------------------------------------------------------
# severity bounds (most-restrictive)
# ---------------------------------------------------------------------------


@given('a PeerConfig with rule "{p1}" severity_cap {cap1} and rule "{p2}" severity_cap {cap2}')
def step_given_two_caps(context, p1: str, cap1: str, p2: str, cap2: str) -> None:
    context.fixtures["cfg"] = PeerConfig(
        rules=[
            Rule(paths=[p1], severity_cap=cap1),  # type: ignore[arg-type]
            Rule(paths=[p2], severity_cap=cap2),  # type: ignore[arg-type]
        ]
    )


@given('a PeerConfig with rule "{p1}" severity_floor {floor}')
def step_given_floor(context, p1: str, floor: str) -> None:
    context.fixtures["cfg"] = PeerConfig(
        rules=[Rule(paths=[p1], severity_floor=floor)]  # type: ignore[arg-type]
    )


@when('I apply severity bounds to a Comment with path "{path}" and severity "{sev}"')
def step_apply_severity_bounds(context, path: str, sev: str) -> None:
    cmt = Comment(path=path, line=1, severity=sev, body="b", rationale="r")  # type: ignore[arg-type]
    resolved = context.fixtures["cfg"].for_path(path)
    context.fixtures["bounded"] = apply_severity_bounds(cmt, resolved)


@then('the resulting Comment\'s severity equals "{sev}"')
def step_bounded_severity(context, sev: str) -> None:
    got = context.fixtures["bounded"].severity
    assert got == sev, f"expected {sev}, got {got}"


# ---------------------------------------------------------------------------
# ignore filtering
# ---------------------------------------------------------------------------


@given('a PeerConfig with ignore.glob ["{a}", "{b}"]')
def step_given_ignore_glob(context, a: str, b: str) -> None:
    context.fixtures["cfg"] = PeerConfig(ignore={"glob": [a, b]})  # type: ignore[arg-type]


@given('a Context with hunks for "{a}" and "{b}"')
def step_given_context_two_hunks(context, a: str, b: str) -> None:
    context.fixtures["ctx"] = _make_context([a, b])


@when("I apply ignore filters")
def step_apply_ignore(context) -> None:
    context.fixtures["filtered"] = context.fixtures["cfg"].filter_context(context.fixtures["ctx"])


@then("the filtered Context has {n:d} hunk")
@then("the filtered Context has {n:d} hunks")
def step_filtered_hunks_n(context, n: int) -> None:
    got = len(context.fixtures["filtered"].hunks)
    assert got == n, f"expected {n} hunks, got {got}"


@then('the remaining hunk\'s path equals "{path}"')
def step_remaining_hunk_path(context, path: str) -> None:
    got = context.fixtures["filtered"].hunks[0].path
    assert got == path, f"expected path={path}, got {got}"


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------


@given('a temp directory containing a .peer.yaml with content "{content}"')
def step_given_temp_with_yaml(context, content: str) -> None:
    # Unescape the literal `\n` in the feature file's string.
    actual = content.encode().decode("unicode_escape")
    tmp = Path(tempfile.mkdtemp(prefix="peer_cfg_test_"))
    (tmp / ".peer.yaml").write_text(actual)
    context.fixtures["tmp_dir"] = tmp


@given("a temp directory with no .peer.yaml")
def step_given_temp_no_yaml(context) -> None:
    context.fixtures["tmp_dir"] = Path(tempfile.mkdtemp(prefix="peer_cfg_empty_"))


@when("I call load_config on that directory")
def step_call_load_config(context) -> None:
    context.fixtures["loaded"] = load_config(context.fixtures["tmp_dir"])


@then('the loaded PeerConfig\'s agent.extra_instructions equals "{val}"')
def step_loaded_extra_instructions(context, val: str) -> None:
    got = context.fixtures["loaded"].agent.extra_instructions
    assert got == val, f"expected {val!r}, got {got!r}"


@then("the loaded PeerConfig has no rules")
def step_loaded_no_rules(context) -> None:
    assert context.fixtures["loaded"].rules == []
