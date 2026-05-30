"""Unit tests for the GitHubAppReviewer adapter (peer-ya3).

Stubs subprocess.run so no network. Covers PR-url parsing, bot filtering,
line-anchoring, paginated-JSON parsing, the EvalRunner seam, and fail-loud.
"""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

import pytest

from peer.dataset.types import GoldSample
from peer.eval.metrics import CommentsPerPR
from peer.eval.runner import EvalRunner
from peer.external_reviewers import (
    ExternalReviewerError,
    GitHubAppReviewer,
    _parse_paginated_json,
    _parse_pr_url,
    coderabbit,
    greptile,
    qodo_merge,
)

_PR = "https://github.com/o/r/pull/7"


def _completed(stdout="", returncode=0, stderr=""):
    return subprocess.CompletedProcess(
        args=["gh"], returncode=returncode, stdout=stdout, stderr=stderr
    )


def _payload(*comments):
    return json.dumps(list(comments))


def _c(login, path, line, body="issue"):
    return {"user": {"login": login}, "path": path, "line": line, "body": body}


def test_parse_pr_url_ok():
    assert _parse_pr_url("https://github.com/django/django/pull/123") == ("django", "django", 123)


def test_parse_pr_url_rejects_garbage():
    with pytest.raises(ExternalReviewerError):
        _parse_pr_url("not a url")


def test_filters_to_bot_author():
    stdout = _payload(
        _c("coderabbitai[bot]", "a.py", 10),
        _c("human-dev", "a.py", 11),
        _c("coderabbitai[bot]", "b.py", 20),
    )
    r = GitHubAppReviewer(bot_login="coderabbitai[bot]")
    with patch("peer.external_reviewers.subprocess.run", return_value=_completed(stdout)):
        review = r.review(_PR)
    assert len(review.comments) == 2
    assert {c.path for c in review.comments} == {"a.py", "b.py"}


def test_bot_match_is_case_insensitive():
    stdout = _payload(_c("CodeRabbitAI[bot]", "a.py", 1))
    r = GitHubAppReviewer(bot_login="coderabbitai[bot]")
    with patch("peer.external_reviewers.subprocess.run", return_value=_completed(stdout)):
        review = r.review(_PR)
    assert len(review.comments) == 1


def test_skips_non_line_anchored_and_empty_body():
    stdout = _payload(
        _c("bot[bot]", "a.py", None, body="file-level"),  # no line -> kept only if original_line
        {"user": {"login": "bot[bot]"}, "path": None, "line": 5, "body": "no path"},
        _c("bot[bot]", "a.py", 9, body="   "),  # empty body
        _c("bot[bot]", "a.py", 12, body="real"),
    )
    r = GitHubAppReviewer(bot_login="bot[bot]")
    with patch("peer.external_reviewers.subprocess.run", return_value=_completed(stdout)):
        review = r.review(_PR)
    # Only the path+line+body comment survives. The None-line one has no
    # original_line fallback so its line is None but path+body present -> kept
    # with line=None. So expect 2 (the None-line file note + the real one).
    bodies = sorted(c.body for c in review.comments)
    assert bodies == ["file-level", "real"]


def test_original_line_fallback():
    stdout = _payload(
        {
            "user": {"login": "bot[bot]"},
            "path": "a.py",
            "line": None,
            "original_line": 42,
            "body": "x",
        }
    )
    r = GitHubAppReviewer(bot_login="bot[bot]")
    with patch("peer.external_reviewers.subprocess.run", return_value=_completed(stdout)):
        review = r.review(_PR)
    assert review.comments[0].line == 42


def test_empty_review_when_bot_silent():
    stdout = _payload(_c("human", "a.py", 1))
    r = GitHubAppReviewer(bot_login="greptileai[bot]")
    with patch("peer.external_reviewers.subprocess.run", return_value=_completed(stdout)):
        review = r.review(_PR)
    assert review.comments == []
    assert review.reason is not None


