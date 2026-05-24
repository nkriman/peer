"""Step definitions for features/linter_context.feature."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from unittest.mock import patch

from behave import given, then, when  # type: ignore[import-untyped]

from peer import CodebaseContext, LinterFinding, RuffLinter
from peer.linters import Linter

# ---------------------------------------------------------------------------
# LinterFinding + CodebaseContext shape
# ---------------------------------------------------------------------------


@when("I construct a LinterFinding with all required fields")
def step_construct_linter_finding(context) -> None:
    context.fixtures["finding"] = LinterFinding(
        linter="ruff",
        path="src/foo.py",
        line=10,
        column=5,
        rule_id="E501",
        severity="nit",
        message="line too long",
    )


@then("the LinterFinding round-trips through model_dump_json + model_validate_json")
def step_linter_finding_roundtrip(context) -> None:
    f = context.fixtures["finding"]
    raw = f.model_dump_json()
    loaded = LinterFinding.model_validate_json(raw)
    assert loaded == f


@when("I construct an empty CodebaseContext")
def step_empty_codebase_context(context) -> None:
    context.fixtures["cc"] = CodebaseContext()


@then("the CodebaseContext's linter_findings is the empty list")
def step_cc_linter_findings_empty(context) -> None:
    assert context.fixtures["cc"].linter_findings == []


# ---------------------------------------------------------------------------
# Custom Linter satisfying Protocol
# ---------------------------------------------------------------------------


@given("a custom Linter class returning two fixed findings")
def step_given_custom_linter(context) -> None:
    findings = [
        LinterFinding(
            linter="custom",
            path="src/foo.py",
            line=i + 1,
            rule_id=f"X{i:03d}",
            severity="minor",
            message=f"fake finding {i}",
        )
        for i in range(2)
    ]

    class CustomLinter:
        name = "custom"

        def lint(self, repo_path: Path, target_files: list[str]) -> list[LinterFinding]:
            return list(findings)

    context.fixtures["linter"] = CustomLinter()


@when("I call lint on a fake repo with a single target file")
def step_call_lint(context) -> None:
    linter: Linter = context.fixtures["linter"]
    context.fixtures["findings"] = linter.lint(Path("/tmp/fake"), ["src/foo.py"])


@then("the returned list has length {n:d}")
def step_findings_length(context, n: int) -> None:
    got = len(context.fixtures["findings"])
    assert got == n, f"expected {n}, got {got}"


@then('each finding has linter equal to "{name}"')
def step_each_finding_linter(context, name: str) -> None:
    for f in context.fixtures["findings"]:
        assert f.linter == name


# ---------------------------------------------------------------------------
# Ruff missing CLI
# ---------------------------------------------------------------------------


@given("the ruff CLI is unavailable on PATH")
def step_ruff_unavailable(context) -> None:
    context.fixtures["_which_patch"] = patch("peer.linters.shutil.which", return_value=None)
    context.fixtures["_which_patch"].start()


@when("I call RuffLinter().lint on a repo with one Python file")
def step_call_ruff_missing(context) -> None:
    # Capture warnings from peer.linters
    with context.fixtures.get("_capture_log", _capture_log_ctx()) as logs:
        linter = RuffLinter()
        context.fixtures["findings"] = linter.lint(Path("/tmp/fake"), ["src/foo.py"])
        context.fixtures["log_records"] = logs.records
    context.fixtures["_which_patch"].stop()


@then("the returned list is empty")
def step_findings_empty(context) -> None:
    assert context.fixtures["findings"] == []


@then("a one-time WARNING log mentions ruff installation")
def step_warning_log_mentions_ruff(context) -> None:
    records = context.fixtures.get("log_records", [])
    warnings = [
        r for r in records if r.levelno == logging.WARNING and "ruff" in r.getMessage().lower()
    ]
    assert warnings, f"expected a WARNING about ruff; got {[r.getMessage() for r in records]}"


# ---------------------------------------------------------------------------
# Ruff JSON parse
# ---------------------------------------------------------------------------


def _make_ruff_completed(stdout: str) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=["ruff"], returncode=0, stdout=stdout, stderr="")


@given("a stub subprocess.run that returns ruff JSON output with one E501 finding")
def step_stub_ruff_e501(context) -> None:
    payload = '[{"code":"E501","filename":"src/foo.py","location":{"row":42,"column":81},"message":"line too long"}]'
    # shutil.which should return a path so the linter proceeds to subprocess.run
    context.fixtures["_which_patch"] = patch(
        "peer.linters.shutil.which", return_value="/usr/bin/ruff"
    )
    context.fixtures["_run_patch"] = patch(
        "peer.linters.subprocess.run", return_value=_make_ruff_completed(payload)
    )
    context.fixtures["_which_patch"].start()
    context.fixtures["_run_patch"].start()


@given("a stub subprocess.run that returns ruff JSON output with one S101 finding")
def step_stub_ruff_s101(context) -> None:
    payload = '[{"code":"S101","filename":"src/foo.py","location":{"row":7,"column":1},"message":"use of assert detected"}]'
    context.fixtures["_which_patch"] = patch(
        "peer.linters.shutil.which", return_value="/usr/bin/ruff"
    )
    context.fixtures["_run_patch"] = patch(
        "peer.linters.subprocess.run", return_value=_make_ruff_completed(payload)
    )
    context.fixtures["_which_patch"].start()
    context.fixtures["_run_patch"].start()


@when('I call RuffLinter(severity_map={"S": "critical"}).lint on a repo')
def step_call_ruff_severity_override(context) -> None:
    linter = RuffLinter(severity_map={"S": "critical"})
    context.fixtures["findings"] = linter.lint(Path("/tmp/fake"), ["src/foo.py"])
    context.fixtures["_which_patch"].stop()
    context.fixtures["_run_patch"].stop()


# The default-RuffLinter scenario reuses the generic "I call RuffLinter().lint" step
# defined above (in the ruff-missing scenario), so we override it here with patches:


@when("I call RuffLinter().lint on a repo with one Python file from stub")
def step_call_ruff_stubbed(context) -> None:
    linter = RuffLinter()
    context.fixtures["findings"] = linter.lint(Path("/tmp/fake"), ["src/foo.py"])
    context.fixtures["_which_patch"].stop()
    context.fixtures["_run_patch"].stop()


# Behave matches scenario steps strictly. When ruff IS stubbed (Given a stub
# subprocess.run...) the "I call RuffLinter().lint on a repo with one Python file"
# step needs the stubs to be active. We restructured the missing-CLI step to its
# own "I call RuffLinter().lint on a repo with one Python file" — re-use the same
# step name here for the stubbed scenario by inserting tear-down on then-steps:


@then('the first finding has rule_id "{rule}"')
def step_first_rule_id(context, rule: str) -> None:
    assert context.fixtures["findings"][0].rule_id == rule


@then('the first finding has linter "{linter}"')
def step_first_linter(context, linter: str) -> None:
    assert context.fixtures["findings"][0].linter == linter


@then('the first finding has severity "{sev}"')
def step_first_severity(context, sev: str) -> None:
    got = context.fixtures["findings"][0].severity
    assert got == sev, f"expected {sev}, got {got}"


# ---------------------------------------------------------------------------
# Helper — log capture context
# ---------------------------------------------------------------------------


class _capture_log_ctx:
    def __init__(self, logger_name: str = "peer.linters") -> None:
        self.logger = logging.getLogger(logger_name)
        self.records: list[logging.LogRecord] = []
        self._handler: logging.Handler | None = None

    def __enter__(self):
        outer = self

        class _H(logging.Handler):
            def emit(self_inner, record):  # type: ignore[override]
                outer.records.append(record)

        self._handler = _H(level=logging.DEBUG)
        self.logger.addHandler(self._handler)
        self.logger.setLevel(logging.DEBUG)
        return self

    def __exit__(self, *args):
        if self._handler is not None:
            self.logger.removeHandler(self._handler)
