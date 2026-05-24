"""peer.benchmark — bug-benchmark capability (schemas + published baselines).

Per benchmark-v01: core schemas land here. The MacroscopeLoader,
BugBenchmarkRunner, and `peer benchmark` CLI subcommand are deferred
follow-ups (see openspec/changes/benchmark-v01/tasks.md).
"""

from .baselines import PUBLISHED_BASELINES
from .types import (
    BenchmarkReport,
    BugBenchmarkResult,
    BugLocation,
    BugSample,
    LineCoordinateSystem,
)

__all__ = [
    "PUBLISHED_BASELINES",
    "BenchmarkReport",
    "BugBenchmarkResult",
    "BugLocation",
    "BugSample",
    "LineCoordinateSystem",
]
