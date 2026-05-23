"""EnrichmentStep Protocol + three implementations.

Default is `NoEnrichment` (passthrough). `PostMergeBugfixCorrelation` and
`LLMOracleEnrichment` are opt-in. Both opt-in impls are conservative — they
only ADD GoldDefect entries (never delete/rewrite human-derived ones) and
they tag `source=` so downstream consumers can filter.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Protocol

import anthropic

from ..context import _gh_run, parse_pr_url
from .types import GoldDefect, GoldSample, PRContext

logger = logging.getLogger(__name__)

DEFAULT_ORACLE_MODEL = "claude-opus-4-7"

_BUGFIX_TITLE_RE = re.compile(r"\b(fix|fixes|fixed|regression|bug|bugfix|hotfix)\b", re.I)


class EnrichmentStep(Protocol):
    """Augment a proposed GoldSample with extra defects from other sources."""

    def enrich(self, sample: GoldSample, pr_context: PRContext) -> GoldSample: ...


class NoEnrichment:
    """Default: passthrough. Returns the sample unchanged."""

    def enrich(self, sample: GoldSample, pr_context: PRContext) -> GoldSample:
        return sample


# ---------------------------------------------------------------------------
# PostMergeBugfixCorrelation
# ---------------------------------------------------------------------------


def _list_pr_files(owner: str, repo: str, number: int) -> list[str]:
    try:
        data = _gh_run(
            ["api", f"repos/{owner}/{repo}/pulls/{number}/files", "--paginate"]
        ) or []
    except Exception as e:
        logger.warning("Could not list files for %s/%s#%d: %s", owner, repo, number, e)
        return []
    return [f.get("filename", "") for f in data if f.get("filename")]


def _search_followup_prs(
    owner: str, repo: str, after: datetime, before: datetime
) -> list[dict]:
    """Search merged PRs in [after, before] whose title looks like a bugfix."""
    q = (
        f"repo:{owner}/{repo} is:pr is:merged "
        f"merged:{after.date().isoformat()}..{before.date().isoformat()}"
    )
    try:
        data = _gh_run(
            ["api", "-X", "GET", "search/issues", "-f", f"q={q}", "--paginate"]
        )
    except Exception as e:
        logger.warning("Follow-up PR search failed: %s", e)
        return []
    items = data.get("items", []) if isinstance(data, dict) else []
    return [it for it in items if _BUGFIX_TITLE_RE.search(it.get("title", ""))]


class PostMergeBugfixCorrelation:
    """Heuristic enrichment: search for PRs merged in the 30 days after the
    current PR with bugfix-y titles overlapping the same files, and add their
    diffs as low/medium-confidence GoldDefect entries.

    NOTE: this is a best-effort heuristic — false-positives are expected and
    every added defect is marked `source="post_merge_correlation"` so the
    operator can filter / spot-check.
    """

    def __init__(self, window_days: int = 30, confidence: str = "medium") -> None:
        self.window_days = window_days
        self.confidence = confidence  # "medium" by default; spec allows low/medium

    def enrich(self, sample: GoldSample, pr_context: PRContext) -> GoldSample:
        if sample.merged_at is None:
            logger.debug(
                "PostMergeBugfixCorrelation: skipping %s (not merged)", sample.pr_url
            )
            return sample
        try:
            owner, repo, number = parse_pr_url(sample.pr_url)
        except Exception as e:
            logger.warning("Cannot parse PR URL %s: %s", sample.pr_url, e)
            return sample

        merged_at = sample.merged_at
        if merged_at.tzinfo is None:
            merged_at = merged_at.replace(tzinfo=timezone.utc)
        window_end = merged_at + timedelta(days=self.window_days)

        our_files = set(_list_pr_files(owner, repo, number))
        if not our_files:
            return sample

        candidates = _search_followup_prs(owner, repo, merged_at, window_end)
        added: list[GoldDefect] = []
        for cand in candidates:
            cand_num = cand.get("number")
            if not cand_num or cand_num == number:
                continue
            cand_files = set(_list_pr_files(owner, repo, cand_num))
            overlap = our_files & cand_files
            if not overlap:
                continue
            title = cand.get("title", "")
            cand_url = cand.get("html_url", "")
            for path in sorted(overlap):
                added.append(
                    GoldDefect(
                        path=path,
                        line=None,
                        category="defect-correctness",
                        severity="important",
                        description=(
                            f"Follow-up PR #{cand_num} '{title}' modified this file "
                            f"shortly after merge; possible defect introduced here. "
                            f"See {cand_url}."
                        ),
                        source="post_merge_correlation",
                        confidence=self.confidence,  # type: ignore[arg-type]
                        original_comment_excerpt=None,
                    )
                )

        if not added:
            return sample
        new_defects = list(sample.gold_defects) + added
        return sample.model_copy(
            update={
                "gold_defects": new_defects,
                "metadata": sample.metadata.model_copy(
                    update={
                        "has_followup_bugfix": True,
                        "defect_comment_count": sample.metadata.defect_comment_count
                        + len(added),
                    }
                ),
            }
        )


# ---------------------------------------------------------------------------
# LLMOracleEnrichment
# ---------------------------------------------------------------------------


_ORACLE_PROMPT = """You are a senior code reviewer doing a final read of a pull
request. Your job is to identify DEFECTS that a thorough reviewer would have
flagged — bugs, security issues, performance pitfalls, missing tests, broken
API contracts.

