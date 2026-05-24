"""SDK-shaped shim that routes model calls through the `claude` CLI.

The `claude` binary authenticates via OAuth/keychain (no
ANTHROPIC_API_KEY needed), so calls through it don't bill against the
API key. `ClaudeCodeShimClient` mimics the small slice of the
`anthropic.Anthropic` interface that peer actually uses
(`.messages.create(...)`) and returns objects with the same attribute
shape — so drop-in replacement is a one-liner everywhere.

When the user's `messages.create` call passes `tools=[...]`, the shim
synthesizes a `tool_use` content block by parsing the response text via
the robust JSON extractor (same one used by ClaudeCodeCLIReviewer).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any

from .reviewers import _extract_comments_payload  # robust JSON parser

logger = logging.getLogger(__name__)

_PEER_USE_CLAUDE_CODE_ENV = "PEER_USE_CLAUDE_CODE"


def _truthy_env(name: str) -> bool:
    val = os.environ.get(name, "").strip().lower()
    return val in ("1", "true", "yes")


# ---------------------------------------------------------------------------
# SDK-shaped response models
# ---------------------------------------------------------------------------


@dataclass
class ClaudeCodeShimUsage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class ClaudeCodeShimContentBlock:
    """Covers both `type="text"` (text-only) and `type="tool_use"` (tool synth)."""

    type: str = "text"
    text: str | None = None
    name: str | None = None
    input: dict | None = None


@dataclass
class ClaudeCodeShimResponse:
    content: list[ClaudeCodeShimContentBlock] = field(default_factory=list)
    usage: ClaudeCodeShimUsage = field(default_factory=ClaudeCodeShimUsage)


# ---------------------------------------------------------------------------
# The shim
# ---------------------------------------------------------------------------


def _flatten_messages(messages: list[dict]) -> str:
    """Flatten Anthropic-shape messages into a single prompt string.

    Each message becomes `[ROLE] <content>` separated by blank lines. The
    CLI's --print mode only takes one prompt, so we serialize the
    conversation linearly. Users / assistants alternate.
    """
    parts: list[str] = []
    for m in messages:
        role = (m.get("role") or "user").upper()
        content = m.get("content") or ""
        if isinstance(content, list):
            # Anthropic permits content as a list of typed blocks; we
            # serialize text blocks and stringify others.
            text_parts: list[str] = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(str(block.get("text", "")))
                    else:
                        text_parts.append(json.dumps(block))
                else:
                    text_parts.append(str(block))
            content = "\n".join(text_parts)
        parts.append(f"[{role}]\n{content}")
    return "\n\n".join(parts)


class _MessagesNamespace:
    """Mirrors `anthropic.Anthropic().messages` — only `.create()` is used."""

    def __init__(self, client: ClaudeCodeShimClient) -> None:
        self._client = client

    def create(
        self,
        *,
        model: str,
        messages: list[dict],
        max_tokens: int = 8192,
        system: str | None = None,
        temperature: float | None = None,
        tools: list[dict] | None = None,
        tool_choice: dict | None = None,
        **_extra,
    ) -> ClaudeCodeShimResponse:
        return self._client._invoke(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            system=system,
            temperature=temperature,
            tools=tools,
            tool_choice=tool_choice,
        )


class ClaudeCodeShimClient:
    """Drop-in for `anthropic.Anthropic()` that calls `claude` CLI under the hood."""

    def __init__(
        self,
        claude_bin: str = "claude",
        timeout_seconds: float = 600.0,
        _runner: Any = None,
    ) -> None:
        self.claude_bin = claude_bin
        self.timeout_seconds = timeout_seconds
        # _runner is the function used to spawn subprocesses; defaults to
        # subprocess.run. Tests inject a recording stub instead of patching.
        self._runner = _runner if _runner is not None else subprocess.run
        self.messages = _MessagesNamespace(self)

    def _invoke(
        self,
        *,
        model: str,
        messages: list[dict],
        max_tokens: int,
        system: str | None,
        temperature: float | None,
        tools: list[dict] | None,
        tool_choice: dict | None,
    ) -> ClaudeCodeShimResponse:
        binary = shutil.which(self.claude_bin) or self.claude_bin
        user_prompt = _flatten_messages(messages)

        argv: list[str] = [
            binary,
            "--print",
            "--output-format",
            "json",
            "--model",
            model,
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
        ]
        if system:
            argv.extend(["--system-prompt", system])
        argv.append(user_prompt)
        # max_tokens / temperature: the CLI doesn't expose these as direct
        # flags today, so we omit them. Callers that need them must accept
        # the CLI's defaults.

        proc = self._runner(
            argv,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            check=False,
        )
        stdout = getattr(proc, "stdout", "") or ""
        rc = getattr(proc, "returncode", 0)
        if rc != 0:
            logger.warning("claude CLI exited %s; stderr=%s", rc, (proc.stderr or "")[:300])

        try:
            envelope = json.loads(stdout)
        except json.JSONDecodeError:
            logger.warning(
                "claude CLI returned non-JSON envelope; first 300 chars: %r", stdout[:300]
            )
            envelope = {"result": "", "usage": {}}

        result_text = envelope.get("result") or ""
        cli_usage = envelope.get("usage") or {}
        # Sum cached + uncached so cost-attribution sees a representative number.
        usage = ClaudeCodeShimUsage(
            input_tokens=int(cli_usage.get("input_tokens", 0) or 0)
            + int(cli_usage.get("cache_read_input_tokens", 0) or 0)
            + int(cli_usage.get("cache_creation_input_tokens", 0) or 0),
            output_tokens=int(cli_usage.get("output_tokens", 0) or 0),
        )

        # Tool-use synthesis: if tools were passed, try to parse the
        # response text as the tool's input schema.
        if tools and tool_choice:
            tool_name = tool_choice.get("name") if isinstance(tool_choice, dict) else None
            if tool_name is None and tools:
                first = tools[0]
                tool_name = first.get("name") if isinstance(first, dict) else None
            payload = _extract_comments_payload(result_text)
            if payload is not None:
                return ClaudeCodeShimResponse(
                    content=[
                        ClaudeCodeShimContentBlock(
                            type="tool_use",
                            name=tool_name,
                            input=payload,
                        )
                    ],
                    usage=usage,
                )
            logger.warning(
                "tool_use requested but could not extract payload from CLI result "
                "(first 200 chars: %r) — returning text-only response",
                result_text[:200],
            )

        return ClaudeCodeShimResponse(
            content=[ClaudeCodeShimContentBlock(type="text", text=result_text)],
            usage=usage,
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def make_client(*, use_claude_code: bool | None = None) -> Any:
    """Return either an anthropic.Anthropic() or a ClaudeCodeShimClient().

    Precedence: explicit `use_claude_code` arg wins; otherwise consult
    the PEER_USE_CLAUDE_CODE env var.
    """
    if use_claude_code is None:
        use_claude_code = _truthy_env(_PEER_USE_CLAUDE_CODE_ENV)
    if use_claude_code:
        return ClaudeCodeShimClient()
    import anthropic

    return anthropic.Anthropic()
