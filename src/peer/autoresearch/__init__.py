"""peer.autoresearch — autonomous recipe experimentation loop.

See `program.md` at the repo root for the agent-facing protocol. This
subpackage ships the leaderboard appender, the safe utility-formula
parser, and the CLI implementations behind `peer autoresearch run/loop`.
"""

from .leaderboard import LEADERBOARD_HEADER, append_row
from .runner import run_one_iteration
from .utility import UnsafeUtilityFormula, default_utility, parse_utility_formula

__all__ = [
    "LEADERBOARD_HEADER",
    "UnsafeUtilityFormula",
    "append_row",
    "default_utility",
    "parse_utility_formula",
    "run_one_iteration",
]
