"""Dataset-split convention: `<name>.jsonl` + `<name>.dev.jsonl` + `<name>.test.jsonl`.

Curation produces a base file plus optional `.dev` / `.test` siblings.
autoresearch loops should always run against the `.dev` split; benchmark
publication should always cite the `.test` split. The split convention is
a runtime accessor — actual splitting happens at curation time.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .storage import JSONLStorage
from .types import GoldSample

logger = logging.getLogger(__name__)

_ALLOWED_SPLITS = {"dev", "test"}


def load_split(base_path: Path | str, split: str) -> list[GoldSample]:
    """Load a named split of a dataset.

    Args:
        base_path: e.g. `Path("data/django_v2.jsonl")`.
        split: one of `"dev"` or `"test"`. Other names raise `ValueError`.

    Returns the GoldSamples from `<stem>.<split>.jsonl` when that file
    exists; otherwise falls back to `base_path` itself and logs INFO.
    """
    if split not in _ALLOWED_SPLITS:
        raise ValueError(f"split must be one of {sorted(_ALLOWED_SPLITS)}; got {split!r}")
    base = Path(base_path)
    # Build sibling path: e.g. "data/django_v2.jsonl" + split="dev" → "data/django_v2.dev.jsonl"
    if base.suffix:
        sibling = base.with_suffix("." + split + base.suffix)
    else:
        sibling = base.parent / f"{base.name}.{split}"
    target = sibling if sibling.exists() else base
    if target == base:
        logger.info(
            "no split file at %s; loading the base dataset %s instead",
            sibling,
            base,
        )
    return JSONLStorage(target).load_all()
