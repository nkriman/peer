"""leaderboard.tsv — tab-separated, append-only log of autoresearch runs.

One row per iteration. Schema is fixed (see LEADERBOARD_HEADER). Appends
are atomic: write to .tmp then os.replace.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

LEADERBOARD_HEADER = (
    "commit_sha\trecipe_hash\tutility\tdetection_rate\t"
    "precision_minor\tprecision_important\tprecision_critical\t"
    "cost_usd\tn_comments_total\tstatus\tdescription"
)

_COLUMNS = LEADERBOARD_HEADER.split("\t")


def append_row(
    path: Path | str,
    *,
    commit_sha: str,
    recipe_hash: str,
    utility: float | None = None,
    detection_rate: float | None = None,
    precision_minor: float | None = None,
    precision_important: float | None = None,
    precision_critical: float | None = None,
    cost_usd: float | None = None,
    n_comments_total: int | None = None,
    status: str,
    description: str,
) -> None:
    """Atomically append one row to the leaderboard TSV.

    Writes the header iff the file does not exist. Cells are coerced via
    `_format_cell` so None becomes the literal "n/a" — never an empty cell
    (empty cells break naive TSV parsers).
    """
    path = Path(path)
    fields: dict[str, object] = {
        "commit_sha": commit_sha,
        "recipe_hash": recipe_hash,
        "utility": utility,
        "detection_rate": detection_rate,
        "precision_minor": precision_minor,
        "precision_important": precision_important,
        "precision_critical": precision_critical,
        "cost_usd": cost_usd,
        "n_comments_total": n_comments_total,
        "status": status,
        "description": description,
    }
    row = "\t".join(_format_cell(fields[col]) for col in _COLUMNS)

    existing = path.read_text() if path.exists() else ""
    if not existing:
        new_text = LEADERBOARD_HEADER + "\n" + row + "\n"
    else:
        # Ensure existing ends with a newline so the new row doesn't smash
        # into the last data line.
        if not existing.endswith("\n"):
            existing = existing + "\n"
        new_text = existing + row + "\n"

    # Atomic write: tmp + os.replace.
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    os.close(fd)
    Path(tmp_path).write_text(new_text)
    os.replace(tmp_path, path)


def _format_cell(value: object) -> str:
    """TSV-safe cell rendering. Tabs/newlines in strings are replaced with
    a single space; None becomes "n/a"; floats render with up to 6
    decimal digits without trailing zeros."""
    if value is None:
        return "n/a"
    if isinstance(value, float):
        s = f"{value:.6f}".rstrip("0").rstrip(".")
        return s or "0"
    if isinstance(value, int):
        return str(value)
    # str / anything else
    s = str(value).replace("\t", " ").replace("\n", " ").replace("\r", " ")
    return s
