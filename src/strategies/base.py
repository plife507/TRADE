"""
Base strategy interface.

Strategies receive a snapshot (RuntimeSnapshot or RuntimeSnapshotView) and params,
returning a Signal or None. This module defines the interface and helper utilities.

P3-004: SnapshotType alias supports both RuntimeSnapshot (legacy) and
RuntimeSnapshotView (preferred, zero-allocation accessor pattern).
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from ..backtest.runtime.snapshot_view import RuntimeSnapshotView
from ..backtest.runtime.types import RuntimeSnapshot
from ..core.risk_manager import Signal

# P3-004 FIX: Type alias for snapshot types (Python 3.10+ union syntax)
# Strategies should accept either RuntimeSnapshot (legacy) or RuntimeSnapshotView (preferred)
SnapshotType = RuntimeSnapshot | RuntimeSnapshotView


class BaseStrategy(ABC):
    """
    Abstract base class for trading strategies.

    Subclasses implement generate_signal() to produce trading signals.

    P3-004: Accepts both RuntimeSnapshot and RuntimeSnapshotView.
    Prefer RuntimeSnapshotView for new strategies (zero-allocation pattern).
    """

    @property
    @abstractmethod
    def strategy_id(self) -> str:
        """Unique strategy identifier."""
        pass

    @abstractmethod
    def generate_signal(
        self,
        snapshot: SnapshotType,
        params: dict[str, Any],
    ) -> Signal | None:
        """
        Generate a trading signal based on current market state.

        Args:
            snapshot: Current market snapshot (RuntimeSnapshot or RuntimeSnapshotView)
            params: Strategy parameters from config

        Returns:
            Signal object or None if no action
        """
        pass

    def __call__(
        self,
        snapshot: SnapshotType,
        params: dict[str, Any],
    ) -> Signal | None:
        """Allow strategy to be called as a function."""
        return self.generate_signal(snapshot, params)


def strategy_function(
    strategy_id: str,
) -> Callable[[Callable], Callable]:
    """
    Decorator to register a function as a strategy.
    
    Usage:
        @strategy_function("my_strategy_v1")
        def my_strategy(snapshot, params):
            # ... strategy logic ...
            return Signal(...) or None
    """
    def decorator(func: Callable) -> Callable:
        func._strategy_id = strategy_id
        return func
    return decorator
