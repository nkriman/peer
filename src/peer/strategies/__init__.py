"""peer.strategies — composable Reviewer-Protocol primitives.

Each strategy is a stand-alone Reviewer that wraps inner Reviewer(s),
introducing an orchestrational concern: multi-pass critique, two-model
pipelining, post-filtering. Recipes wire strategies via
`reviewer_dotted_path`, either by short name (registry lookup) or full
dotted path. See `docs/strategies.md` for authoring a new strategy.
"""

from .agentic import AgenticReviewer
from .draft_critique import DraftCritiqueReviewer
from .multi_sample import MultiSampleReviewer
from .registry import (
    UnknownStrategy,
    register_strategy,
    registered_strategy_names,
    resolve_strategy,
)
from .self_filter import SelfFilterReviewer
from .two_model_pipeline import TwoModelPipelineReviewer

# Built-in pre-registration.
register_strategy("agentic", AgenticReviewer)
register_strategy("draft_critique", DraftCritiqueReviewer)
register_strategy("two_model_pipeline", TwoModelPipelineReviewer)
register_strategy("self_filter", SelfFilterReviewer)
register_strategy("multi_sample", MultiSampleReviewer)

__all__ = [
    "AgenticReviewer",
    "DraftCritiqueReviewer",
    "MultiSampleReviewer",
    "SelfFilterReviewer",
    "TwoModelPipelineReviewer",
    "UnknownStrategy",
    "register_strategy",
    "registered_strategy_names",
    "resolve_strategy",
]
