"""Legacy entry point: `python -m peer.review <pr_url>`.

Forwards to `peer review` (the unified CLI's subcommand) so existing
scripts keep working. New code should use `peer review` or
`python -m peer review`.
"""

from __future__ import annotations

import sys

from .cli import main as cli_main


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    return cli_main(["review", *argv])


if __name__ == "__main__":
    sys.exit(main())
