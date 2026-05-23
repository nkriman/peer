"""Tests for peer.dataset.curation.Curator."""

from __future__ import annotations

import pytest

from peer.dataset.curation import Curator
from peer.dataset.enrichment import NoEnrichment
from peer.dataset.taxonomy import DefaultTaxonomy
from peer.dataset.types import (
    Classification,
    RawComment,
    RawSample,
)
from peer.exceptions import CurationRejected


class FakeSource:
    def __init__(self, sample):
        self.sample = sample
        self.calls: list[str] = []

    def fetch(self, pr_url):
        self.calls.append(pr_url)
        return self.sample


class FakeClassifier:
    def __init__(self, decisions):
        self.decisions = decisions
        self.calls: list[str] = []

    def classify(self, comment, pr_context):
        self.calls.append(comment.source_id)
        if comment.source_id in self.decisions:
            return self.decisions[comment.source_id]
        raise ValueError(f"no fake decision for {comment.source_id}")


class FakeStorage:
    def __init__(self):
        self.samples = []

    def add(self, sample):
        for i, s in enumerate(self.samples):
            if s.pr_url == sample.pr_url:
                self.samples[i] = sample
                return
        self.samples.append(sample)

    def load_all(self):
        return list(self.samples)

    def find(self, pr_url):
        for s in self.samples:
            if s.pr_url == pr_url:
                return s
        return None

    def delete(self, pr_url):
        self.samples = [s for s in self.samples if s.pr_url != pr_url]


@pytest.fixture
def fake_source(raw_sample):
    return FakeSource(raw_sample)


@pytest.fixture
def fake_classifier(raw_comment, classification_correctness):
    return FakeClassifier({raw_comment.source_id: classification_correctness})


@pytest.fixture
def fake_storage():
    return FakeStorage()


def _curator(source, classifier, storage=None):
    return Curator(
        storage=storage,
        source=source,
        classifier=classifier,
        enrichment=NoEnrichment(),
        taxonomy=DefaultTaxonomy,
    )


def test_preview_without_storage_works(fake_source, fake_classifier):
    curator = _curator(fake_source, fake_classifier, storage=None)
    proposed = curator.preview("https://github.com/o/r/pull/1")
    assert proposed.proposed.pr_url == "https://github.com/o/r/pull/1"
    assert len(proposed.proposed.gold_defects) == 1
    assert proposed.proposed.gold_defects[0].category == "defect-correctness"


def test_preview_dropped_categories_recorded(raw_sample):
    # Classify the single comment as 'discussion' which is dropped
    cls = Classification(
        category="discussion",
        severity="minor",
        reasoning="just chatting about the implementation",
    )
    source = FakeSource(raw_sample)
    classifier = FakeClassifier({raw_sample.comments[0].source_id: cls})
    curator = _curator(source, classifier)
    proposed = curator.preview("https://github.com/o/r/pull/1")
    assert proposed.proposed.gold_defects == []
    assert "discussion" in proposed.dropped_categories


def test_preview_drops_inline_comment_without_path(pr_context):
    rc = RawComment(
        source_id="github:issues/comments/9",
        author="bob",
        path=None,
        line=None,
        body="general comment",
        kind="issue_comment",
    )
    raw = RawSample(
        pr_url="https://github.com/o/r/pull/3",
        pr_title="x",
        pr_body="",
        head_sha="x",
        comments=[rc],
    )
    source = FakeSource(raw)
    classifier = FakeClassifier(
        {
            rc.source_id: Classification(
                category="defect-correctness",
                severity="important",
                reasoning="something about correctness in general",
            )
        }
    )
    curator = _curator(source, classifier)
    proposed = curator.preview(raw.pr_url)
    # path-less comments can't anchor — dropped
    assert proposed.proposed.gold_defects == []