Be conservative: only flag issues you are highly confident are real defects
grounded in the visible diff. Do NOT speculate. Do NOT flag style preferences.
If the PR is clean, return an empty list.

PR title: {title}
PR url: {pr_url}

PR body:
{body}

Diff summary:
{diff}

Respond as JSON in this exact shape:
{{"defects": [
  {{"path": "path/to/file.py",
    "line": 42,
    "severity": "important",
    "description": "...",
    "confidence": "high"}}
]}}

severity must be one of: critical, important, minor, nit.
confidence must be one of: high, medium, low.
Only defects with confidence=high will be added to the gold sample.
"""


class LLMOracleEnrichment:
    """Strong-model second opinion. Adds only `confidence="high"` defects.

    NOTE: stubbed-ish for v0.1 — calls the model and parses JSON best-effort.
    If the model can't produce parseable JSON, the sample is returned unchanged
    with a warning rather than erroring.
    """

    def __init__(
        self,
        model: str = DEFAULT_ORACLE_MODEL,
        client: Optional[anthropic.Anthropic] = None,
        max_diff_chars: int = 20000,
    ) -> None:
        self.model = model
        self._client = client
        self.max_diff_chars = max_diff_chars

    @property
    def client(self) -> anthropic.Anthropic:
        if self._client is None:
            self._client = anthropic.Anthropic()
        return self._client

    def _fetch_diff(self, pr_url: str) -> str:
        try:
            owner, repo, number = parse_pr_url(pr_url)
            text = _gh_run(
                ["pr", "diff", str(number), "--repo", f"{owner}/{repo}"],
                parse_json=False,
            )
            return (text or "")[: self.max_diff_chars]
        except Exception as e:
            logger.warning("Oracle: cannot fetch diff for %s: %s", pr_url, e)
            return ""

    def enrich(self, sample: GoldSample, pr_context: PRContext) -> GoldSample:
        diff = pr_context.diff_summary or self._fetch_diff(sample.pr_url)
        prompt = _ORACLE_PROMPT.format(
            title=pr_context.title or sample.pr_title,
            pr_url=sample.pr_url,
            body=(pr_context.body or sample.pr_body)[:3000],
            diff=diff[: self.max_diff_chars],
        )
        try:
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as e:
            logger.warning("LLMOracleEnrichment: model call failed: %s", e)
            return sample

        text = ""
        for block in resp.content:
            t = getattr(block, "text", None)
            if t:
                text += t

        # Best-effort JSON extraction.
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            logger.warning("LLMOracleEnrichment: no JSON in oracle response")
            return sample
        try:
            payload = json.loads(m.group(0))
        except json.JSONDecodeError as e:
            logger.warning("LLMOracleEnrichment: cannot parse JSON: %s", e)
            return sample

        added: list[GoldDefect] = []
        for d in payload.get("defects", []) or []:
            if (d.get("confidence") or "").lower() != "high":
                continue
            path = d.get("path")
            desc = d.get("description")
            if not path or not desc:
                continue
            severity = (d.get("severity") or "important").lower()
            if severity not in ("critical", "important", "minor", "nit"):
                severity = "important"
            line = d.get("line")
            try:
                line_int = int(line) if line is not None else None
            except (ValueError, TypeError):
                line_int = None
            added.append(
                GoldDefect(
                    path=path,
                    line=line_int,
                    category="defect-correctness",
                    severity=severity,  # type: ignore[arg-type]
                    description=desc[:1000],
                    source="llm_oracle",
                    confidence="high",
                    original_comment_excerpt=None,
                )
            )

        if not added:
            return sample
        return sample.model_copy(
            update={
                "gold_defects": list(sample.gold_defects) + added,
                "metadata": sample.metadata.model_copy(
                    update={
                        "defect_comment_count": sample.metadata.defect_comment_count
                        + len(added),
                    }
                ),
            }
        )
