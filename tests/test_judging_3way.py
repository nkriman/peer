"""Tests for the 3-way CR-Bench-style comment classifier (peer-ivb).

Stubs the anthropic client so no API calls. Verifies the parser maps
HIT/VALID/NOISE responses to the right enum and that any unexpected
response defaults to 'noise' (conservative).
"""

from __future__ import annotations

from dataclasses import dataclass

from peer.dataset.types import GoldDefect
from peer.eval.judging import classify_comment
from peer.types import Comment


@dataclass
class _Block:
    text: str


@dataclass
class _Resp:
    content: list[_Block]


class _StubClient:
    """Returns the same scripted response for every messages.create call."""

    def __init__(self, response_text: str) -> None:
        self.calls: list[dict] = []
        self.response_text = response_text

        outer = self

        class _Messages:
            def create(self, **kwargs):  # type: ignore[no-untyped-def]
                outer.calls.append(kwargs)
                return _Resp(content=[_Block(text=outer.response_text)])

        self.messages = _Messages()


def _comment() -> Comment:
    return Comment(path="a.py", line=10, severity="minor", body="b", rationale="r")


def _gold() -> list[GoldDefect]:
    return [
        GoldDefect(
            path="a.py",
            line=10,
            category="defect-correctness",
            severity="important",
            description="off-by-one in range bound",
            source="human_reviewer:x",
        )
    ]


def test_classify_comment_hit() -> None:
    client = _StubClient("HIT")
    cls = classify_comment(_comment(), _gold(), client=client)
    assert cls == "hit"
    assert len(client.calls) == 1


def test_classify_comment_valid() -> None:
    client = _StubClient("VALID")
    cls = classify_comment(_comment(), _gold(), client=client)
    assert cls == "valid"


def test_classify_comment_noise() -> None:
    client = _StubClient("NOISE")
    cls = classify_comment(_comment(), _gold(), client=client)
    assert cls == "noise"


def test_classify_comment_unparseable_defaults_to_noise() -> None:
    """Anything we can't parse is conservatively classified as noise — keeps
    SNR honest by never letting a hallucinated response inflate signal."""
    client = _StubClient("I'm not sure, maybe HIT or maybe not.")
    cls = classify_comment(_comment(), _gold(), client=client)
    # The string starts with 'I' so neither HIT nor VALID prefix matches.
    assert cls == "noise"


def test_classify_comment_no_gold_defects_still_callable() -> None:
    """With zero gold defects, hit is impossible — but valid/noise still
    distinguishes useful from hallucinated comments."""
    client = _StubClient("VALID")
    cls = classify_comment(_comment(), [], client=client)
    assert cls == "valid"
    # Prompt should still have been constructed without crashing.
    msg = client.calls[0]["messages"][0]["content"]
    assert "no labeled defects" in msg
