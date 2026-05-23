"""Tests for peer.dataset.taxonomy."""

from __future__ import annotations

import pytest

from peer.dataset.taxonomy import DefaultTaxonomy, Taxonomy
from peer.dataset.types import CategoryDef


def test_default_taxonomy_has_expected_categories():
    names = DefaultTaxonomy.category_names()
    assert "defect-correctness" in names
    assert "defect-security" in names
    assert "style-nit" in names
    assert "discussion" in names
    # 8 categories per design
    assert len(names) == 8


def test_default_taxonomy_severities_order():
    assert DefaultTaxonomy.severities == ["critical", "important", "minor", "nit"]


def test_default_taxonomy_drops_discussion_only():
    assert DefaultTaxonomy.is_kept("discussion") is False
    assert DefaultTaxonomy.is_kept("defect-correctness") is True
    assert DefaultTaxonomy.is_kept("style-nit") is True


def test_default_taxonomy_forces_style_nit_to_nit():
    assert DefaultTaxonomy.force_severity_for("style-nit") == "nit"


def test_default_taxonomy_force_severity_for_normal_category_returns_none():
    assert DefaultTaxonomy.force_severity_for("defect-correctness") is None


def test_default_taxonomy_force_severity_for_unknown_returns_none():
    assert DefaultTaxonomy.force_severity_for("does-not-exist") is None


def test_get_returns_category_def():
    cat = DefaultTaxonomy.get("defect-correctness")
    assert cat is not None
    assert cat.is_defect is True
    assert cat.force_severity is None


def test_get_returns_none_for_unknown():
    assert DefaultTaxonomy.get("nonexistent") is None


def test_custom_taxonomy_drop_and_force():
    custom = Taxonomy(
        categories=[
            CategoryDef(name="bug", description="a bug", is_defect=True),
            CategoryDef(name="chat", description="chatter", is_defect=False),
            CategoryDef(
                name="docs",
                description="docs",
                is_defect=False,
                force_severity="minor",
            ),
        ],
        severities=["critical", "important", "minor", "nit"],
        drop_categories=["chat"],
        nit_only_categories=[],
        version="custom-v1",
    )
    assert custom.is_kept("bug") is True
    assert custom.is_kept("chat") is False
    assert custom.force_severity_for("docs") == "minor"
    assert custom.force_severity_for("bug") is None
    assert custom.version == "custom-v1"


def test_custom_nit_only_overrides_force_severity():
    # nit_only_categories should win over a CategoryDef.force_severity
    custom = Taxonomy(
        categories=[
            CategoryDef(
                name="style",
                description="style",
                is_defect=False,
                force_severity="minor",
            ),
        ],
        severities=["critical", "important", "minor", "nit"],
        drop_categories=[],
        nit_only_categories=["style"],
        version="v1",
    )
    assert custom.force_severity_for("style") == "nit"
