"""Pluggable Reviewer backends. Slice 1 ships ClaudeReviewer only.

OpenAIReviewer lands in Slice 3 alongside the eval scaffolding.
"""

from __future__ import annotations

from typing import Optional, Protocol

import anthropic

from .prompts import DEFAULT_SYSTEM_PROMPT, format_prompt
from .types import CodebaseContext, Comment, Context

_COMMENT_TOOL = {
    "name": "post_review_comments",
    "description": (
        "Post the list of inline review comments for this PR. "
        "Pass an empty list if the PR has no issues worth flagging."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "comments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "line": {"type": ["integer", "null"]},
                        "severity": {
                            "type": "string",
                            "enum": ["critical", "important", "minor", "nit"],
                        },
                        "body": {"type": "string"},
                        "rationale": {"type": "string"},
                    },
                    "required": ["path", "severity", "body", "rationale"],
                },
            },
        },
        "required": ["comments"],
    },
}


class Reviewer(Protocol):
    def review(
        self,
        context: Context,
        codebase_context: Optional[CodebaseContext] = None,
    ) -> tuple[list[Comment], dict]: ...


class ClaudeReviewer:
    def __init__(
        self, model: str, system_prompt: str = DEFAULT_SYSTEM_PROMPT
    ) -> None:
        self.model = model
        self.system_prompt = system_prompt
        self.client = anthropic.Anthropic()

    def review(
        self,
        context: Context,
        codebase_context: Optional[CodebaseContext] = None,
    ) -> tuple[list[Comment], dict]:
        user_msg = format_prompt(context, codebase_context)
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=8192,
            system=self.system_prompt,
            tools=[_COMMENT_TOOL],
            tool_choice={"type": "tool", "name": "post_review_comments"},
            messages=[{"role": "user", "content": user_msg}],
        )
        comments: list[Comment] = []
        for block in resp.content:
            if getattr(block, "type", None) != "tool_use":
                continue
            if getattr(block, "name", None) != "post_review_comments":
                continue
            for raw in block.input.get("comments", []):
                comments.append(Comment(**raw))
        usage = {
            "input_tokens": resp.usage.input_tokens,
            "output_tokens": resp.usage.output_tokens,
            "model": self.model,
        }
        return comments, usage
