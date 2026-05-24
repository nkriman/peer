"""Shared Pydantic schemas for peer.

Slice 1: Severity, Comment, ContextHunk, Context, Review.
Slice 2: Symbol, CallSite, TestFile, CodebaseContext.
"""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

SymbolKind = Literal["function", "method", "class"]

Severity = Literal["critical", "important", "minor", "nit"]


class Comment(BaseModel):
    path: str
    line: int | None = None
    end_line: int | None = None  # patch-suggestions-v01: line range upper bound
    severity: Severity
    body: str
    rationale: str
    references: list[str] | None = None
    suggestion: str | None = None  # patch-suggestions-v01: optional replacement block
    issue_header: str | None = None  # patch-suggestions-v01: short categorical label

    @model_validator(mode="after")
    def _validate_end_line(self) -> "Comment":
        if self.end_line is not None and self.line is not None and self.end_line < self.line:
            raise ValueError(f"end_line ({self.end_line}) must be >= line ({self.line})")
        return self


class ContextHunk(BaseModel):
    path: str
    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    diff_text: str
    surrounding_code: str | None = None


class Context(BaseModel):
    pr_url: str
    owner: str
    repo: str
    number: int
    title: str
    body: str
    head_sha: str
    hunks: list[ContextHunk] = Field(default_factory=list)
    prior_comments: list[str] = Field(default_factory=list)
    token_estimate: int = 0


class Review(BaseModel):
    comments: list[Comment] = Field(default_factory=list)
    reason: str | None = None
    usage: dict = Field(default_factory=dict)


class Symbol(BaseModel):
    name: str
    path: str
    kind: SymbolKind
    signature: str
    enclosing_qualifier: str | None = None
    start_line: int
    end_line: int
    deleted: bool = False


class CallSite(BaseModel):
    symbol_name: str
    path: str
    line: int
    snippet: str


class TestFile(BaseModel):
    path: str
    source_file: str
    content: str
    truncated: bool = False


class LinterFinding(BaseModel):
    """One finding from a Linter (ruff, mypy, semgrep, ...).

    Carries enough information for the agent to cite the rule_id + message
    and decide whether to surface it as-is or supplement with reasoning.
    """

    linter: str
    path: str
    line: int
    column: int | None = None
    rule_id: str
    severity: Severity
    message: str
    fix_suggestion: str | None = None


class CodebaseContext(BaseModel):
    modified_symbols: list[Symbol] = Field(default_factory=list)
    call_sites: list[CallSite] = Field(default_factory=list)
    related_tests: list[TestFile] = Field(default_factory=list)
    untested_files: list[str] = Field(default_factory=list)
    unsupported_files: list[str] = Field(default_factory=list)
    parse_failures: list[str] = Field(default_factory=list)
    linter_findings: list[LinterFinding] = Field(default_factory=list)
    # blame-enricher-v01: empty string = git history not gathered (default
    # for back-compat). Non-empty = markdown ready to drop into the prompt's
    # `## GIT HISTORY` section.
    git_history: str = ""
    token_estimate: int = 0
    truncations: dict[str, int] = Field(default_factory=dict)
