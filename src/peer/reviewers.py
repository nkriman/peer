"""Pluggable Reviewer backends. Slice 1 ships ClaudeReviewer only.

OpenAIReviewer lands in Slice 3 alongside the eval scaffolding.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
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
                        "end_line": {
                            "type": ["integer", "null"],
                            "description": (
                                "Optional upper bound for a multi-line comment "
                                "range. When set, must satisfy end_line >= line "
                                "and stay within the same hunk."
                            ),
                        },
                        "severity": {
                            "type": "string",
                            "enum": ["critical", "important", "minor", "nit"],
                        },
                        "body": {"type": "string"},
                        "rationale": {"type": "string"},
                        "issue_header": {
                            "type": ["string", "null"],
                            "description": (
                                "Short 1-3 word categorical label (e.g. "
                                "'Possible Bug', 'Performance Concern', "
                                "'Test Coverage'). Surfaced in CLI + reports."
                            ),
                        },
                        "suggestion": {
                            "type": ["string", "null"],
                            "description": (
                                "Optional replacement text for the lines being "
                                "commented on. Rendered as a GitHub "
                                "```suggestion``` block. Include ONLY when the "
                                "fix is small (<=5 lines), concrete, and "
                                "high-confidence — never for 'consider "
                                "refactoring' style nudges."
                            ),
                        },
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


# ---------------------------------------------------------------------------
# ClaudeCodeCLIReviewer — drives peer via the `claude` CLI
# ---------------------------------------------------------------------------

# JSON schema the model is asked to conform to. Mirror of _COMMENT_TOOL's
# input_schema minus the wrapping tool fields. Passed to the CLI via
# --json-schema; the CLI treats it as a strong hint, not a hard constraint
# (the model may still wrap in markdown), so we have a robust fallback
# parser below.
_CLI_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "comments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "line": {"type": ["integer", "null"]},
                    "end_line": {"type": ["integer", "null"]},
                    "severity": {
                        "type": "string",
                        "enum": ["critical", "important", "minor", "nit"],
                    },
                    "body": {"type": "string"},
                    "rationale": {"type": "string"},
                    "issue_header": {"type": ["string", "null"]},
                    "suggestion": {"type": ["string", "null"]},
                },
                "required": ["path", "severity", "body", "rationale"],
            },
        },
    },
    "required": ["comments"],
}

_CLI_INSTRUCTIONS_SUFFIX = (
    "\n\nReturn ONLY a JSON object with this shape and nothing else: "
    '{"comments": [{"path": str, "line": int|null, "severity": '
    '"critical"|"important"|"minor"|"nit", "body": str, "rationale": str, '
    '"issue_header": str|null, "suggestion": str|null}, ...]}. '
    "Return an empty comments list if the PR has no issues. "
    "Do NOT wrap in markdown fences. Do NOT include any prose before or after."
)


def _extract_comments_payload(text: str) -> dict | None:
    """Best-effort recovery of a `{"comments": [...]}` object from raw model
    output. Tries (in order):
      1. Parse the whole string as JSON.
      2. Find the first fenced ```json ... ``` block.
      3. Find the first balanced-brace `{...}` span and try parsing it.
    Returns None if all attempts fail.
    """
    s = text.strip()
    if not s:
        return None
    # 1. Direct parse.
    try:
        obj = json.loads(s)
        if isinstance(obj, dict) and "comments" in obj:
            return obj
    except json.JSONDecodeError:
        pass
    # 2. ```json ... ``` block.
    m = re.search(r"```(?:json)?\s*\n(.+?)\n```", s, re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group(1))
            if isinstance(obj, dict) and "comments" in obj:
                return obj
        except json.JSONDecodeError:
            pass
    # 3. First balanced {...} span. Stop-on-depth-zero scan; tolerates
    #    nested braces inside string values.
    start = s.find("{")
    while start != -1:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(s)):
            ch = s[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = s[start : i + 1]
                    try:
                        obj = json.loads(candidate)
                        if isinstance(obj, dict) and "comments" in obj:
                            return obj
                    except json.JSONDecodeError:
                        pass
                    break
        start = s.find("{", start + 1)
    return None


@dataclass
class ClaudeCodeCLIReviewer:
    """Reviewer that shells out to the `claude` CLI instead of the SDK.

    Uses Claude Code's OAuth/keychain auth, so it works without an
    ANTHROPIC_API_KEY in the environment. Slower per call than the SDK
    (CLI startup + cache_creation), but doesn't need a separate key.

    Tools/skills/CLAUDE.md auto-discovery are suppressed so the reviewer
    runs deterministically — only `--system-prompt` content matters.
    """

    name: str = "claude_code_cli"
    model: str = "claude-code:sonnet"
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    model_id: str = "sonnet"
    claude_bin: str = "claude"
    timeout_seconds: float = 600.0

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

        binary = shutil.which(self.claude_bin) or self.claude_bin
        user_msg = format_prompt(context, codebase_context)
        if extra_user_message:
            user_msg = user_msg + "\n\n" + extra_user_message
        user_msg = user_msg + _CLI_INSTRUCTIONS_SUFFIX

        argv = [
            binary,
            "--print",
            "--output-format",
            "json",
            "--model",
            self.model_id,
            "--system-prompt",
            self.system_prompt,
            "--disable-slash-commands",
            "--disallowedTools",
            "Bash",
            "Edit",
            "Write",
            "Read",
            "Grep",
            "Glob",
            "WebFetch",
            "WebSearch",
            "--json-schema",
            json.dumps(_CLI_OUTPUT_SCHEMA),
            user_msg,
        ]

        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            check=False,
        )
        if proc.returncode != 0:
            logger.warning(
                "claude CLI exited %s; stderr=%s",
                proc.returncode,
                proc.stderr[:500] if proc.stderr else "(empty)",
            )

        try:
            envelope = json.loads(proc.stdout)
        except json.JSONDecodeError:
            logger.warning(
                "claude CLI returned non-JSON envelope; first 500 chars: %r",
                proc.stdout[:500],
            )
            envelope = {"result": "", "total_cost_usd": 0.0, "usage": {}}

        result_text = envelope.get("result") or ""
        cli_usage = envelope.get("usage") or {}
        comments: list[Comment] = []
        payload = _extract_comments_payload(result_text)
        if payload is not None:
            for raw in payload.get("comments", []):
                try:
                    comments.append(Comment(**raw))
                except Exception as e:
                    logger.warning("dropping unparseable comment from CLI: %s", e)
        usage = {
            "input_tokens": cli_usage.get("input_tokens", 0),
            "output_tokens": cli_usage.get("output_tokens", 0),
            "model": self.model,
            "total_cost_usd": envelope.get("total_cost_usd", 0.0),
            "duration_ms": envelope.get("duration_ms"),
        }
        return comments, usage


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
