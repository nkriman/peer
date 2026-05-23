"""Configurable Taxonomy with the framework's "good enough" default.

Per design.md Decision 4: 8 categories × 4 severities. `discussion` is
dropped; `style-nit` is kept but forced to nit severity. The other six
categories are kept as defects with classifier-assigned severity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..types import Severity
from .types import CategoryDef


@dataclass
class Taxonomy:
    """Configurable classification + severity scheme."""
    categories: list[CategoryDef]
    severities: list[Severity]
    drop_categories: list[str]
    nit_only_categories: list[str]
    version: str

    def get(self, name: str) -> Optional[CategoryDef]:
        for c in self.categories:
            if c.name == name:
                return c
        return None

    def is_kept(self, category_name: str) -> bool:
        """Whether comments in this category survive into GoldSample."""
        return category_name not in self.drop_categories

    def force_severity_for(self, category_name: str) -> Optional[Severity]:
        """If this category overrides the classifier's severity, return that severity."""
        if category_name in self.nit_only_categories:
            return "nit"
        cat = self.get(category_name)
        if cat is not None and cat.force_severity is not None:
            return cat.force_severity
        return None

    def category_names(self) -> list[str]:
        return [c.name for c in self.categories]


_DEFAULT_CATEGORIES: list[CategoryDef] = [
    CategoryDef(
        name="defect-correctness",
        description="Bug, logic error, broken behaviour, regression risk, off-by-one, "
        "null/None dereference, race condition, incorrect handling of edge cases.",
        is_defect=True,
    ),
    CategoryDef(
        name="defect-security",
        description="Security or privacy concern: injection, auth bypass, secret leak, "
        "unsafe deserialization, missing input validation that creates a vulnerability.",
        is_defect=True,
    ),
    CategoryDef(
        name="defect-performance",
        description="Performance concern with a concrete cost case: unnecessary work in "
        "a hot path, N+1 query, redundant allocation, missing index, blocking I/O on the "
        "wrong thread.",
        is_defect=True,
    ),
    CategoryDef(
        name="defect-api-design",
        description="Wrong abstraction layer, breaking API change, leaky abstraction, "
        "confusing naming that will mislead callers, mutable default arg.",
        is_defect=True,
    ),
    CategoryDef(
        name="defect-test-gap",
        description="The change is untested, lacks coverage for an important branch, "
        "or breaks/disables existing tests without justification.",
        is_defect=True,
    ),
    CategoryDef(
        name="defect-doc-gap",
        description="The change needs documentation it doesn't have: missing docstring "
        "on a new public API, missing changelog entry, outdated docs that the change "
        "now contradicts.",
        is_defect=True,
    ),
    CategoryDef(
        name="style-nit",
        description="Pure formatting, naming preference, import ordering, line-length, "
        "trailing commas — anything a linter could catch.",
        is_defect=False,
        force_severity="nit",
    ),
    CategoryDef(
        name="discussion",
        description="Implementation Q&A from author, reviewer suggesting how-to, "
        "clarification chatter, 'looks good', 'please review', approval, praise, "
        "off-topic. NOT a defect; dropped from gold.",
        is_defect=False,
    ),
]


DefaultTaxonomy = Taxonomy(
    categories=_DEFAULT_CATEGORIES,
    severities=["critical", "important", "minor", "nit"],
    drop_categories=["discussion"],
    nit_only_categories=["style-nit"],
    version="default-v1",
)
