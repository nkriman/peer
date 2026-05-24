"""Recipe — single Pydantic model covering peer's reviewer mutation surface.

A `Recipe` captures everything an autoresearch iteration is allowed to
mutate: model, temperature, max_tokens, system-prompt path, retries, codebase-
context budgets, and post-processing knobs. A default-constructed Recipe
reproduces today's `Agent()` behavior — so applying a recipe to a fresh
agent is a no-op when the recipe is untouched.

The companion `prompts/default_system_prompt.md` file is the *content* under
mutation; this YAML is the *configuration*. The autoresearch loop edits one
or both between iterations.

See `program.md` at the repo root for how the autoresearch agent uses this.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

Severity = Literal["critical", "important", "minor", "nit"]


class Recipe(BaseModel):
    """Full reviewer configuration in one place. Mutated by autoresearch."""

    model_config = ConfigDict(extra="forbid")

    # ----- LLM call -----
    model: str = "anthropic:claude-sonnet-4-6"
    temperature: float = 0.0
    max_tokens: int = 8192

    # ----- Prompt -----
    system_prompt_path: Path = Path("prompts/default_system_prompt.md")
    team_conventions_path: Path | None = None

    # ----- Retries -----
    retries: dict[str, int] = Field(default_factory=lambda: {"output": 1})

    # ----- Codebase-context budgets -----
    codebase_context_max_tokens: int = 30000
    codebase_context_max_call_sites_per_symbol: int = 5
    codebase_context_max_test_file_chars: int = 5000

    # ----- Post-processing -----
    post_processing_max_comments_per_pr: int | None = None
    post_processing_severity_floor: Severity | None = None
    post_processing_drop_paths: list[str] = Field(default_factory=list)

    # ----- Strategy plumbing (filled in by autoresearch-strategies-v01) -----
    reviewer_dotted_path: str | None = None
    reviewer_kwargs: dict[str, Any] = Field(default_factory=dict)

    # -------------------------------------------------------------------
    # YAML round-trip
    # -------------------------------------------------------------------

    def to_yaml(self) -> str:
        """Dump to a canonical YAML string.

        Path fields are serialized as strings; defaults are preserved.
        """
        data = self.model_dump(mode="json")
        text: str = yaml.safe_dump(data, sort_keys=True, default_flow_style=False)
        return text

    @classmethod
    def from_yaml(cls, text: str) -> Recipe:
        """Parse YAML into a Recipe. Raises ValidationError on unknown fields."""
        obj = yaml.safe_load(text) or {}
        return cls.model_validate(obj)

    @classmethod
    def from_file(cls, path: Path | str) -> Recipe:
        return cls.from_yaml(Path(path).read_text())

    def canonical_hash(self) -> str:
        """First 8 hex chars of SHA-256 over the canonical YAML.

        Used as the recipe identifier in the leaderboard TSV.
        """
        return hashlib.sha256(self.to_yaml().encode("utf-8")).hexdigest()[:8]

    # -------------------------------------------------------------------
    # Apply to Agent
    # -------------------------------------------------------------------

    def apply_to_agent(self, agent: Any) -> Any:
        """Mutate `agent` in place to match this recipe. Returns the agent
        for chaining.

        Re-loads the system prompt from `system_prompt_path`. Optionally
        appends team conventions if `team_conventions_path` is set.
        Rebuilds the reviewer so model + temperature + max_tokens land on
        the underlying SDK call. Sets `retries`.
        """
        from .agent import _parse_model_id, _select_reviewer

        prompt_text = Path(self.system_prompt_path).read_text()
        if self.team_conventions_path is not None:
            tc = Path(self.team_conventions_path).read_text().strip()
            prompt_text = (
                prompt_text
                + "\n\n# TEAM CONVENTIONS\n\n"
                + "The following document captures style and review conventions "
                "this team consistently applies. When reviewing the PR below, "
                "flag departures from these conventions as defects. Infer the "
                "appropriate severity from the convention's own framing — a "
                "stated style preference is a style nit; a stated correctness "
                "rule is a correctness defect. Cite the convention by name when "
                "flagging a related issue.\n\n" + tc + "\n"
            )

        agent.system_prompt = prompt_text
        agent.retries = dict(self.retries)
        provider, model_id = _parse_model_id(self.model)
        canonical = f"{provider}:{model_id}"
        agent.model = canonical

        # Build reviewer. If a strategy is wired, defer to that path
        # (autoresearch-strategies-v01 expands this branch via the real
        # registry; until then we resolve dotted paths via importlib).
        if self.reviewer_dotted_path:
            cls = _resolve_dotted(self.reviewer_dotted_path)
            agent.reviewer = cls(**self._resolved_reviewer_kwargs())
        else:
            base = _select_reviewer(provider, model_id, canonical, prompt_text)
            # Re-set temperature + max_tokens — _select_reviewer doesn't know about Recipe.
            if hasattr(base, "temperature"):
                base.temperature = self.temperature
            if hasattr(base, "max_tokens"):
                base.max_tokens = self.max_tokens
            agent.reviewer = base
        return agent

    def _resolved_reviewer_kwargs(self) -> dict[str, Any]:
        """Resolve any dotted-path values in reviewer_kwargs to concrete
        instances. One level of recursion only — values that look like
        peer.* dotted paths AND resolve to a Reviewer-shaped class get
        instantiated with no kwargs. Other values pass through.
        """
        out: dict[str, Any] = {}
        for k, v in self.reviewer_kwargs.items():
            if isinstance(v, str) and v.startswith("peer."):
                try:
                    cls = _resolve_dotted(v)
                    out[k] = cls()
                    continue
                except Exception:
                    pass
            out[k] = v
        return out


def _resolve_dotted(path: str) -> Any:
    """Resolve a dotted import path to a class.

    autoresearch-strategies-v01 introduces a richer registry with short
    names; until then this falls back to plain importlib lookup. Both
    paths through the recipe go through the registry once it lands.
    """
    import importlib

    if "." not in path:
        # Short-name lookup — try the strategies registry if available.
        try:
            from .strategies.registry import resolve_strategy

            return resolve_strategy(path)
        except ImportError as e:
            raise ValueError(
                f"Cannot resolve short name {path!r}: peer.strategies registry "
                f"is not installed. Provide a full dotted path instead."
            ) from e
    module_path, attr = path.rsplit(".", 1)
    mod = importlib.import_module(module_path)
    return getattr(mod, attr)
