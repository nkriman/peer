"""Strategy registry: short-name + dotted-path resolver.

Built-in strategies pre-register at import time (`peer.strategies.__init__`
imports each strategy module which calls `register_strategy(name, cls)`).
Users add new strategies by dropping a file in `peer/strategies/`, calling
`register_strategy` at module import.
"""

from __future__ import annotations

import importlib
from typing import Any

from ..exceptions import PeerError


class UnknownStrategy(PeerError):
    """resolve_strategy was called with a name/path that doesn't map to a class."""


_REGISTRY: dict[str, type] = {}


def register_strategy(name: str, cls: type) -> None:
    """Register a Reviewer-shaped class under a short name.

    Re-registering an existing name overwrites — useful for tests that
    swap built-ins for fakes.
    """
    _REGISTRY[name] = cls


def resolve_strategy(name_or_path: str) -> type:
    """Resolve a short name (registry lookup) or dotted Python path.

    Short names are tried first; if no match, the string is treated as a
    dotted import path and resolved via importlib. Either way, raises
    `UnknownStrategy` on miss.
    """
    if name_or_path in _REGISTRY:
        return _REGISTRY[name_or_path]
    if "." in name_or_path:
        module_path, attr = name_or_path.rsplit(".", 1)
        try:
            mod = importlib.import_module(module_path)
        except ImportError as e:
            raise UnknownStrategy(
                f"Cannot import module {module_path!r} for strategy {name_or_path!r}: {e}"
            ) from e
        cls = getattr(mod, attr, None)
        if cls is None:
            raise UnknownStrategy(
                f"Module {module_path!r} has no attribute {attr!r} for strategy {name_or_path!r}"
            )
        return cls  # type: ignore[no-any-return]
    raise UnknownStrategy(
        f"Unknown strategy {name_or_path!r}. "
        f"Registered short names: {sorted(_REGISTRY)}. "
        f"For other modules, use a full dotted path like 'mypkg.module.MyStrategy'."
    )


def registered_strategy_names() -> list[str]:
    return sorted(_REGISTRY)


# Forward declarations for late-import-resolution. Modules in this package
# import each strategy lazily to avoid circular imports.
_ = Any
