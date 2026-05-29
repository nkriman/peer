"""Honest baselines for peer's eval framework.

If `BareClaudeCodeReviewer` (diff-only `claude --print`) scores as well as
peer's full pipeline on the same dataset, peer's codebase-context +
prompt-tuning machinery is providing no value and the framework has
failed its falsifiability test.

This module ships baselines as first-class Reviewer implementations so
they can be benchmarked through the same EvalRunner / CrossJudgeRunner
machinery as any peer recipe. Publishing benchmarks WITHOUT these
baselines is the AI-hype pattern peer exists to refute.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import time

from .reviewers import _extract_comments_payload
from .types import CodebaseContext, Comment, Context, Review

logger = logging.getLogger(__name__)


class BaselineInfraError(RuntimeError):
    """gh/claude subprocess failure that must NOT be silently treated as
    'reviewer returned zero comments'. EvalRunner records the raised
    exception as a failed sample, keeping the metric medians honest."""


_BARE_PROMPT_INSTRUCTIONS = """You are a code reviewer. Review the following PR diff for bugs, security concerns, design problems, and style/convention departures.

Return ONLY a JSON object with this shape and nothing else: {"comments": [{"path": str, "line": int|null, "severity": "critical"|"important"|"minor"|"nit", "body": str, "rationale": str}, ...]}.

Return an empty comments list if the PR has no issues. Do NOT wrap in markdown fences. Do NOT include any prose before or after.

PR DIFF:
"""


class BareClaudeCodeReviewer:
    """Diff-only baseline reviewer: `gh pr diff` → `claude --print` → JSON parse.

    NO codebase context. NO peer prompt. NO peer strategies. NO peer
    enrichers. Just the raw diff piped to Claude with a generic
    review-the-diff instruction. This is the "does peer add value
    over a 5-line script?" baseline.

    Routes through the `claude` CLI so it costs $0 under subscription
    auth, matching peer's CLI-everywhere stance.
    """

    name: str = "bare_claude_code"
    model: str = "claude-code:sonnet"

    def __init__(
        self,
        model_id: str = "sonnet",
        claude_bin: str = "claude",
        gh_bin: str = "gh",
        timeout_seconds: float = 600.0,
        gh_max_attempts: int = 3,
        gh_backoff_seconds: float = 2.0,
    ) -> None:
        self.model_id = model_id
        self.model = f"claude-code:{model_id}"
        self.claude_bin = claude_bin
        self.gh_bin = gh_bin
        self.timeout_seconds = timeout_seconds
        if gh_max_attempts < 1:
            raise ValueError(f"gh_max_attempts must be >= 1; got {gh_max_attempts}")
        self.gh_max_attempts = int(gh_max_attempts)
        self.gh_backoff_seconds = float(gh_backoff_seconds)

    def _fetch_diff_with_retry(self, pr_url: str) -> str:
        """Run `gh pr diff` with exponential backoff. Raises BaselineInfraError
        on persistent failure so EvalRunner records it as an errored sample
        instead of silently averaging in a zero-comment 'success'."""
        gh = shutil.which(self.gh_bin) or self.gh_bin
        last_stderr = ""
        last_rc = 0
        for attempt in range(1, self.gh_max_attempts + 1):
            proc = subprocess.run(
                [gh, "pr", "diff", pr_url],
                capture_output=True,
                text=True,
                check=False,
                timeout=120,
            )
            if proc.returncode == 0:
                return proc.stdout
            last_rc = proc.returncode
            last_stderr = (proc.stderr or "")[:300]
            logger.warning(
                "gh pr diff failed (attempt %d/%d) for %s: rc=%d %s",
                attempt,
                self.gh_max_attempts,
                pr_url,
                last_rc,
                last_stderr,
            )
            if attempt < self.gh_max_attempts:
                time.sleep(self.gh_backoff_seconds * (2 ** (attempt - 1)))
        raise BaselineInfraError(
            f"gh pr diff failed {self.gh_max_attempts}x for {pr_url}: rc={last_rc} stderr={last_stderr!r}"
        )

    def review(self, pr_url: str) -> Review:
        # 1. Fetch the diff via gh CLI (same path peer's context.gather uses).
        # Subprocess failures raise — see _fetch_diff_with_retry docstring.
        diff = self._fetch_diff_with_retry(pr_url)

        prompt = _BARE_PROMPT_INSTRUCTIONS + diff

        # 2. Send to `claude --print`. No system prompt, no tools, no
        # peer machinery. Just the prompt.
        claude = shutil.which(self.claude_bin) or self.claude_bin
        argv = [
            claude,
            "--print",
            "--output-format",
            "json",
            "--model",
            self.model_id,
            "--disable-slash-commands",
            "--disallowedTools=Bash,Edit,Write,Read,Grep,Glob,WebFetch,WebSearch",
            prompt,
        ]
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=False,
            timeout=self.timeout_seconds,
        )
        if proc.returncode != 0:
            raise BaselineInfraError(
                f"claude exit={proc.returncode} on {pr_url}; stderr={(proc.stderr or '')[:300]!r}"
            )

        try:
            envelope = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise BaselineInfraError(
                f"claude returned non-JSON envelope on {pr_url}; "
                f"first 300 chars: {proc.stdout[:300]!r}"
            ) from exc

        # Prefer structured_output (CLI --json-schema path) — empty here
        # since we didn't pass --json-schema; fall back to result-text parse.
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
                    logger.warning("dropping unparseable comment from bare baseline: %s", e)

        cli_usage = envelope.get("usage") or {}
        in_tok = (
            int(cli_usage.get("input_tokens", 0) or 0)
            + int(cli_usage.get("cache_read_input_tokens", 0) or 0)
            + int(cli_usage.get("cache_creation_input_tokens", 0) or 0)
        )
        out_tok = int(cli_usage.get("output_tokens", 0) or 0)
        # Zero input tokens is impossible — the prompt alone is hundreds of
        # tokens. This indicates claude never actually executed the call
        # (auth blip, rate limit, transient CLI failure). Refuse to silently
        # report it as a clean "no issues" result.
        if in_tok == 0 and out_tok == 0:
            raise BaselineInfraError(
                f"claude returned zero usage on {pr_url}: input_tokens=0 output_tokens=0 "
                f"(call did not execute); envelope keys={list(envelope.keys())}"
            )
        usage = {
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "model": self.model,
            "total_cost_usd": envelope.get("total_cost_usd", 0.0),
        }

        if not comments:
            return Review(comments=[], reason="bare baseline: no issues found", usage=usage)
        return Review(comments=comments, usage=usage)

    # Reviewer Protocol compatibility: peer's eval-runner calls `.review(pr_url)`
    # directly; we don't need the Context/CodebaseContext-shaped version.
    def review_with_context(
        self,
        context: Context,
        codebase_context: CodebaseContext | None = None,
        *,
        extra_user_message: str | None = None,
        run_context: object | None = None,
    ) -> tuple[list[Comment], dict]:
        review = self.review(context.pr_url)
        return list(review.comments), review.usage or {}
