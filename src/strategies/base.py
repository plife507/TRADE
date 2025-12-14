"""
Base strategy interface.

Strategies receive a RuntimeSnapshot and params, return a Signal or None.
This module defines the interface and helper utilities.

Phase 2: RuntimeSnapshot is the only supported snapshot type.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Callable

from ..backtest.runtime.types import RuntimeSnapshot
from ..core.risk_manager import Signal


class BaseStrategy(ABC):
    """
    Abstract base class for trading strategies.
    
    Subclasses implement generate_signal() to produce trading signals.
    
    Phase 2: Accepts RuntimeSnapshot only.
    """
    
    @property
    @abstractmethod
    def strategy_id(self) -> str:
        """Unique strategy identifier."""
        pass
    
    @abstractmethod
    def generate_signal(
        self,
        snapshot: RuntimeSnapshot,
        params: Dict[str, Any],
    ) -> Optional[Signal]:
        """
        Generate a trading signal based on current market state.
        
        Args:
            snapshot: Current market snapshot (RuntimeSnapshot)
            params: Strategy parameters from config
            
        Returns:
            Signal object or None if no action
        """
        pass
    
    def __call__(
        self,
        snapshot: RuntimeSnapshot,
        params: Dict[str, Any],
    ) -> Optional[Signal]:
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
