"""LLM-as-judge helper for semantic same-issue matching.

Promoted from the MVP at src/peer/eval.py: same prompt, but the comparator
now takes a GoldDefect (curated dataset record) instead of a raw HumanComment.

eval-v02 adds the `LLMJudge` Evaluator dataclass — a configurable judge
with `rubric / model / include_input / include_expected_output /
include_reason` fields. `judge_match` stays as a thin convenience for the
"same issue?" use case.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import anthropic

from ..dataset.types import GoldDefect, GoldSample
from ..types import Comment, Review
from .types import AggregateKind, MetricResult

JUDGE_MODEL = "claude-haiku-4-5-20251001"
JUDGE_PROMPT = """Two code reviewers commented on a pull request, both on the same file. Decide whether they are flagging the SAME ISSUE or DIFFERENT ISSUES.

Reviewer A (line {peer_line}):
{peer_body}

Reviewer B (line {human_line}):
{human_body}

Same issue = the underlying concern is the same, even if phrased differently or focused on slightly different lines of the same code. Different issue = they're about different things entirely (different bugs, different concerns).

Respond with exactly one word: SAME or DIFFERENT."""


# peer-ivb: CR-Bench-style 3-way classification (arxiv 2603.11078).
# Hit / Valid / Noise lets us compute Signal-to-Noise Ratio (peer-k03),
# which is the standard field control against verbose-reviewer wins.
CommentClass = Literal["hit", "valid", "noise"]

JUDGE_3WAY_PROMPT = """A code reviewer made a comment on a pull request. You also see the list of GOLD DEFECTS the human reviewers identified for this PR. Classify the comment into exactly one of three categories.

CATEGORIES:
- HIT: the comment identifies or directly relates to one of the gold defects.
- VALID: the comment does NOT match a gold defect, but is still a useful, accurate, actionable suggestion about the code (e.g. real style improvement, real bug not in the gold list, useful refactor).
- NOISE: the comment is unhelpful, hallucinated, off-topic, or just describes what the code does without identifying any issue.

When in doubt between VALID and NOISE, choose NOISE — this rubric is intentionally conservative to penalise verbose reviewers.

COMMENT (line {comment_line}):
{comment_body}

GOLD DEFECTS for this PR:
{gold_defects}

