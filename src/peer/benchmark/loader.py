"""Bug-benchmark dataset loaders.

`BugDatasetSource` is a `Protocol` so users can plug in alternative
dataset sources (a local CSV, a database, a remote API) without touching
the runner.

`MacroscopeLoader` is the default — reads BugSamples from a JSONL file
in the Macroscope-shaped format vendored at
`dataset/benchmark/macroscope_v1.jsonl`. The actual upstream fetch +
schema mapping is out of scope for the runtime change; this loader
operates on the vendored file. Run `peer benchmark update-dataset` to
refresh from upstream (deferred follow-up).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from ..exceptions import InvalidBugSample
from .types import BugSample


class BugDatasetSource(Protocol):
    """Anything that can yield BugSamples for the benchmark."""

    def load(self, language: str | None = None) -> list[BugSample]: ...


class MacroscopeLoader:
    """Loads BugSamples from a JSONL file in Macroscope-shaped schema.

    Each line is a JSON object that round-trips through `BugSample`.
    Malformed lines raise `InvalidBugSample(line=…, error=…)`.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def load(self, language: str | None = None) -> list[BugSample]:
        """Read all rows; optionally filter by `language` (case-insensitive)."""
        if not self.path.exists():
            raise FileNotFoundError(f"Macroscope dataset not found at {self.path}")
        samples: list[BugSample] = []
        with self.path.open("r", encoding="utf-8") as fh:
            for lineno, raw in enumerate(fh, start=1):
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                    sample = BugSample.model_validate(obj)
                except (json.JSONDecodeError, ValidationError) as e:
                    raise InvalidBugSample(f"{self.path}:{lineno} — {e}") from e
                if language is not None and sample.language.lower() != language.lower():
                    continue
                samples.append(sample)
        return samples
