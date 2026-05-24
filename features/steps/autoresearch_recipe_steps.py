"""Step definitions for features/autoresearch_recipe.feature (peer-o4v)."""

from __future__ import annotations

import importlib
import tempfile
from pathlib import Path
from unittest.mock import patch

from behave import given, then, when  # type: ignore[import-untyped]
from pydantic import ValidationError

from peer import Agent, ClaudeReviewer, Recipe
from peer.autoresearch import (
    LEADERBOARD_HEADER,
    UnsafeUtilityFormula,
    append_row,
    parse_utility_formula,
)

# ---------------------------------------------------------------------------
# Recipe
# ---------------------------------------------------------------------------


@when("I construct a Recipe with no arguments")
def step_recipe_default(context) -> None:
    context.fixtures["recipe"] = Recipe()


@then('the Recipe\'s model equals "{val}"')
def step_recipe_model(context, val: str) -> None:
    got = context.fixtures["recipe"].model
    assert got == val, f"expected {val!r}, got {got!r}"


@then("the Recipe's temperature equals {val:f}")
def step_recipe_temp(context, val: float) -> None:
    got = context.fixtures["recipe"].temperature
    assert got == val, f"expected {val}, got {got!r}"


@then("the Recipe's max_tokens equals {val:d}")
def step_recipe_max_tokens(context, val: int) -> None:
    got = context.fixtures["recipe"].max_tokens
    assert got == val, f"expected {val}, got {got!r}"


@then('the Recipe\'s retries equal {{"output": {n:d}}}')
def step_recipe_retries(context, n: int) -> None:
    got = context.fixtures["recipe"].retries
    assert got == {"output": n}, f"expected {{'output': {n}}}, got {got!r}"


@given('a populated Recipe with model "{model}" and temperature {temp:f}')
def step_populated_recipe(context, model: str, temp: float) -> None:
    context.fixtures["original_recipe"] = Recipe(model=model, temperature=temp)


@when("I dump it via to_yaml and parse it back via from_yaml")
def step_yaml_roundtrip(context) -> None:
    orig = context.fixtures["original_recipe"]
    yaml_text = orig.to_yaml()
    context.fixtures["yaml_text"] = yaml_text
    context.fixtures["parsed_recipe"] = Recipe.from_yaml(yaml_text)


@then("the parsed Recipe equals the original")
def step_recipe_equals(context) -> None:
    assert context.fixtures["parsed_recipe"] == context.fixtures["original_recipe"]


@when('I parse a YAML string with a top-level "{key}: {value}"')
def step_parse_unknown_yaml(context, key: str, value: str) -> None:
    try:
        Recipe.from_yaml(f"{key}: {value}")
        context.fixtures["error"] = None
    except Exception as e:
        context.fixtures["error"] = e


@then("a Pydantic ValidationError is raised")
def step_validation_error(context) -> None:
    err = context.fixtures["error"]
    assert isinstance(err, ValidationError), f"expected ValidationError, got {type(err)!r}"


# ---------------------------------------------------------------------------
# ClaudeReviewer temperature
# ---------------------------------------------------------------------------


@given("a ClaudeReviewer constructed with default temperature")
def step_reviewer_default_temp(context) -> None:
    with patch("anthropic.Anthropic"):
        context.fixtures["reviewer"] = ClaudeReviewer(model="anthropic:claude-sonnet-4-6")


@given("a ClaudeReviewer constructed with temperature {temp:f}")
def step_reviewer_with_temp(context, temp: float) -> None:
    with patch("anthropic.Anthropic"):
        context.fixtures["reviewer"] = ClaudeReviewer(
            model="anthropic:claude-sonnet-4-6", temperature=temp
        )


@when("I inspect the kwargs it would pass to messages.create")
def step_inspect_kwargs(context) -> None:
    rv: ClaudeReviewer = context.fixtures["reviewer"]
    # The reviewer's temperature is set as an attribute; the SDK call uses it.
    # Capture by patching the call inline.
    captured: dict = {}

    def _capture(**kwargs):
        captured.update(kwargs)
        # Return a minimal valid response shape.
        from unittest.mock import MagicMock

        m = MagicMock()
        m.content = []
        m.usage.input_tokens = 0
        m.usage.output_tokens = 0
        return m

    rv.client.messages.create.side_effect = _capture  # type: ignore[attr-defined]

    # Call the reviewer on a minimal Context.
    from peer.types import Context, ContextHunk

    ctx = Context(
        pr_url="x",
        owner="o",
        repo="r",
        number=1,
        title="t",
        body="",
        head_sha="s",
        hunks=[
            ContextHunk(
                path="src/foo.py",
                old_start=10,
                old_lines=2,
                new_start=10,
                new_lines=2,
                diff_text="@@ -10,2 +10,2 @@\n line\n line",
            )
        ],
        prior_comments=[],
        token_estimate=0,
    )
    rv.review(ctx)
    context.fixtures["captured_kwargs"] = captured


