"""Linter Protocol + RuffLinter default implementation.

Per linter-context-v01: ship `RuffLinter` only as default (MypyLinter
needs per-project mypy.ini + venv-installed types, so it lives in
`examples/mypy_linter.py` rather than as a default shipment).

CodeRabbit-style: surface linter output in the codebase context so the
agent can cite rule_ids rather than re-discover style issues from scratch.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Protocol

from .types import LinterFinding, Severity

logger = logging.getLogger(__name__)


# Default ruff rule-prefix → peer severity. Override via RuffLinter(severity_map=...).
_DEFAULT_RUFF_SEVERITY_MAP: dict[str, Severity] = {
    # Style / formatting / pyflakes / etc.
    "E": "nit",
    "F": "minor",
    "W": "nit",
    "I": "nit",
    "N": "nit",
    "D": "nit",
    "Q": "nit",
    "C": "nit",
    "UP": "nit",
    "ANN": "nit",
    "RUF": "nit",
    "SIM": "nit",
    "TID": "nit",
    "TCH": "nit",
    # Bug / correctness families
    "B": "important",
    "BLE": "important",
    "PLE": "important",
    "PLW": "minor",
    "PIE": "minor",
    "PLR": "nit",
    # Security
    "S": "important",
}


class Linter(Protocol):
    """Anything with `name` + `lint(repo_path, target_files) -> list[LinterFinding]`."""

    name: str

    def lint(self, repo_path: Path, target_files: list[str]) -> list[LinterFinding]: ...


class RuffLinter:
    """Default Python linter — shells out to `ruff check --output-format=json`.

    Graceful degradation: if `ruff` is missing from `PATH`, logs a one-time
    WARNING and returns an empty list. Subsequent invocations return empty
    silently.
    """

    name = "ruff"

    def __init__(
        self,
        severity_map: dict[str, Severity] | None = None,
        timeout_sec: float = 30.0,
    ) -> None:
        # Merge user override on top of default — user keys take precedence.
        self.severity_map: dict[str, Severity] = {**_DEFAULT_RUFF_SEVERITY_MAP}
        if severity_map:
            self.severity_map.update(severity_map)
        self.timeout_sec = timeout_sec
        self._warned_missing = False

    # --- public API --------------------------------------------------------

    def lint(self, repo_path: Path, target_files: list[str]) -> list[LinterFinding]:
        if not target_files:
            return []
        if shutil.which("ruff") is None:
            if not self._warned_missing:
                logger.warning(
                    "peer.linters.ruff: ruff not found on PATH; install with 'pip install ruff'. "
                    "Skipping linter findings for this run."
                )
                self._warned_missing = True
            return []
        try:
            result = subprocess.run(
                [
                    "ruff",
                    "check",
                    "--output-format=json",
                    "--quiet",
                    "--no-cache",
                    *target_files,
                ],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=False,
                timeout=self.timeout_sec,
            )
        except (subprocess.TimeoutExpired, OSError) as e:
            logger.error("peer.linters.ruff: subprocess failed: %s", e)
            return []
        return self._parse_ruff_json(result.stdout)

    # --- internals ---------------------------------------------------------

    def _parse_ruff_json(self, raw: str) -> list[LinterFinding]:
        if not raw.strip():
            return []
        try:
            entries = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning("peer.linters.ruff: malformed JSON from ruff: %s", e)
            return []
        out: list[LinterFinding] = []
        for entry in entries:
            try:
                code = entry.get("code") or ""
                loc = entry.get("location") or {}
                row = loc.get("row") or 0
                col = loc.get("column")
                out.append(
                    LinterFinding(
                        linter=self.name,
                        path=entry.get("filename", ""),
                        line=int(row),
                        column=int(col) if col is not None else None,
                        rule_id=code,
                        severity=self._map_severity(code),
                        message=entry.get("message", ""),
                        fix_suggestion=(entry.get("fix") or {}).get("message"),
                    )
                )
            except Exception as e:
                logger.warning("peer.linters.ruff: skipping malformed entry: %s", e)
        return out

    def _map_severity(self, code: str) -> Severity:
        """Pick the most-specific prefix match from severity_map. Defaults to 'nit'."""
        best: tuple[int, Severity] = (0, "nit")
        for prefix, sev in self.severity_map.items():
            if code.startswith(prefix) and len(prefix) > best[0]:
                best = (len(prefix), sev)
        return best[1]


__all__ = ["Linter", "RuffLinter"]
