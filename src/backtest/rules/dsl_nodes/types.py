"""
DSL Type Aliases for Play Expression Language.

This module defines type aliases used across the DSL modules.
Placed in a separate module to avoid circular imports.
"""

from __future__ import annotations

from .condition import Cond
from .boolean import AllExpr, AnyExpr, NotExpr, SetupRef
from .windows import (
    HoldsFor, OccurredWithin, CountTrue,
    HoldsForDuration, OccurredWithinDuration, CountTrueDuration,
    BarWindowExpr, DurationWindowExpr, WindowExpr,
)


# =============================================================================
# Type Alias
# =============================================================================

# All expression types that can appear in a condition tree
Expr = (
    AllExpr | AnyExpr | NotExpr | Cond
    | HoldsFor | OccurredWithin | CountTrue
    | HoldsForDuration | OccurredWithinDuration | CountTrueDuration
    | SetupRef
)


__all__ = [
    "Expr",
    "BarWindowExpr",
    "DurationWindowExpr",
    "WindowExpr",
]