@then('the kwargs include "temperature" equal to {val:f}')
def step_kwargs_temp(context, val: float) -> None:
    got = context.fixtures["captured_kwargs"].get("temperature")
    assert got == val, f"expected temperature={val}, got {got!r}"


# ---------------------------------------------------------------------------
# Recipe.apply_to_agent
# ---------------------------------------------------------------------------


@given('a fresh Agent and a Recipe with model "{model}" and temperature {temp:f}')
def step_fresh_agent_and_recipe(context, model: str, temp: float) -> None:
    with patch("anthropic.Anthropic"):
        context.fixtures["agent"] = Agent(model="anthropic:claude-sonnet-4-6")
    context.fixtures["recipe"] = Recipe(model=model, temperature=temp)


@when("I call recipe.apply_to_agent")
def step_apply_recipe(context) -> None:
    with patch("anthropic.Anthropic"):
        context.fixtures["recipe"].apply_to_agent(context.fixtures["agent"])


@then("the Agent's reviewer's temperature equals {val:f}")
def step_agent_reviewer_temp(context, val: float) -> None:
    got = context.fixtures["agent"].reviewer.temperature
    assert got == val, f"expected {val}, got {got!r}"


@then('the Agent\'s model equals "{val}"')
def step_agent_model_equals(context, val: str) -> None:
    got = context.fixtures["agent"].model
    assert got == val, f"expected {val!r}, got {got!r}"


@when('I construct an Agent with model "{model}" and recipe model "{recipe_model}"')
def step_agent_with_recipe_kwarg(context, model: str, recipe_model: str) -> None:
    with patch("anthropic.Anthropic"):
        context.fixtures["agent"] = Agent(model=model, recipe=Recipe(model=recipe_model))


# ---------------------------------------------------------------------------
# DEFAULT_SYSTEM_PROMPT externalization
# ---------------------------------------------------------------------------


@given("the file prompts/default_system_prompt.md exists with a known marker")
def step_prompt_file_with_marker(context) -> None:
    # Refuse to operate on a file that doesn't look like the real prompt —
    # earlier scenarios occasionally left a corrupted/empty file behind,
    # and snapshotting THAT as "original" then propagated the corruption.
    # Skip the scenario gracefully if the file isn't a real prompt.
    pfile = Path(__file__).resolve().parents[2] / "prompts" / "default_system_prompt.md"
    raw = pfile.read_text()
    if len(raw) < 500 or "GitHub pull request" not in raw:
        context.scenario.skip(
            reason=f"prompts/default_system_prompt.md looks corrupted ({len(raw)} chars); "
            f"restore it first (e.g., `git checkout HEAD -- prompts/default_system_prompt.md`)"
        )
        return
    marker = "AUTORESEARCH_RECIPE_MARKER_42"
    # Strip any leftover marker from a prior (potentially-crashed) run before
    # snapshotting "original" — protects against marker accretion.
    orig = "\n".join(line for line in raw.splitlines() if line.strip() != marker).rstrip() + "\n"
    context.fixtures["_orig_prompt"] = orig
    pfile.write_text(orig + "\n" + marker + "\n")
    context.fixtures["_marker"] = marker
    context.fixtures["_pfile"] = pfile


@when("I freshly import peer.prompts")
def step_reimport_prompts(context) -> None:
    import peer.prompts as _pp

    importlib.reload(_pp)
    context.fixtures["reloaded_prompt_text"] = _pp.DEFAULT_SYSTEM_PROMPT


@then("peer.prompts.DEFAULT_SYSTEM_PROMPT contains the marker")
def step_prompt_has_marker(context) -> None:
    try:
        text = context.fixtures["reloaded_prompt_text"]
        assert context.fixtures["_marker"] in text, (
            f"marker not in reloaded prompt; first 200 chars: {text[:200]!r}"
        )
    finally:
        # Always restore.
        context.fixtures["_pfile"].write_text(context.fixtures["_orig_prompt"])
        # Re-import once more to leave the module clean.
        import peer.prompts as _pp

        importlib.reload(_pp)


# ---------------------------------------------------------------------------
# parse_utility_formula
# ---------------------------------------------------------------------------


@when('I parse the program.md utility block "{formula}"')
def step_parse_formula(context, formula: str) -> None:
    program_md = f"## Utility\n\n```python\n{formula}\n```\n"
    try:
        context.fixtures["utility_fn"] = parse_utility_formula(program_md)
        context.fixtures["formula_error"] = None
    except Exception as e:
        context.fixtures["formula_error"] = e