def test_persistent_gh_failure_raises_after_retries():
    r = GitHubAppReviewer(bot_login="bot[bot]", gh_max_attempts=3, gh_backoff_seconds=0.0)
    with (
        patch(
            "peer.external_reviewers.subprocess.run",
            return_value=_completed(returncode=1, stderr="rate limited"),
        ) as mock_run,
        pytest.raises(ExternalReviewerError, match="failed 3x"),
    ):
        r.review(_PR)
    assert mock_run.call_count == 3


def test_unparseable_json_raises():
    r = GitHubAppReviewer(bot_login="bot[bot]", gh_max_attempts=1)
    with (
        patch("peer.external_reviewers.subprocess.run", return_value=_completed("{not json")),
        pytest.raises(ExternalReviewerError, match="unparseable"),
    ):
        r.review(_PR)


def test_parse_paginated_json_single_array():
    assert _parse_paginated_json('[{"a": 1}, {"a": 2}]') == [{"a": 1}, {"a": 2}]


def test_parse_paginated_json_concatenated_pages():
    # gh --paginate can emit one array per page, concatenated.
    out = _parse_paginated_json('[{"a": 1}]\n[{"a": 2}, {"a": 3}]')
    assert out == [{"a": 1}, {"a": 2}, {"a": 3}]


def test_parse_paginated_json_empty():
    assert _parse_paginated_json("   ") == []


def test_convenience_constructors_set_model():
    assert coderabbit().model == "external:coderabbit"
    assert greptile().model == "external:greptile"
    assert qodo_merge().model == "external:qodo"


def test_convenience_constructors_use_verified_bot_logins():
    # Logins verified against real PRs in Phase 2 (peer-2sw, 2026-05-30).
    # Regression guard: greptile is greptile-apps[bot] (NOT greptileai[bot]),
    # qodo free tier is codiumai-pr-agent-free[bot] (NOT qodo-merge-pro[bot]).
    assert coderabbit().bot_login == "coderabbitai[bot]"
    assert greptile().bot_login == "greptile-apps[bot]"
    assert qodo_merge().bot_login == "codiumai-pr-agent-free[bot]"


def test_rejects_zero_max_attempts():
    with pytest.raises(ValueError, match="gh_max_attempts"):
        GitHubAppReviewer(bot_login="bot[bot]", gh_max_attempts=0)


def test_flows_through_evalrunner():
    """The whole point of Phase 0: an external reviewer drops into EvalRunner
    exactly like peer/bare-Claude, scored by the existing metrics."""
    sample = GoldSample(pr_url=_PR, pr_title="t")
    stdout = _payload(
        _c("coderabbitai[bot]", "a.py", 10, "bug one"),
        _c("coderabbitai[bot]", "a.py", 20, "bug two"),
    )
    reviewer = coderabbit()
    with patch("peer.external_reviewers.subprocess.run", return_value=_completed(stdout)):
        runner = EvalRunner(reviewer=reviewer, dataset=[sample], metrics=[CommentsPerPR()])
        report = runner.run()
    assert report.summary.metric_values["comments_per_pr"] == 2.0
    assert report.summary.n_samples_succeeded == 1


# --------------------------------------------------------------------------
# Issue-level summary extraction (peer-bno)
# --------------------------------------------------------------------------

from pathlib import Path  # noqa: E402

