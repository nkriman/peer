"""`.peer.yaml` config: schema + loader + per-path resolver + severity bounds.

Per peer-config-v01 design decisions:
- First-matching-glob wins for CONVENTIONS (specific-first ordering).
- MOST-RESTRICTIVE intersection wins for SEVERITY bounds (per adversarial
  review item 2.4 — first-match would have surprising behavior on path
  combinations like tests/test_security.py matching both tests/** and **).
- ignore.glob / ignore.regex / ignore.generated_code filter files BEFORE
  codebase-context extraction (saves tokens + avoids agent attention on
  generated code).
"""

from __future__ import annotations

import fnmatch
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .exceptions import PeerError
from .types import Comment, Context, Severity

logger = logging.getLogger(__name__)


# Severity ordinal: critical=0 (most severe) → nit=3 (least severe).
_SEVERITY_ORDER: dict[Severity, int] = {
    "critical": 0,
    "important": 1,
    "minor": 2,
    "nit": 3,
}


class PeerConfigInvalid(PeerError):
    """`.peer.yaml` failed to parse or validate."""


class AgentConfigSection(BaseModel):
    """Top-level `agent:` section of .peer.yaml."""

    model_config = ConfigDict(extra="forbid")

    extra_instructions: str | None = None


class IgnoreSection(BaseModel):
    """Top-level `ignore:` section: paths/patterns to skip before review."""

    model_config = ConfigDict(extra="forbid")

    glob: list[str] = Field(default_factory=list)
    regex: list[str] = Field(default_factory=list)
    generated_code: list[str] | None = None  # None = use defaults


class Rule(BaseModel):
    """One per-path rule in `.peer.yaml`'s `rules:` list."""

    model_config = ConfigDict(extra="forbid")

    paths: list[str]
    conventions_file: str | None = None
    conventions_text: str | None = None  # inline; mutually exclusive with conventions_file
    severity_floor: Severity | None = None
    severity_cap: Severity | None = None

    @field_validator("paths")
    @classmethod
    def _paths_nonempty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("rules[*].paths must be non-empty")
        return v


@dataclass
class ResolvedRule:
    """Result of `PeerConfig.for_path(path)` — the merged effect at a path."""

    conventions_texts: list[str] = field(default_factory=list)
    severity_floor: Severity | None = None
    severity_cap: Severity | None = None

    @classmethod
    def empty(cls) -> ResolvedRule:
        return cls()


# Default generated-code patterns vendored from PR-Agent's generated_code_ignore.toml.
_DEFAULT_GENERATED_CODE_PATTERNS: tuple[str, ...] = (
    # protobuf
    "**/*.pb.go",
    "**/*.pb.cc",
    "**/*_pb2.py",
    "**/*.pb.swift",
    "**/*.pb.rb",
    "**/*.pb.php",
    "**/*.pb.h",
    # OpenAPI / Swagger
    "**/__generated__/**",
    "**/openapi_client/**",
    "**/openapi_server/**",
    "**/swagger.json",
    "**/swagger.yaml",
    # GraphQL codegen
    "**/*.graphql.ts",
    "**/*.generated.ts",
    "**/*.graphql.js",
    # gRPC
    "**/*_grpc.py",
    "**/*Grpc.java",
    "**/*Grpc.cs",
    "**/*_grpc.ts",
    "**/*_grpc.js",
    # Go generators
    "**/*_gen.go",
    "**/*.gen.go",
)


class PeerConfig(BaseModel):
    """Top-level schema for `.peer.yaml`."""

    model_config = ConfigDict(extra="forbid")

    version: int = 1
    agent: AgentConfigSection = Field(default_factory=AgentConfigSection)
    rules: list[Rule] = Field(default_factory=list)
    ignore: IgnoreSection = Field(default_factory=IgnoreSection)

    # --- per-path resolution ----------------------------------------------

    def for_path(self, file_path: str) -> ResolvedRule:
        """Return the merged ResolvedRule for `file_path`.

        - conventions_texts: collected from ALL matching rules in rule order
          (so users can stack a global doc with a path-specific doc).
        - severity_floor: HIGHEST (most-restrictive) across matching rules.
        - severity_cap: LOWEST (most-restrictive) across matching rules.
        """
        out = ResolvedRule()
        for rule in self.rules:
            if not _any_glob_match(file_path, rule.paths):
                continue
            text = _resolve_conventions_text(rule)
            if text is not None:
                out.conventions_texts.append(text)
            if rule.severity_floor is not None and (
                out.severity_floor is None
                or _SEVERITY_ORDER[rule.severity_floor] < _SEVERITY_ORDER[out.severity_floor]
            ):
                out.severity_floor = rule.severity_floor
            if rule.severity_cap is not None and (
                out.severity_cap is None
                or _SEVERITY_ORDER[rule.severity_cap] > _SEVERITY_ORDER[out.severity_cap]
            ):
                out.severity_cap = rule.severity_cap
        return out

    # --- ignore filtering --------------------------------------------------

    def should_ignore(self, path: str) -> bool:
        """True if `path` matches any ignore pattern."""
        if _any_glob_match(path, self.ignore.glob):
            return True
        for rgx in self.ignore.regex:
            try:
                if re.search(rgx, path):
                    return True
            except re.error:
                logger.warning("Invalid regex in ignore.regex: %r", rgx)
        gen = (
            tuple(self.ignore.generated_code)
            if self.ignore.generated_code is not None
            else _DEFAULT_GENERATED_CODE_PATTERNS
        )
        return _any_glob_match(path, gen)

    def filter_context(self, ctx: Context) -> Context:
        """Return a copy of ctx with ignored hunks removed."""
        kept = [h for h in ctx.hunks if not self.should_ignore(h.path)]
        if len(kept) == len(ctx.hunks):
            return ctx
        return ctx.model_copy(update={"hunks": kept})


