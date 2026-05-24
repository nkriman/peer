"""CommentClassifier Protocol + LLMCommentClassifier default impl.

Single Haiku-4.5 call per raw comment. Prompt is generated from the active
Taxonomy so custom taxonomies "just work". Disk-cached at
``~/.cache/peer/classifier_cache.jsonl`` keyed on
``sha256(repo + comment_id + taxonomy.version)``; the version in the key gives
us automatic invalidation when the Taxonomy changes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Protocol

import anthropic

from ..exceptions import UnknownCategoryError
from ..types import Severity
from .taxonomy import DefaultTaxonomy, Taxonomy
from .types import Classification, PRContext, RawComment

logger = logging.getLogger(__name__)

DEFAULT_CLASSIFIER_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_CACHE_PATH = Path.home() / ".cache" / "peer" / "classifier_cache.jsonl"

_VALID_SEVERITIES: tuple[Severity, ...] = ("critical", "important", "minor", "nit")


def _build_prompt(comment: RawComment, pr_context: PRContext, taxonomy: Taxonomy) -> str:
    cat_lines: list[str] = []
    for c in taxonomy.categories:
        cat_lines.append(f"  - {c.name}: {c.description}")
    cats_block = "\n".join(cat_lines)

    sev_block = ", ".join(taxonomy.severities)

    where = f"{comment.path}:{comment.line}" if comment.path else "(top-level comment)"

    return f"""You are classifying a single code-review comment from a pull request.

PR title: {pr_context.title}
PR url: {pr_context.pr_url}

Comment by @{comment.author} on {where}:
\"\"\"
{comment.body[:2000]}
\"\"\"

Choose exactly ONE category from this list:
{cats_block}

Choose exactly ONE severity from this list: {sev_block}

Example for the "discussion" category: a comment like "What information should
I pass as context here?" is a question, not a defect — that is discussion.

Reply with EXACTLY one line in this format (pipe-separated, no extra prose):
CATEGORY|SEVERITY|short reasoning grounded in the comment text

The reasoning MUST be a short sentence (<200 chars) that quotes or paraphrases
the comment — do NOT invent claims the comment does not make.
"""


def _parse_response(text: str, taxonomy: Taxonomy) -> Classification:
    """Parse 'CATEGORY|SEVERITY|reasoning' from the model. Coerce unknowns
    sensibly: unknown category -> raise UnknownCategoryError; unknown severity
    -> fall back to 'minor' with a warning."""
    # Take the first non-empty line that looks like our format.
    line = ""
    for raw in text.splitlines():
        s = raw.strip()
        if "|" in s:
            line = s
            break
    if not line:
        # Last-ditch: treat the whole thing as one chunk
        line = text.strip().replace("\n", " ")

    parts = [p.strip() for p in line.split("|", 2)]
    while len(parts) < 3:
        parts.append("")
    category, severity, reasoning = parts[0], parts[1].lower(), parts[2]

    # Strip surrounding quotes / markdown emphasis the model might add.
    category = re.sub(r"^[\"'`*]+|[\"'`*]+$", "", category).strip()

    valid_categories = set(taxonomy.category_names())
    if category not in valid_categories:
        # Try case-insensitive match before giving up.
        for c in valid_categories:
            if c.lower() == category.lower():
                category = c
                break
        else:
            raise UnknownCategoryError(
                f"Classifier returned unknown category {category!r}; "
                f"valid: {sorted(valid_categories)}"
            )

    if severity not in _VALID_SEVERITIES:
        logger.warning("Classifier returned unknown severity %r; coercing to 'minor'", severity)
        severity = "minor"

    if not reasoning:
        reasoning = "(no reasoning provided by classifier)"

    return Classification(
        category=category,
        severity=severity,  # type: ignore[arg-type]
        reasoning=reasoning[:500],
    )


def _cache_key(repo: str, comment_id: str, taxonomy_version: str) -> str:
    h = hashlib.sha256()
    h.update(repo.encode("utf-8"))
    h.update(b"\x00")
    h.update(comment_id.encode("utf-8"))
    h.update(b"\x00")
    h.update(taxonomy_version.encode("utf-8"))
    return h.hexdigest()


def _repo_from_pr_url(pr_url: str) -> str:
    # Best-effort owner/repo extraction; falls back to the raw URL if it fails.
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+)/pull/\d+", pr_url.strip())
    if not m:
        return pr_url
    return f"{m.group(1)}/{m.group(2)}"


class CommentClassifier(Protocol):
    """Classifies one raw comment into a Taxonomy category + severity."""

    def classify(self, comment: RawComment, pr_context: PRContext) -> Classification: ...


class LLMCommentClassifier:
    """Default classifier: Haiku 4.5 with a Taxonomy-derived prompt.

    Disk-cache hits skip the LLM call. Cache key includes taxonomy.version so
    Taxonomy changes invalidate automatically.
    """

    def __init__(
        self,
        taxonomy: Taxonomy = DefaultTaxonomy,
        model: str = DEFAULT_CLASSIFIER_MODEL,
        client: anthropic.Anthropic | None = None,
        cache_path: Path | None = DEFAULT_CACHE_PATH,
    ) -> None:
        self.taxonomy = taxonomy
        self.model = model
        self._client = client
        self.cache_path = cache_path
        self._cache: dict[str, Classification] = {}
        self._cache_loaded = False

    @property
    def client(self) -> anthropic.Anthropic:
        if self._client is None:
            self._client = anthropic.Anthropic()
        return self._client

    # ------------------------------------------------------------------ cache

    def _load_cache(self) -> None:
        if self._cache_loaded:
            return
        self._cache_loaded = True
        if self.cache_path is None or not self.cache_path.exists():
            return
        try:
            with self.cache_path.open() as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        key = rec.get("key")
                        cls_raw = rec.get("classification")
                        if key and cls_raw:
                            self._cache[key] = Classification.model_validate(cls_raw)
                    except (json.JSONDecodeError, Exception) as e:
                        logger.debug("Skipping malformed cache line: %s", e)
        except OSError as e:
            logger.warning("Failed to read classifier cache %s: %s", self.cache_path, e)

    def _write_cache(self, key: str, classification: Classification) -> None:
        if self.cache_path is None:
            return
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with self.cache_path.open("a") as fh:
                fh.write(
                    json.dumps(
                        {
                            "key": key,
                            "taxonomy_version": self.taxonomy.version,
                            "classification": classification.model_dump(),
                        }
                    )
                    + "\n"
                )
        except OSError as e:
            logger.warning("Failed to write classifier cache: %s", e)

    # --------------------------------------------------------------- classify

    def classify(self, comment: RawComment, pr_context: PRContext) -> Classification:
        self._load_cache()
        repo = _repo_from_pr_url(pr_context.pr_url)
        key = _cache_key(repo, comment.source_id, self.taxonomy.version)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        prompt = _build_prompt(comment, pr_context, self.taxonomy)
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        text = ""
        for block in resp.content:
            t = getattr(block, "text", None)
            if t:
                text += t

        classification = _parse_response(text, self.taxonomy)
        self._cache[key] = classification
        self._write_cache(key, classification)
        return classification