def test_preview_forces_style_nit_severity(raw_sample):
    cls = Classification(
        category="style-nit",
        severity="critical",  # classifier said critical
        reasoning="trailing whitespace on line 10",
    )
    source = FakeSource(raw_sample)
    classifier = FakeClassifier({raw_sample.comments[0].source_id: cls})
    curator = _curator(source, classifier)
    proposed = curator.preview(raw_sample.pr_url)
    assert len(proposed.proposed.gold_defects) == 1
    # taxonomy forces nit regardless of classifier severity
    assert proposed.proposed.gold_defects[0].severity == "nit"


def test_add_requires_storage(fake_source, fake_classifier):
    curator = _curator(fake_source, fake_classifier, storage=None)
    with pytest.raises(ValueError, match="storage"):
        curator.add("https://github.com/o/r/pull/1", auto_accept=True)


def test_add_auto_accept_writes_to_storage(
    fake_source, fake_classifier, fake_storage
):
    curator = _curator(fake_source, fake_classifier, storage=fake_storage)
    sample = curator.add("https://github.com/o/r/pull/1", auto_accept=True)
    assert sample.pr_url == "https://github.com/o/r/pull/1"
    assert len(fake_storage.samples) == 1
    assert fake_storage.samples[0].pr_url == sample.pr_url


def test_add_interactive_accept(fake_source, fake_classifier, fake_storage, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *_a, **_kw: "a")
    curator = _curator(fake_source, fake_classifier, storage=fake_storage)
    sample = curator.add("https://github.com/o/r/pull/1", auto_accept=False)
    assert len(fake_storage.samples) == 1
    # Interactive accept must mark spot_checked
    assert sample.metadata.spot_checked is True


def test_add_interactive_reject_raises_curation_rejected(
    fake_source, fake_classifier, fake_storage, monkeypatch
):
    monkeypatch.setattr("builtins.input", lambda *_a, **_kw: "r")
    curator = _curator(fake_source, fake_classifier, storage=fake_storage)
    with pytest.raises(CurationRejected):
        curator.add("https://github.com/o/r/pull/1", auto_accept=False)
    assert fake_storage.samples == []


def test_classifier_failure_does_not_abort_other_comments():
    # Two comments — first one raises during classification, second succeeds.
    rc1 = RawComment(
        source_id="c1", author="alice", path="a.py", line=1, body="bad"
    )
    rc2 = RawComment(
        source_id="c2", author="bob", path="b.py", line=2, body="also bad"
    )
    raw = RawSample(
        pr_url="https://github.com/o/r/pull/9",
        pr_title="t",
        pr_body="",
        head_sha="x",
        comments=[rc1, rc2],
    )
    decisions = {
        "c2": Classification(
            category="defect-correctness",
            severity="important",
            reasoning="long enough reasoning string",
        )
    }  # c1 missing -> FakeClassifier raises
    source = FakeSource(raw)
    classifier = FakeClassifier(decisions)
    curator = _curator(source, classifier)
    proposed = curator.preview(raw.pr_url)
    # one comment survived
    assert len(proposed.proposed.gold_defects) == 1
    assert proposed.proposed.gold_defects[0].path == "b.py"


def test_add_batch_continues_past_rejection(
    fake_source, fake_classifier, fake_storage, monkeypatch
):
    # auto_accept path => no input prompts, all should succeed
    curator = _curator(fake_source, fake_classifier, storage=fake_storage)
    out = curator.add_batch(
        ["https://github.com/o/r/pull/1", "https://github.com/o/r/pull/1"],
        auto_accept=True,
    )
    # FakeSource always returns same sample, so storage has 1 (overwritten)
    assert len(out) == 2


def test_preview_metadata_records_taxonomy_version(
    fake_source, fake_classifier
):
    curator = _curator(fake_source, fake_classifier)
    proposed = curator.preview("https://github.com/o/r/pull/1")
    assert proposed.proposed.metadata.taxonomy_version == "default-v1"
    assert proposed.proposed.metadata.curation_source == "default_pipeline"


def test_review_depth_buckets(raw_sample, fake_classifier):
    # raw_sample fixture has 1 comment => "light"
    source = FakeSource(raw_sample)
    curator = _curator(source, fake_classifier)
    proposed = curator.preview(raw_sample.pr_url)
    assert proposed.proposed.metadata.review_depth == "light"
