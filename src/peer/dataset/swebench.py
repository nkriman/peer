"""Reconstruct CR-Bench-style gold labels from SWE-bench_Verified (Phase 1b, peer-4z5).

CR-Bench isn't publicly downloadable, but it's derived from SWE-bench by the
authors' own account. We reconstruct equivalent gold-defect labels directly
from SWE-bench_Verified (public, human-verified): each instance's fix `patch`
identifies the files/lines that were defective at `base_commit`, and
`problem_statement` describes the defect a good reviewer should have caught.

This is the CONTAMINATED-but-broad half of the hybrid benchmark: SWE-bench is
in model training data, so every sample here is tagged
`contamination_safe=False`. The leaderboard LEADS with the fresh holdout
(`contamination_safe=True`, see holdout.py); this half adds breadth and
comparability to published CR-Bench/SWE-bench numbers.

No git-blame or repo cloning required: the fix patch alone localizes the
defect. We deliberately do NOT LLM-paraphrase the problem statement (CR-Bench
does) — that costs quota and the raw, truncated statement is a faithful
defect description. Paraphrasing is an optional future enrichment.

Fetch the source (network, no quota):

    uv run python -c "from datasets import load_dataset; \\
      load_dataset('princeton-nlp/SWE-bench_Verified', split='test').to_json('swebench_verified.jsonl')"

then: ``swebench_jsonl_to_gold_samples(Path('swebench_verified.jsonl'))``
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable
from pathlib import Path

from unidiff import PatchSet

from .types import GoldDefect, GoldSample, GoldSampleMetadata

logger = logging.getLogger(__name__)


def _parse_instance_id(instance_id: str) -> tuple[str, str, int] | None:
    """('django__django-11099') -> ('django', 'django', 11099). Returns None
    if the id doesn't match the expected shape. instance_id format is
    "{owner}__{repo}-{number}", e.g. "sphinx-doc__sphinx-8721"."""
    if "__" not in instance_id:
        return None
    owner, rest = instance_id.split("__", 1)
    m = re.match(r"^(?P<repo>.+)-(?P<number>\d+)$", rest)
    if not m or not owner:
        return None
    return owner, m.group("repo"), int(m.group("number"))


def _patch_to_defects(
    patch: str,
    description: str,
    instance_id: str,
) -> list[GoldDefect]:
    """One GoldDefect per file the fix patch touches, anchored at the first
    hunk's source line (the location in the BUGGY base file)."""
    try:
        patch_set = PatchSet.from_string(patch)
    except Exception as e:
        logger.warning("swebench %s: unparseable patch (%s); skipping", instance_id, e)
        return []
    defects: list[GoldDefect] = []
    for patched_file in patch_set:
        # Skip pure-deletions / files with no hunks we can anchor.
        hunks = list(patched_file)
        if not hunks:
            continue
        path = patched_file.path
        if not path or path == "/dev/null":
            continue
        line = hunks[0].source_start
        defects.append(
            GoldDefect(
                path=path,
                line=line if isinstance(line, int) and line > 0 else None,
                category="defect-correctness",
                severity="important",
                description=description,
                source=f"crbench-recon:swe-verified:{instance_id}",
                confidence="high",  # SWE-bench_Verified is human-verified solvable
            )
        )
    return defects


def swebench_record_to_gold_sample(
    rec: dict,
    *,
    max_desc_chars: int = 2000,
) -> GoldSample | None:
    """Convert one SWE-bench_Verified record to a GoldSample, or None if it
    lacks the fields we need (instance_id, patch) or yields no defects."""
    instance_id = rec.get("instance_id")
    patch = rec.get("patch")
    if not isinstance(instance_id, str) or not isinstance(patch, str) or not patch.strip():
        return None
    problem = (rec.get("problem_statement") or "").strip()
    description = problem[:max_desc_chars] if problem else f"Defect fixed in {instance_id}"

    defects = _patch_to_defects(patch, description, instance_id)
    if not defects:
        return None

    parsed = _parse_instance_id(instance_id)
    if parsed is not None:
        owner, repo, number = parsed
        pr_url = f"https://github.com/{owner}/{repo}/pull/{number}"
        repo_full = f"{owner}/{repo}"
    else:
        # Fall back to a stable synthetic id; Phase 2 replay keys off the
        # source tag / kept SWE-bench record, not this URL.
        pr_url = f"swebench://{instance_id}"
        repo_full = str(rec.get("repo") or "")

    pr_title = f"[SWE-bench_Verified] {repo_full} {instance_id}".strip()
    return GoldSample(
        pr_url=pr_url,
        pr_title=pr_title,
        pr_body=description,
        head_sha=str(rec.get("base_commit") or ""),
        gold_defects=defects,
        metadata=GoldSampleMetadata(
            defect_comment_count=len(defects),
            has_followup_bugfix=True,
            curation_source="crbench-recon:swe-verified",
            # SWE-bench is in training data — this half is explicitly contaminated.
            contamination_safe=False,
        ),
    )


def swebench_records_to_gold_samples(
    records: Iterable[dict],
    *,
    max_desc_chars: int = 2000,
) -> list[GoldSample]:
    out: list[GoldSample] = []
    skipped = 0
    for rec in records:
        gs = swebench_record_to_gold_sample(rec, max_desc_chars=max_desc_chars)
        if gs is None:
            skipped += 1
            continue
        out.append(gs)
    logger.info("swebench reconstruction: %d gold samples (%d skipped)", len(out), skipped)
    return out


def swebench_jsonl_to_gold_samples(
    path: Path | str,
    *,
    max_desc_chars: int = 2000,
) -> list[GoldSample]:
    """Read a local SWE-bench_Verified JSONL dump (one record per line) and
    convert. Download the dump first (see module docstring)."""
    p = Path(path)
    records: list[dict] = []
    with p.open() as fh:
        for lineno, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                logger.warning("%s:%d: malformed JSON, skipping (%s)", p, lineno, e)
    return swebench_records_to_gold_samples(records, max_desc_chars=max_desc_chars)
