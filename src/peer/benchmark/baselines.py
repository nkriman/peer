"""Published-baseline numbers for the Macroscope 118-bug benchmark.

Sourced from docs/competitive_landscape_research.md (commit research date
2026-05-23). Each entry includes the detection_rate, comments_per_pr,
methodology footnote, and a source URL.

These numbers DRIFT. Per benchmark-v01 design.md Decision 5 + adversarial-
review item 2.10: document the drift policy; users running benchmark in
CI should pin to a peer version that matches their baseline expectations.
"""

from __future__ import annotations

from typing import Any

PUBLISHED_BASELINES: dict[str, dict[str, Any]] = {
    "macroscope": {
        "detection_rate": 0.483,  # 57/118
        "comments_per_pr": 2.55,
        "precision": 0.98,
        "source": "https://macroscope.com/content/best-ai-code-review-tools-github-2026",
        "as_of": "2026-05-23",
        "notes": "Macroscope's own benchmark, full 118-bug coverage.",
    },
    "coderabbit": {
        "detection_rate": 0.458,  # 54/118
        "comments_per_pr": 10.84,
        "comments_per_pr_runtime_relevant": 4.69,
        "source": "https://macroscope.com/content/best-ai-code-review-tools-github-2026",
        "as_of": "2026-05-23",
        "notes": "High comment volume; only ~4.7 of 10.84 are runtime-relevant.",
    },
    "cursor_bugbot": {
        "detection_rate": 0.424,  # 50/118
        "comments_per_pr": 0.91,
        "precision": 0.70,
        "source": "https://macroscope.com/content/best-ai-code-review-tools-github-2026",
        "as_of": "2026-05-23",
        "notes": "Low volume / high precision. Bundled with Cursor IDE.",
    },
    "greptile": {
        "detection_rate": 0.236,  # 17/72 — tested on partial dataset
        "comments_per_pr": 3.08,
        "tested_on": "72/118 bugs (access revoked mid-evaluation)",
        "source": "https://macroscope.com/content/best-ai-code-review-tools-github-2026",
        "as_of": "2026-05-23",
        "notes": "Tested on incomplete subset; independent dev.to study reported 0% FPR on 120 findings.",
    },
    "graphite_diamond": {
        "detection_rate": 0.183,  # 21/115
        "comments_per_pr": 0.62,
        "precision_negative_feedback": 0.03,  # <3% unhelpful
        "source": "https://macroscope.com/content/best-ai-code-review-tools-github-2026",
        "as_of": "2026-05-23",
        "notes": "Most conservative / lowest volume tool in the benchmark.",
    },
}


__all__ = ["PUBLISHED_BASELINES"]
