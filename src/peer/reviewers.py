"""Pluggable Reviewer backends. Slice 1 ships ClaudeReviewer only.

OpenAIReviewer lands in Slice 3 alongside the eval scaffolding.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import anthropic

from . import deps as _deps_module
from .exceptions import LLMCallsDisabled, ReviewerRateLimited
from .prompts import DEFAULT_SYSTEM_PROMPT, format_prompt
from .types import CodebaseContext, Comment, Context, Severity

logger = logging.getLogger(__name__)

_COMMENT_TOOL = {
    "name": "post_review_comments",
    "description": (
        "Post the list of inline review comments for this PR. "
        "Pass an empty list if the PR has no issues worth flagging."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "comments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "line": {"type": ["integer", "null"]},
                        "severity": {
                            "type": "string",
                            "enum": ["critical", "important", "minor", "nit"],
                        },
                        "body": {"type": "string"},
                        "rationale": {"type": "string"},
                    },
                    "required": ["path", "severity", "body", "rationale"],
                },
            },
        },
        "required": ["comments"],
    },
}


class Reviewer(Protocol):
    def review(
        self,
        context: Context,
        codebase_context: CodebaseContext | None = None,
        *,
        extra_user_message: str | None = None,
        run_context: object | None = None,
    ) -> tuple[list[Comment], dict]: ...


def _is_rate_limit_error(exc: Exception) -> bool:
    """True if `exc` looks like an HTTP-429 rate-limit error.

    Detect both anthropic.RateLimitError and any exception exposing
    `status_code == 429` (covers HTTP libraries the SDK might wrap).
    """
    cls = getattr(anthropic, "RateLimitError", None)
    if cls is not None and isinstance(exc, cls):
        return True
    return getattr(exc, "status_code", None) == 429


class ClaudeReviewer:
    def __init__(
        self,
        model: str,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        *,
        model_id: str | None = None,
        rate_limit_max_retries: int = 4,
        rate_limit_base_backoff: float = 1.0,
        _sleep: object | None = None,
    ) -> None:
        # `model` is the canonical provider:model_id form (e.g.
        # "anthropic:claude-sonnet-4-6"). `model_id` is the bare model
        # passed to the SDK (e.g. "claude-sonnet-4-6"). Agent strips the
        # provider prefix and passes both.
        self.model = model
        self._model_id = model_id or model.split(":", 1)[-1]
        self.system_prompt = system_prompt
        self.client = anthropic.Anthropic()
        # 429 backoff: total attempts = rate_limit_max_retries + 1.
        self.rate_limit_max_retries = rate_limit_max_retries
        self.rate_limit_base_backoff = rate_limit_base_backoff
        # Sleep hook is overridable so BDD scenarios can run without real waits.
        self._sleep = _sleep if _sleep is not None else time.sleep

    def review(
        self,
        context: Context,
        codebase_context: CodebaseContext | None = None,
        *,
        extra_user_message: str | None = None,
        run_context: object | None = None,
    ) -> tuple[list[Comment], dict]:
        if not _deps_module.ALLOW_LLM_CALLS:
            raise LLMCallsDisabled()
        user_msg = format_prompt(context, codebase_context)
        if extra_user_message:
            user_msg = user_msg + "\n\n" + extra_user_message

        resp = self._call_with_backoff(user_msg)

        comments: list[Comment] = []
        for block in resp.content:
            if getattr(block, "type", None) != "tool_use":
                continue
            if getattr(block, "name", None) != "post_review_comments":
                continue
            for raw in block.input.get("comments", []):
                comments.append(Comment(**raw))
        usage = {
            "input_tokens": resp.usage.input_tokens,
            "output_tokens": resp.usage.output_tokens,
            "model": self.model,
        }
        return comments, usage

    def _call_with_backoff(self, user_msg: str) -> Any:
        """Call the SDK with exponential backoff on HTTP 429.

        Total attempts = self.rate_limit_max_retries + 1. Sleep schedule:
        base * 2**attempt (1, 2, 4, ... base ticks). Non-429 exceptions
        propagate immediately. ReviewerRateLimited raised on exhaustion.
        """
        last_exc: Exception | None = None
        attempts = self.rate_limit_max_retries + 1
        for attempt in range(attempts):
            try:
                # Tool schema + tool_choice shapes are dicts at runtime;
                # Anthropic's overload typings don't accept the dict form
                # directly, so we silence the call-site mypy noise rather
                # than wrestle the SDK.
                return self.client.messages.create(  # type: ignore[call-overload]
                    model=self._model_id,
                    max_tokens=8192,
                    system=self.system_prompt,
                    tools=[_COMMENT_TOOL],
                    tool_choice={"type": "tool", "name": "post_review_comments"},
                    messages=[{"role": "user", "content": user_msg}],
                )
            except Exception as e:
                if not _is_rate_limit_error(e):
                    raise
                last_exc = e
                if attempt == attempts - 1:
                    break
                backoff = self.rate_limit_base_backoff * (2**attempt)
                logger.warning(
                    "Rate-limited by %s (attempt %d/%d); sleeping %.2fs",
                    self.model,
                    attempt + 1,
                    attempts,
                    backoff,
                )
                self._sleep(backoff)  # type: ignore[operator]
        raise ReviewerRateLimited(self.model, attempts, last_exc)


@dataclass
class TestReviewer:
    """Deterministic Reviewer that never invokes an LLM.

    Two modes:

    - **Fixed list:** pass `comments=[Comment(...), Comment(...)]` at
      construction. `review()` returns that exact list.
    - **Synthesized:** pass `n_comments=N, severity=S` (default `n_comments=1,
      severity="minor"`). `review()` synthesizes N Comments anchored to the
      first N hunks of the supplied Context.

    Always returns `usage={"input_tokens": 0, "output_tokens": 0, "model":
    "test"}`. Ignores `peer.deps.ALLOW_LLM_CALLS` — its job is to be safe
    in tests where the flag is False.
    """

    name: str = "test"
    model: str = "test:stub"
    comments: list[Comment] | None = None
    n_comments: int = 1
    severity: Severity = "minor"
    extra_usage: dict = field(default_factory=dict)

    def review(
        self,
        context: Context,
        codebase_context: CodebaseContext | None = None,
        *,
        extra_user_message: str | None = None,
        run_context: object | None = None,
    ) -> tuple[list[Comment], dict]:
        # extra_user_message is accepted for Reviewer-Protocol uniformity but
        # has no effect on synthesized output. Tests that want to assert the
        # retry loop wired it through use a custom scripted Reviewer instead.
        if self.comments is not None:
            out = [c.model_copy() for c in self.comments]
        else:
            out = []
            for h in context.hunks[: self.n_comments]:
                out.append(
                    Comment(
                        path=h.path,
                        line=h.new_start,
                        severity=self.severity,
                        body="synthetic test comment",
                        rationale="synthetic test rationale",
                    )
                )
        usage = {"input_tokens": 0, "output_tokens": 0, "model": "test"}
        usage.update(self.extra_usage)
        return out, usage
