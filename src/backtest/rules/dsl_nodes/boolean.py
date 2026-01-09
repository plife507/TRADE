"""
DSL Boolean Expression Nodes for Play Expression Language.

This module defines boolean expression nodes:
- AllExpr: AND expression (all children must be true)
- AnyExpr: OR expression (any child must be true)
- NotExpr: NOT expression (negates child)
- SetupRef: Reference to a reusable Setup
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .types import Expr


# =============================================================================
# Boolean Expression Nodes
# =============================================================================

@dataclass(frozen=True)
class AllExpr:
    """
    AND expression: All children must be true.

    Short-circuit evaluation: First false result stops evaluation.

    Attributes:
        children: Tuple of child expressions (at least 1)

    Examples:
        AllExpr((cond1, cond2, cond3))  # cond1 AND cond2 AND cond3
    """
    children: tuple["Expr", ...]

    def __post_init__(self):
        """Validate children."""
        if len(self.children) < 1:
            raise ValueError("AllExpr: requires at least 1 child expression")

    def __repr__(self) -> str:
        if len(self.children) == 1:
            return repr(self.children[0])
        children_str = ", ".join(repr(c) for c in self.children)
        return f"All({children_str})"


@dataclass(frozen=True)
class AnyExpr:
    """
    OR expression: Any child must be true.

    Short-circuit evaluation: First true result stops evaluation.

    Attributes:
        children: Tuple of child expressions (at least 1)

    Examples:
        AnyExpr((cond1, cond2))  # cond1 OR cond2
    """
    children: tuple["Expr", ...]

    def __post_init__(self):
        """Validate children."""
        if len(self.children) < 1:
            raise ValueError("AnyExpr: requires at least 1 child expression")

    def __repr__(self) -> str:
        if len(self.children) == 1:
            return repr(self.children[0])
        children_str = ", ".join(repr(c) for c in self.children)
        return f"Any({children_str})"


@dataclass(frozen=True)
class NotExpr:
    """
    NOT expression: Negates the child expression.

    Attributes:
        child: The expression to negate

    Examples:
        NotExpr(cond)  # NOT cond
    """
    child: "Expr"

    def __repr__(self) -> str:
        return f"Not({self.child!r})"


# =============================================================================
# Setup Reference Node
# =============================================================================

@dataclass(frozen=True)
class SetupRef:
    """
    A reference to a Setup defined in strategies/setups/.

    Setups are reusable market condition blocks that encapsulate
    common patterns (e.g., "RSI oversold", "EMA pullback").

    When evaluated, the Setup's condition is resolved and evaluated
    as if it were inlined at this position.

    Attributes:
        setup_id: The Setup ID to reference (e.g., "rsi_oversold")

    Examples:
        SetupRef(setup_id="rsi_oversold")
        SetupRef(setup_id="ema_pullback")

    YAML Syntax:
        - setup: rsi_oversold
        - all:
            - setup: rsi_oversold
            - setup: ema_pullback
    """
    setup_id: str

    def __post_init__(self):
        """Validate SetupRef parameters."""
        if not self.setup_id:
            raise ValueError("SetupRef: setup_id is required")

    def __repr__(self) -> str:
        return f"Setup({self.setup_id!r})"


__all__ = [
    "AllExpr",
    "AnyExpr",
    "NotExpr",
    "SetupRef",
]
