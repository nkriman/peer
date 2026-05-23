"""Shared Pydantic schemas for peer.

Slice 1 ships: Severity, Comment, ContextHunk, Context, Review.
CodebaseContext / Symbol / CallSite / TestFile land in Slice 2.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

Severity = Literal["critical", "important", "minor", "nit"]


class Comment(BaseModel):
    path: str
    line: Optional[int] = None
    severity: Severity
    body: str
    rationale: str
    references: Optional[list[str]] = None


class ContextHunk(BaseModel):
    path: str
    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    diff_text: str
    surrounding_code: Optional[str] = None


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
    reason: Optional[str] = None
    usage: dict = Field(default_factory=dict)
