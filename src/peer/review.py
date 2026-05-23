"""CLI smoke-test entry point: `python -m peer.review <pr_url>`."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .agent import Agent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="peer.review",
        description="Run peer on a single GitHub PR.",
    )
    parser.add_argument("pr_url", help="GitHub PR URL")
    parser.add_argument(
        "--model", default="claude-opus-4-7", help="Model id (default: claude-opus-4-7)"
    )
    parser.add_argument(
        "--system-prompt-file",
        type=Path,
        default=None,
        help="Path to a custom system prompt (overrides the default)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Verbose logging"
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    agent = Agent(model=args.model, system_prompt_file=args.system_prompt_file)
    review = agent.review(args.pr_url)

    print(f"\n=== Review for {args.pr_url} ===")
    print(
        f"Model: {review.usage.get('model')}  |  "
        f"in={review.usage.get('input_tokens')}  out={review.usage.get('output_tokens')}"
    )

    if not review.comments:
        print(f"\nNo comments. Reason: {review.reason or 'n/a'}")
        return 0

    counts: dict[str, int] = {}
    for c in review.comments:
        counts[c.severity] = counts.get(c.severity, 0) + 1
    summary = ", ".join(f"{k}={v}" for k, v in counts.items())
    print(f"\n{len(review.comments)} comment(s)  ({summary})")

    for severity in ("critical", "important", "minor", "nit"):
        for c in review.comments:
            if c.severity != severity:
                continue
            line = f":{c.line}" if c.line is not None else ""
            print(f"\n[{c.severity.upper()}] {c.path}{line}")
            print(f"  {c.body}")
            print(f"  -- {c.rationale}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