from peer.external_reviewers import (  # noqa: E402
    ExtractedFinding,
    _haiku_summary_extractor,
    _parse_findings_json,
    _strip_summary_noise,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "external_summaries"


def _issue(login, body):
    return {"user": {"login": login}, "body": body}


def test_strip_summary_noise_removes_html_comments_and_base64():
    raw = _FIXTURES.joinpath("coderabbit_with_findings.md").read_text()
    cleaned = _strip_summary_noise(raw)
    # The giant base64 internal-state blob lives inside an HTML comment.
    assert "<!--" not in cleaned
    assert "internal state" not in cleaned
    # Real prose survives.
    assert "Walkthrough" in cleaned


def test_parse_findings_json_plain_array():
    out = _parse_findings_json('[{"path": "a.py", "line": 5, "finding": "bug"}]')
    assert out == [ExtractedFinding(path="a.py", line=5, finding="bug")]


def test_parse_findings_json_tolerates_fence_and_prose():
    text = 'Here you go:\n```json\n[{"path":"b.py","line":null,"finding":"x"}]\n```\nDone.'
    out = _parse_findings_json(text)
    assert out == [ExtractedFinding(path="b.py", line=None, finding="x")]


def test_parse_findings_json_garbage_returns_empty():
    assert _parse_findings_json("not json at all") == []
    assert _parse_findings_json("") == []
    assert _parse_findings_json("{not an array}") == []


def test_parse_findings_json_skips_malformed_items():
    text = '[{"path":"a.py","line":1,"finding":"ok"},{"no_path":true},{"path":""}]'
    out = _parse_findings_json(text)
    assert out == [ExtractedFinding(path="a.py", line=1, finding="ok")]


def test_default_does_not_fetch_summary():
    # include_issue_summary defaults False → only the inline endpoint is hit.
    inline = _payload(_c("coderabbitai[bot]", "a.py", 10))
    with patch("peer.external_reviewers.subprocess.run", return_value=_completed(inline)) as run:
        review = GitHubAppReviewer(bot_login="coderabbitai[bot]").review(_PR)
    assert len(review.comments) == 1
    # exactly one gh call: the inline fetch, no issues/comments fetch
    assert run.call_count == 1


def test_summary_findings_merge_with_inline():
    inline = _payload(_c("bot[bot]", "a.py", 10, "inline bug"))
    summary = _payload(_issue("bot[bot]", "summary body"))

    def stub_extractor(_md):
        return [ExtractedFinding(path="b.py", line=20, finding="summary bug")]

    r = GitHubAppReviewer(
        bot_login="bot[bot]",
        include_issue_summary=True,
        summary_extractor=stub_extractor,
    )
    with patch(
        "peer.external_reviewers.subprocess.run",
        side_effect=[_completed(inline), _completed(summary)],
    ):
        review = r.review(_PR)
    paths = sorted(c.path for c in review.comments)
    assert paths == ["a.py", "b.py"]
    summary_c = next(c for c in review.comments if c.path == "b.py")
    assert summary_c.line == 20
    assert "summary" in summary_c.rationale


def test_summary_dedups_against_inline():
    # A summary finding at the same (path, line) as an inline comment is dropped.
    inline = _payload(_c("bot[bot]", "a.py", 10, "inline bug"))
    summary = _payload(_issue("bot[bot]", "summary body"))

    def stub_extractor(_md):
        return [ExtractedFinding(path="a.py", line=10, finding="same bug, restated")]

    r = GitHubAppReviewer(
        bot_login="bot[bot]",
        include_issue_summary=True,
        summary_extractor=stub_extractor,
    )
    with patch(
        "peer.external_reviewers.subprocess.run",
        side_effect=[_completed(inline), _completed(summary)],
    ):
        review = r.review(_PR)
    assert len(review.comments) == 1  # the duplicate was not double-counted


class _StubBlock:
    def __init__(self, text):
        self.text = text


class _StubResp:
    def __init__(self, text):
        self.content = [_StubBlock(text)]


class _StubMessages:
    def __init__(self, text, calls):
        self._text = text
        self._calls = calls

    def create(self, **_kwargs):
        self._calls.append(1)
        return _StubResp(self._text)


class _StubClient:
    def __init__(self, text, calls=None):
        self.messages = _StubMessages(text, calls if calls is not None else [])


def test_haiku_extractor_empty_summary_skips_llm():
    # A ratelimited summary that strips to nothing must NOT call the client.
    calls = []
    # "<!-- only a comment -->" strips to "" → early return [] before any call.
    out = _haiku_summary_extractor("<!-- only a comment -->", client=_StubClient("ignored", calls))
    assert out == []
    assert calls == []  # client.messages.create never invoked


def test_haiku_extractor_parses_stub_client_reply():
    client = _StubClient('[{"path":"x.py","line":3,"finding":"leak"}]')
    out = _haiku_summary_extractor("real findings here", client=client)
    assert out == [ExtractedFinding(path="x.py", line=3, finding="leak")]