@when("I parse a None program.md")
def step_parse_none_program(context) -> None:
    context.fixtures["utility_fn"] = parse_utility_formula(None)


@then("evaluating the formula on metrics {{detection_rate: {dr:f}}} returns {expected:f}")
def step_eval_dr(context, dr: float, expected: float) -> None:
    fn = context.fixtures["utility_fn"]
    got = fn({"detection_rate": dr})
    assert abs(got - expected) < 1e-9, f"expected {expected}, got {got}"


@then(
    "evaluating the formula on metrics {{detection_rate: {dr:f}, n_comments_total: {n:d}}} returns {expected:f}"
)
def step_eval_dr_n(context, dr: float, n: int, expected: float) -> None:
    fn = context.fixtures["utility_fn"]
    got = fn({"detection_rate": dr, "n_comments_total": n})
    assert abs(got - expected) < 1e-9, f"expected {expected}, got {got}"


@then("evaluating the resulting formula on metrics {{detection_rate: {dr:f}}} returns {expected:f}")
def step_eval_fallback(context, dr: float, expected: float) -> None:
    fn = context.fixtures["utility_fn"]
    got = fn({"detection_rate": dr})
    assert abs(got - expected) < 1e-9, f"expected {expected}, got {got}"


@then("UnsafeUtilityFormula is raised")
def step_unsafe_raised(context) -> None:
    err = context.fixtures["formula_error"]
    assert isinstance(err, UnsafeUtilityFormula), (
        f"expected UnsafeUtilityFormula, got {type(err)!r}"
    )


# ---------------------------------------------------------------------------
# leaderboard.append_row
# ---------------------------------------------------------------------------


@given("a fresh empty temp file path for the leaderboard")
def step_fresh_leaderboard(context) -> None:
    fd, path = tempfile.mkstemp(suffix=".tsv")
    import os

    os.close(fd)
    os.unlink(path)  # we want a non-existent path
    context.fixtures["board_path"] = Path(path)


@given("a leaderboard file with one prior row")
def step_prior_row(context) -> None:
    fd, path = tempfile.mkstemp(suffix=".tsv")
    import os

    os.close(fd)
    os.unlink(path)
    p = Path(path)
    append_row(
        p,
        commit_sha="abc1234",
        recipe_hash="deadbeef",
        utility=0.05,
        detection_rate=0.05,
        status="ok",
        description="baseline",
    )
    context.fixtures["board_path"] = p


@when('I call append_row with utility {u:f} and status "{status}"')
def step_call_append_simple(context, u: float, status: str) -> None:
    append_row(
        context.fixtures["board_path"],
        commit_sha="abc1234",
        recipe_hash="deadbeef",
        utility=u,
        detection_rate=u,
        status=status,
        description="t",
    )


@when('I call append_row with status "{status}" and description "{desc}"')
def step_call_append_status_desc(context, status: str, desc: str) -> None:
    append_row(
        context.fixtures["board_path"],
        commit_sha="abc1234",
        recipe_hash="deadbeef",
        utility=0.0,
        detection_rate=0.0,
        status=status,
        description=desc,
    )


@when("I call append_row twice more with utility {u1:f} and utility {u2:f}")
def step_call_append_twice(context, u1: float, u2: float) -> None:
    p = context.fixtures["board_path"]
    for u in (u1, u2):
        append_row(
            p,
            commit_sha="abc1234",
            recipe_hash="deadbeef",
            utility=u,
            detection_rate=u,
            status="ok",
            description="t",
        )


@then("the file's first line equals the canonical TSV header")
def step_first_line_header(context) -> None:
    text = context.fixtures["board_path"].read_text()
    first = text.splitlines()[0]
    assert first == LEADERBOARD_HEADER, f"expected header, got {first!r}"


@then("the file has exactly {n:d} lines total")
@then("the file has exactly {n:d} non-empty lines")
def step_line_count(context, n: int) -> None:
    text = context.fixtures["board_path"].read_text()
    actual = len([line for line in text.splitlines() if line])
    assert actual == n, f"expected {n} lines, got {actual}: {text!r}"


@then("the file's last row's status column is \"{val}\"")
def step_last_status(context, val: str) -> None:
    text = context.fixtures["board_path"].read_text()
    last = text.splitlines()[-1]
    cols = last.split("\t")
    # status is the 10th column (index 9)
    assert cols[9] == val, f"expected status={val!r}, got {cols[9]!r}"


@then("the file's last row's description column is \"{val}\"")
def step_last_desc(context, val: str) -> None:
    text = context.fixtures["board_path"].read_text()
    last = text.splitlines()[-1]
    cols = last.split("\t")
    assert cols[10] == val, f"expected description={val!r}, got {cols[10]!r}"