Respond with exactly one word: HIT or VALID or NOISE."""


def classify_comment(
    comment: Comment,
    gold_defects: list[GoldDefect],
    client: anthropic.Anthropic | None = None,
    model: str = JUDGE_MODEL,
) -> CommentClass:
    """3-way comment classification (Hit / Valid / Noise) per CR-Bench (2026).

    Used by SignalToNoiseRatio (peer-k03) to distinguish 'useful reviewer'
    from 'verbose reviewer with high recall'. Returns 'noise' on any parse
    failure (conservative — keeps the SNR honest).
    """
    if client is None:
        client = anthropic.Anthropic()
    if gold_defects:
        gold_text = "\n".join(
            f"- [{g.severity}] {g.path}:{g.line if g.line is not None else (g.line_range[0] if g.line_range else 0)} "
            f"{g.description[:200]}"
            for g in gold_defects
        )
    else:
        gold_text = "(no labeled defects for this PR)"
    prompt = JUDGE_3WAY_PROMPT.format(
        comment_line=comment.line if comment.line is not None else 0,
        comment_body=comment.body[:1500],
        gold_defects=gold_text,
    )
    resp = client.messages.create(
        model=model,
        max_tokens=10,
        messages=[{"role": "user", "content": prompt}],
    )
    text = ""
    for block in resp.content:
        t = getattr(block, "text", None)
        if t:
            text = t.strip().upper()
            break
    if text.startswith("HIT"):
        return "hit"
    if text.startswith("VALID"):
        return "valid"
    return "noise"


def judge_match(
    peer_comment: Comment,
    gold_defect: GoldDefect,
    client: anthropic.Anthropic | None = None,
) -> bool:
    """Use a cheap LLM judge to decide if a peer comment refers to the same
    issue as a gold defect."""
    if client is None:
        client = anthropic.Anthropic()
    gold_line = (
        gold_defect.line
        if gold_defect.line is not None
        else (gold_defect.line_range[0] if gold_defect.line_range else 0)
    )
    prompt = JUDGE_PROMPT.format(
        peer_line=peer_comment.line if peer_comment.line is not None else 0,
        peer_body=peer_comment.body[:1500],
        human_line=gold_line,
        human_body=gold_defect.description[:1500],
    )
    resp = client.messages.create(
        model=JUDGE_MODEL,
        max_tokens=10,
        messages=[{"role": "user", "content": prompt}],
    )
    text = ""
    for block in resp.content:
        t = getattr(block, "text", None)
        if t:
            text = t.strip().upper()
            break
    return text.startswith("SAME")


# ---------------------------------------------------------------------------
# eval-v02: configurable LLMJudge Evaluator
# ---------------------------------------------------------------------------


@dataclass
class LLMJudge:
    """Configurable LLM-as-judge Evaluator.

    Inspired by Pydantic Evals' `LLMJudge` (see
    `docs/pydantic_evals_design_philosophy.md`). Users instantiate with
    their own rubric + visibility flags; the framework builds a prompt and
    parses the response.

    For peer's specific use cases (RationaleGrounding etc.), subclass and
    override `rubric` + `include_input`.

    Per eval-v02 design.md Decision 4. NOT in the default metric set;
    user-supplied or via `peer eval --with-rationale-grounding`.
    """

    name: str = "llm_judge"
    rubric: str = "Evaluate the comment quality."
    model: str = "claude-haiku-4-5-20251001"
    include_input: bool = False
    include_expected_output: bool = True
    include_reason: bool = True
    aggregate_kind: AggregateKind = AggregateKind.MEAN
    priority: int = 20  # runs after deterministic checks

    def score(
        self,
        sample: GoldSample,
        review: Review,
        client: anthropic.Anthropic | None = None,
    ) -> MetricResult:
        """Score the review against the rubric. Returns a per-sample dict
        result `{score: 0-1, reason: str}` (or just `score` when
        `include_reason=False`). Aggregator can take mean across samples."""
        if client is None:
            client = anthropic.Anthropic()
        # Build a single combined judgment over all peer comments.
        # Subclasses may override this for per-comment scoring (see
        # RationaleGrounding's overridden score below).
        comments_text = (
            "\n\n".join(
                f"- {c.severity.upper()} {c.path}:{c.line}\n  {c.body}\n  -- {c.rationale}"
                for c in review.comments
            )
            or "(no comments)"
        )
        sections = [f"RUBRIC:\n{self.rubric}", "REVIEWER COMMENTS:\n" + comments_text]
        if self.include_input:
            sections.append(
                "PR INPUT:\nTitle: "
                + sample.pr_title
                + "\nURL: "
                + sample.pr_url
                + ("\nDescription: " + sample.pr_body if sample.pr_body else "")
            )
        if self.include_expected_output and sample.gold_defects:
            gold = "\n".join(
                f"- [{g.severity}] {g.path}:{g.line} {g.description[:200]}"
                for g in sample.gold_defects
            )
            sections.append("GOLD DEFECTS:\n" + gold)
        instruction = "Respond with: SCORE: <0.0-1.0>" + (
            "\nREASON: <one sentence>" if self.include_reason else ""
        )
        prompt = "\n\n".join(sections) + "\n\n" + instruction
        resp = client.messages.create(
            model=self.model,
            max_tokens=200 if self.include_reason else 40,
            messages=[{"role": "user", "content": prompt}],
        )
        text = ""
        for block in resp.content:
            t = getattr(block, "text", None)
            if t:
                text = t
                break
        score, reason = _parse_score_response(text)
        detail: dict = {"raw_response": text.strip()}
        if reason is not None:
            detail["reason"] = reason
        return MetricResult(name=self.name, value=score, per_sample_detail=detail)


@dataclass
class RationaleGrounding(LLMJudge):
    """OPT-IN judge that scores how well peer comments' rationales reference
    the cited code.

    Per eval-v02 proposal.md adversarial-review item 1.5 + 5.1:
    - default OFF (NOT in default metric set)
    - ~$0.001 per peer comment via Haiku
    - sold as catching hallucinated-line-citation issues; v1 reference
      dataset has ~0% hallucination so this metric is for users with
      weaker reviewer models / less constrained prompts
    """

    name: str = "rationale_grounding"
    rubric: str = (
        "Score 0-1: does this code review's rationale accurately reference "
        "the code it cites? Specifically: are the line numbers correct? Are "
        "the function/variable names referenced actually present in the "
        "cited code? Are any 'consistent with X' claims actually consistent "
        "with X? Score 1.0 if the rationale is fully grounded; 0.0 if it's "
        "hallucinated. Always include reasoning."
    )
    include_input: bool = True  # judge needs to see the diff hunk
    include_expected_output: bool = False
    priority: int = 25


def _parse_score_response(text: str) -> tuple[float | None, str | None]:
    """Parse `SCORE: 0.85\\nREASON: ...` out of judge response.
    Returns (score, reason) — both Optional."""
    score: float | None = None
    reason: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.upper().startswith("SCORE:"):
            rest = line.split(":", 1)[1].strip()
            try:
                score = float(rest.split()[0])
            except (ValueError, IndexError):
                score = None
        elif line.upper().startswith("REASON:"):
            reason = line.split(":", 1)[1].strip()
    # Fallback: SAME/DIFFERENT-style binary responses (back-compat).
    if score is None:
        up = text.strip().upper()
        if up.startswith("SAME"):
            score = 1.0
        elif up.startswith("DIFFERENT"):
            score = 0.0
    return score, reason
