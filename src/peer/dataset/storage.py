"""GoldSampleStorage Protocol + JSONLStorage default impl.

One file per dataset, one GoldSample per line. `add` is append-style but
rewrites the file if `pr_url` already exists (overwrite-on-duplicate). Load
validates every line via Pydantic; malformed lines raise InvalidGoldSample
with the line number.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from ..exceptions import InvalidGoldSample
from .types import GoldSample


class GoldSampleStorage(Protocol):
    def add(self, sample: GoldSample) -> None: ...
    def load_all(self) -> list[GoldSample]: ...
    def find(self, pr_url: str) -> GoldSample | None: ...
    def delete(self, pr_url: str) -> None: ...


class JSONLStorage:
    """One `.jsonl` file = one dataset. Each line is a serialized GoldSample."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ read

    def load_all(self) -> list[GoldSample]:
        if not self.path.exists():
            return []
        out: list[GoldSample] = []
        with self.path.open() as fh:
            for lineno, raw in enumerate(fh, start=1):
                line = raw.rstrip("\n")
                if not line.strip():
                    continue
                try:
                    out.append(GoldSample.model_validate_json(line))
                except ValidationError as e:
                    raise InvalidGoldSample(
                        f"{self.path}:{lineno}: failed to validate GoldSample: {e}"
                    ) from e
                except json.JSONDecodeError as e:
                    raise InvalidGoldSample(f"{self.path}:{lineno}: malformed JSON: {e}") from e
        return out

    def find(self, pr_url: str) -> GoldSample | None:
        for sample in self.load_all():
            if sample.pr_url == pr_url:
                return sample
        return None

    # ----------------------------------------------------------------- write

    def add(self, sample: GoldSample) -> None:
        """Append, OR rewrite-with-replace if pr_url already exists."""
        existing = self.load_all() if self.path.exists() else []
        replaced = False
        for i, s in enumerate(existing):
            if s.pr_url == sample.pr_url:
                existing[i] = sample
                replaced = True
                break
        if replaced:
            self._write_all(existing)
        else:
            with self.path.open("a") as fh:
                fh.write(sample.model_dump_json() + "\n")

    def delete(self, pr_url: str) -> None:
        existing = self.load_all() if self.path.exists() else []
        keep = [s for s in existing if s.pr_url != pr_url]
        if len(keep) != len(existing):
            self._write_all(keep)

    # ---------------------------------------------------------------- helper

    def _write_all(self, samples: list[GoldSample]) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp.open("w") as fh:
            for s in samples:
                fh.write(s.model_dump_json() + "\n")
        tmp.replace(self.path)
