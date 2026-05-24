"""peer.benchmark — bug-benchmark capability.

Schemas, published baselines, MacroscopeLoader, judge, runner.
The `peer benchmark` CLI subcommand lives in src/peer/cli.py.
"""

from .baselines import PUBLISHED_BASELINES
from .judge import DEFAULT_JUDGE_MODEL, DEFAULT_PROXIMITY_LINES, judge_bug_caught
from .loader import BugDatasetSource, MacroscopeLoader
from .runner import BugBenchmarkRunner
from .types import (
    BenchmarkReport,
    BugBenchmarkResult,
    BugLocation,
    BugSample,
    LineCoordinateSystem,
)

__all__ = [
    "DEFAULT_JUDGE_MODEL",
    "DEFAULT_PROXIMITY_LINES",
    "PUBLISHED_BASELINES",
    "BenchmarkReport",
    "BugBenchmarkResult",
    "BugBenchmarkRunner",
    "BugDatasetSource",
    "BugLocation",
    "BugSample",
    "LineCoordinateSystem",
    "MacroscopeLoader",
    "judge_bug_caught",
]
