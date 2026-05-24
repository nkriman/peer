"""Top-level PR review agent: dispatches to a Reviewer based on the model id,
gathers context, validates LLM output against the diff, and returns a Review.

`peer-deps-v01` adds:
- provider:model string parsing ("anthropic:claude-sonnet-4-6") with legacy
  bare-name back-compat (emits DeprecationWarning).
- Agent.override(*, model=None, reviewer=None, deps=None) context manager
  that swaps fields for the with-block and restores on exit (re-entrant).
- Agent.run(pr_url, deps=None) — the new canonical entry. Agent.review(pr_url)
  remains as a thin shim for back-compat.
"""

from __future__ import annotations

import logging
import time
import warnings
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .codebase_context import gather_codebase_context
from .context import gather
from .exceptions import CodebaseContextTooLarge, UnknownModelError
from .prompts import DEFAULT_SYSTEM_PROMPT, format_prompt
from .reviewers import ClaudeCodeCLIReviewer, ClaudeReviewer, Reviewer
from .runtime import RunContext, _emit_captured_message
from .types import CodebaseContext, Comment, Context, Review

if TYPE_CHECKING:
    from .deps import PeerDeps

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Model string parsing — provider:model_id canonical form
# ---------------------------------------------------------------------------


_PROVIDER_BY_BARE_PREFIX: list[tuple[tuple[str, ...], str]] = [
    (("claude",), "anthropic"),
    (("gpt", "o1", "o2", "o3", "o4", "o5", "o6", "o7", "o8", "o9"), "openai"),
]


def _parse_model_id(model: str) -> tuple[str, str]:
    """Return (provider, model_id) for `model`.

    Canonical form: "anthropic:claude-sonnet-4-6" → ("anthropic", "claude-sonnet-4-6").
    Legacy bare form: "claude-sonnet-4-6" → ("anthropic", "claude-sonnet-4-6")
    AND emit DeprecationWarning pointing at the canonical form.

    Raises UnknownModelError if the provider is unrecognized (canonical form)
    or no legacy inference matches (bare form).
    """
    if ":" in model:
        provider, model_id = model.split(":", 1)
        provider = provider.strip().lower()
        model_id = model_id.strip()
        if provider not in ("anthropic", "openai", "claude-code"):
            raise UnknownModelError(
                f"Unknown provider {provider!r} in model {model!r}. "
                f"Supported providers: anthropic, openai, claude-code."
            )
        return provider, model_id
    # Legacy bare name — infer provider + warn
    lower = model.lower()
    for prefixes, provider in _PROVIDER_BY_BARE_PREFIX:
        if any(lower.startswith(p) for p in prefixes):
            canonical = f"{provider}:{model}"
            warnings.warn(
                f"Bare model name {model!r} is deprecated. Use {canonical!r} "
                f"(provider:model_id format). Legacy inference will be removed "
                f"in v1.0.",
                DeprecationWarning,
                stacklevel=3,
            )
            return provider, model
    raise UnknownModelError(
        f"Unknown model {model!r}. Use canonical format like "
        f"'anthropic:claude-sonnet-4-6' or 'openai:gpt-4o'."
    )


def _select_reviewer(
    provider: str, model_id: str, canonical_model: str, system_prompt: str
) -> Reviewer:
    if provider == "anthropic":
        return ClaudeReviewer(model=canonical_model, system_prompt=system_prompt, model_id=model_id)
    if provider == "claude-code":
        return ClaudeCodeCLIReviewer(
            model=canonical_model,
            system_prompt=system_prompt,
            model_id=model_id,
        )
    if provider == "openai":
        raise UnknownModelError(
            f"OpenAI backend not yet implemented (agent-v01 task 3.3). model={canonical_model}"
        )
    raise UnknownModelError(f"Unsupported provider: {provider!r}.")


def _valid_lines_per_path(ctx: Context) -> dict[str, set[int]]:
    out: dict[str, set[int]] = {}
    for h in ctx.hunks:
        bucket = out.setdefault(h.path, set())
        for ln in range(h.new_start, h.new_start + max(h.new_lines, 0)):
            bucket.add(ln)
    return out


def _validate_comments_with_reasons(
    comments: list[Comment], ctx: Context
) -> tuple[list[Comment], list[tuple[Comment, str]]]:
    """Return (kept, dropped_with_reason)."""
    valid_lines = _valid_lines_per_path(ctx)
    kept: list[Comment] = []
    dropped: list[tuple[Comment, str]] = []
    for c in comments:
        if c.path not in valid_lines:
            dropped.append(
                (
                    c,
                    f"path {c.path!r} is not modified by this PR — only "
                    f"comment on modified files: {sorted(valid_lines)}",
                )
            )
            continue
        if c.line is not None and c.line not in valid_lines[c.path]:
            valid_for_path = sorted(valid_lines[c.path])
            dropped.append(
                (
                    c,
                    f"line {c.line} on {c.path!r} is outside the modified "
                    f"hunks — valid lines for this file: {valid_for_path}",
                )
            )
            continue
        kept.append(c)
    return kept, dropped


