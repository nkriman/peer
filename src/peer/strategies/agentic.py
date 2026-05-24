"""AgenticReviewer — claude CLI with tool-use enabled.

The CLI has its own tool ecosystem (Read, Grep, Glob, Bash, Edit, ...).
Most peer reviewers DISABLE these via `--disallowedTools` for
determinism. AgenticReviewer flips the switch: it ENABLES a curated
default set and bounds the iteration via `--max-turns`. The model can
then decide when to grep the repo, read related files, etc., before
emitting its final review.

Same JSON-output contract as ClaudeCodeCLIReviewer (structured_output
preferred, prose fallback). Same ALLOW_LLM_CALLS gate. Same usage
accounting.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass, field

from .. import deps as _deps_module
from ..exceptions import LLMCallsDisabled
from ..prompts import DEFAULT_SYSTEM_PROMPT, format_prompt
from ..reviewers import _CLI_INSTRUCTIONS_SUFFIX, _extract_comments_payload
from ..types import CodebaseContext, Comment, Context

logger = logging.getLogger(__name__)

_DEFAULT_ALLOWED_TOOLS = ["Read", "Grep", "Glob"]


@dataclass
class AgenticReviewer:
    """Reviewer that delegates to `claude` CLI with its built-in tools enabled.

    Lets the model decide WHEN to grep / read files / check the repo
    before emitting its final review. Strategically different from the
    static-context reviewers — the per-PR latency varies with how many
    tool turns the model takes.
    """

    name: str = "agentic"
    model: str = "claude-code:sonnet"
    model_id: str = "sonnet"
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    allowed_tools: list[str] = field(default_factory=lambda: list(_DEFAULT_ALLOWED_TOOLS))
    max_turns: int = 15
    claude_bin: str = "claude"
    timeout_seconds: float = 1800.0

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

        tools_csv = ",".join(self.allowed_tools)
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
            f"--allowedTools={tools_csv}",
            "--max-turns",
            str(self.max_turns),
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
                "agentic claude exit %s; stderr=%s",
                proc.returncode,
                (proc.stderr or "")[:300],
            )

        try:
            envelope = json.loads(proc.stdout)
        except json.JSONDecodeError:
            logger.warning(
                "agentic claude returned non-JSON envelope; first 300 chars: %r",
                proc.stdout[:300],
            )
            envelope = {"result": "", "usage": {}}

        cli_usage = envelope.get("usage") or {}
        # Prefer structured_output; fall back to result-text parse.
        payload: dict | None = None
        so = envelope.get("structured_output")
        if isinstance(so, dict) and "comments" in so:
            payload = so
        if payload is None:
            payload = _extract_comments_payload(envelope.get("result") or "")

        comments: list[Comment] = []
        if payload is not None:
            for raw in payload.get("comments", []):
                try:
                    comments.append(Comment(**raw))
                except Exception as e:
                    logger.warning("dropping unparseable agentic comment: %s", e)

        usage = {
            "input_tokens": int(cli_usage.get("input_tokens", 0) or 0)
            + int(cli_usage.get("cache_read_input_tokens", 0) or 0)
            + int(cli_usage.get("cache_creation_input_tokens", 0) or 0),
            "output_tokens": int(cli_usage.get("output_tokens", 0) or 0),
            "model": self.model,
            "total_cost_usd": envelope.get("total_cost_usd", 0.0),
            "n_turns": envelope.get("num_turns"),
        }
        return comments, usage