# --- helpers ---------------------------------------------------------------


def _any_glob_match(path: str, patterns: list[str] | tuple[str, ...]) -> bool:
    """fnmatch with `**` support (Python's fnmatch handles `**` if path is
    rendered as POSIX). Both inputs are normalized to forward-slash form."""
    norm_path = path.replace("\\", "/")
    for pat in patterns:
        norm_pat = pat.replace("\\", "/")
        if fnmatch.fnmatchcase(norm_path, norm_pat):
            return True
        # Manual support for `**` in patterns where fnmatch on its own treats
        # `**` like `*` (no cross-segment match).
        if "**" in norm_pat and _double_star_match(norm_path, norm_pat):
            return True
    return False


def _double_star_match(path: str, pattern: str) -> bool:
    """Match `**` as "zero or more path segments"."""
    # Convert glob to regex: `**` → `.*`, `*` → `[^/]*`, `?` → `[^/]`,
    # other chars escaped.
    rgx_parts: list[str] = []
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "*":
            if i + 1 < len(pattern) and pattern[i + 1] == "*":
                rgx_parts.append(".*")
                i += 2
                # Eat the trailing slash after `**/` so `src/**/foo` matches `src/foo`.
                if i < len(pattern) and pattern[i] == "/":
                    i += 1
            else:
                rgx_parts.append("[^/]*")
                i += 1
        elif ch == "?":
            rgx_parts.append("[^/]")
            i += 1
        elif ch in r".\+()[]{}|^$":
            rgx_parts.append("\\" + ch)
            i += 1
        else:
            rgx_parts.append(ch)
            i += 1
    return re.fullmatch("".join(rgx_parts), path) is not None


def _resolve_conventions_text(rule: Rule) -> str | None:
    """Return rule's conventions content (from `_text` or by reading
    `_file`). Returns None if neither set."""
    if rule.conventions_text is not None:
        return rule.conventions_text
    if rule.conventions_file is not None:
        p = Path(rule.conventions_file)
        if not p.exists():
            logger.warning("conventions_file not found: %s", rule.conventions_file)
            return None
        return p.read_text()
    return None


# --- severity bounds ------------------------------------------------------


def apply_severity_bounds(comment: Comment, rule: ResolvedRule) -> Comment:
    """Apply rule.severity_floor / severity_cap to a single Comment. Returns
    the (possibly updated) comment. INFO-logs when severity changes."""
    new_sev: Severity = comment.severity
    if rule.severity_floor is not None and (
        _SEVERITY_ORDER[new_sev] > _SEVERITY_ORDER[rule.severity_floor]
    ):
        # current less severe than floor — promote
        new_sev = rule.severity_floor
        logger.info(
            "severity floor: %s:%s %s -> %s",
            comment.path,
            comment.line,
            comment.severity,
            new_sev,
        )
    if rule.severity_cap is not None and (
        _SEVERITY_ORDER[new_sev] < _SEVERITY_ORDER[rule.severity_cap]
    ):
        # current more severe than cap — demote
        new_sev = rule.severity_cap
        logger.info(
            "severity cap: %s:%s %s -> %s",
            comment.path,
            comment.line,
            comment.severity,
            new_sev,
        )
    if new_sev == comment.severity:
        return comment
    return comment.model_copy(update={"severity": new_sev})


# --- loader ---------------------------------------------------------------


def load_config(root: Path) -> PeerConfig:
    """Look for `.peer.yaml` in `root`. Return parsed config or empty
    PeerConfig() if absent. Raises PeerConfigInvalid on YAML / schema errors."""
    path = root / ".peer.yaml"
    if not path.exists():
        return PeerConfig()
    return load_config_from(path)


def load_config_from(path: Path) -> PeerConfig:
    """Load a specific `.peer.yaml` file."""
    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        raise PeerConfigInvalid(f"YAML parse error in {path}: {e}") from e
    if raw is None:
        return PeerConfig()
    try:
        cfg = PeerConfig.model_validate(raw)
    except Exception as e:
        raise PeerConfigInvalid(f"schema validation failed for {path}: {e}") from e
    logger.info("loaded peer config from %s", path)
    return cfg


__all__ = [
    "AgentConfigSection",
    "IgnoreSection",
    "PeerConfig",
    "PeerConfigInvalid",
    "ResolvedRule",
    "Rule",
    "apply_severity_bounds",
    "load_config",
    "load_config_from",
]


# Suppress unused-import warning for re-exports.
_ = Literal