def _validate_comments(comments: list[Comment], ctx: Context) -> list[Comment]:
    kept, dropped = _validate_comments_with_reasons(comments, ctx)
    for c, reason in dropped:
        logger.warning("Dropping comment %s:%s (sev=%s) — %s", c.path, c.line, c.severity, reason)
    return kept


def _build_retry_message(dropped: list[tuple[Comment, str]]) -> str:
    """Build the follow-up user message that's appended on a retry round.

    Cites each dropped comment by index + reason so the model can correct
    its grounding.
    """
    lines = [
        "Some of your previous comments were dropped because they did not",
        "ground to a modified line of this PR. Please re-issue them with",
        "corrected `path` + `line` values (or drop them if they cannot be",
        "anchored). Do not repeat comments that were accepted.",
        "",
        "Dropped comments:",
    ]
    for i, (c, reason) in enumerate(dropped, start=1):
        lines.append(f"{i}. {c.path}:{c.line} (sev={c.severity}) — {reason}")
        lines.append(f"   body: {c.body[:200]}")
    return "\n".join(lines)


class Agent:
    def __init__(
        self,
        model: str = "anthropic:claude-sonnet-4-6",
        system_prompt: str | None = None,
        system_prompt_file: Path | None = None,
        team_conventions: str | None = None,
        team_conventions_file: Path | None = None,
        retries: dict | None = None,
        recipe: Any | None = None,
    ) -> None:
        if system_prompt and system_prompt_file:
            raise ValueError("Pass system_prompt OR system_prompt_file, not both.")
        if team_conventions and team_conventions_file:
            raise ValueError("Pass team_conventions OR team_conventions_file, not both.")
        if system_prompt_file:
            system_prompt = Path(system_prompt_file).read_text()
        if team_conventions_file:
            team_conventions = Path(team_conventions_file).read_text()

        base_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        if team_conventions:
            base_prompt = (
                base_prompt
                + "\n\n# TEAM CONVENTIONS\n\n"
                + "The following document captures style and review conventions "
                "this team consistently applies. When reviewing the PR below, "
                "flag departures from these conventions as defects. Infer the "
                "appropriate severity from the convention's own framing — a "
                "stated style preference is a style nit; a stated correctness "
                "rule is a correctness defect. Cite the convention by name when "
                "flagging a related issue.\n\n" + team_conventions.strip() + "\n"
            )

        provider, model_id = _parse_model_id(model)
        canonical = f"{provider}:{model_id}"
        self.model = canonical
        self.system_prompt = base_prompt
        self.reviewer: Reviewer = _select_reviewer(
            provider, model_id, canonical, self.system_prompt
        )
        # Override stack: each frame is a dict of original-values to restore.
        self._override_stack: list[dict[str, Any]] = []
        # Retry budget. Keyed for forward-compat with Pydantic AI's
        # `retries={'output': N, 'tool_call': M}` shape; today we only
        # consume `output` (validation-failure retries).
        self.retries: dict[str, int] = dict(retries) if retries is not None else {"output": 1}

        # Recipe overrides any explicit kwargs above (the recipe wins).
        # See autoresearch-recipe-v01.
        if recipe is not None:
            recipe.apply_to_agent(self)

    # ----- override -----------------------------------------------------------

    @contextmanager
    def override(
        self,
        *,
        model: str | None = None,
        reviewer: Reviewer | None = None,
    ) -> Iterator[Agent]:
        """Context manager: swap fields for the with-block and restore on exit.

        Use for tests + eval pipelines that need to swap a reviewer (e.g.
        TestReviewer) or model without mutating client code.
        """
        frame: dict[str, Any] = {}
        if reviewer is not None:
            frame["reviewer"] = self.reviewer
            self.reviewer = reviewer
        if model is not None:
            frame["model"] = self.model
            frame["_model_reviewer"] = self.reviewer
            provider, model_id = _parse_model_id(model)
            canonical = f"{provider}:{model_id}"
            self.model = canonical
            # If reviewer wasn't also overridden, build a fresh one for the new model
            if reviewer is None:
                self.reviewer = _select_reviewer(provider, model_id, canonical, self.system_prompt)
        self._override_stack.append(frame)
        try:
            yield self
        finally:
            popped = self._override_stack.pop()
            # Restore reviewer first (it depends on model)
            if "_model_reviewer" in popped:
                self.reviewer = popped["_model_reviewer"]
            if "reviewer" in popped and "_model_reviewer" not in popped:
                self.reviewer = popped["reviewer"]
            if "model" in popped:
                self.model = popped["model"]

    # ----- run / review --------------------------------------------------------

    def run(self, pr_url: str, deps: PeerDeps | None = None) -> Review:
        """Canonical entry point. `deps` carries per-run dependencies.

        When `deps.config` is set (peer-config-v01): ignore-filter the
        Context's hunks pre-review, and apply per-path severity bounds to
        every returned Comment post-validation.

        When `deps.linters` is non-empty (linter-context-v01): pass them
        into `gather_codebase_context` so cc.linter_findings is populated.
        """
        from .config import PeerConfig, apply_severity_bounds  # local import

        ctx = gather(pr_url)
        logger.info(
            "Gathered PR context for %s: %d hunks, ~%d tokens",
            pr_url,
            len(ctx.hunks),
            ctx.token_estimate,
        )

        # peer-config-v01: drop ignored hunks before any downstream work.
        config: PeerConfig | None = (
            deps.config if deps and isinstance(deps.config, PeerConfig) else None
        )
        if config is not None:
            before = len(ctx.hunks)
            ctx = config.filter_context(ctx)
            after = len(ctx.hunks)
            if after < before:
                logger.info("Ignore filter dropped %d hunk(s)", before - after)

        # linter-context-v01: pass linters through to codebase-context gather.
        linters = list(deps.linters) if deps and deps.linters else []

        cc: CodebaseContext | None = None
        try:
            cc = gather_codebase_context(ctx, linters=linters)
            logger.info(
                "Gathered codebase context: %d symbols, %d call sites, "
                "%d tests, %d untested, %d linter findings, ~%d tokens",
                len(cc.modified_symbols),
                len(cc.call_sites),
                len(cc.related_tests),
                len(cc.untested_files),
                len(cc.linter_findings),
                cc.token_estimate,
            )
        except CodebaseContextTooLarge as e:
            logger.warning("Codebase context too large, proceeding without: %s", e)
            cc = None
        except Exception as e:
            logger.warning(
                "Codebase context extraction failed (%s); proceeding with PR context only",
                e,
            )
            cc = None

        # Retry loop. On the first pass, no extra_user_message. If everything
        # the Reviewer returned got dropped during validation AND there's
        # budget left, feed the dropped Comments back as an extra user message
        # and re-invoke the Reviewer.
        budget = int(self.retries.get("output", 0))
        attempt = 0
        n_retries_used = 0
        extra_msg: str | None = None
        valid: list[Comment] = []
        usage: dict = {}
        raw_comments: list[Comment] = []
        dropped: list[tuple[Comment, str]] = []

        while True:
            rc = RunContext[Any](deps=deps, pr_url=pr_url, attempt=attempt)
            t0 = time.perf_counter()
            raw_comments, usage = self.reviewer.review(
                ctx,
                cc,
                extra_user_message=extra_msg,
                run_context=rc,
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000.0

            # capture_run_messages() hook — no-op outside an active block.
            _emit_captured_message(
                system_prompt=self.system_prompt,
                user_prompt=format_prompt(ctx, cc) + ("\n\n" + extra_msg if extra_msg else ""),
                raw_response={"comments": [c.model_dump() for c in raw_comments]},
                usage=usage,
                latency_ms=elapsed_ms,
                pr_url=pr_url,
                attempt=attempt,
            )

            valid, dropped = _validate_comments_with_reasons(raw_comments, ctx)
            for c, reason in dropped:
                logger.warning(
                    "Dropping comment %s:%s (sev=%s) — %s", c.path, c.line, c.severity, reason
                )

            # Only retry when the Reviewer DID return something but all of it
            # was dropped — that's a grounding error worth re-prompting on.
            should_retry = budget > 0 and len(raw_comments) > 0 and len(valid) == 0
            if not should_retry:
                break
            n_retries_used += 1
            budget -= 1
            attempt += 1
            extra_msg = _build_retry_message(dropped)
            logger.info(
                "Validation dropped all %d comment(s); retrying (attempt=%d, budget left=%d)",
                len(raw_comments),
                attempt,
                budget,
            )

        # peer-config-v01: apply per-path severity bounds AFTER validation.
        if config is not None:
            valid = [apply_severity_bounds(c, config.for_path(c.path)) for c in valid]

        usage = dict(usage)
        usage["n_retries_used"] = n_retries_used

        if not valid:
            return Review(comments=[], reason="no issues found", usage=usage)
        return Review(comments=valid, usage=usage)

    def review(self, pr_url: str) -> Review:
        """Back-compat shim. Equivalent to `self.run(pr_url, deps=None)`."""
        return self.run(pr_url, deps=None)
