"""
Strategy registry.

Maps (strategy_id, strategy_version) tuples to strategy functions.
Stores metadata for each strategy: function, description.

Terminology model:
- StrategyFamily: A Python implementation of trading logic
- Identified by (strategy_id, strategy_version) tuple

Identifier model:
- strategy_id: Stable family name (e.g., "ema_rsi_atr")
- strategy_version: Explicit version string (e.g., "1.0.0")

Phase 2: RuntimeSnapshot is the only supported snapshot type.
"""

from typing import Dict, Callable, Optional, Any, List, Tuple
from dataclasses import dataclass

from ..backtest.runtime.types import RuntimeSnapshot
from ..core.risk_manager import Signal


# Type alias for strategy functions (accepts RuntimeSnapshot only)
StrategyFunction = Callable[[RuntimeSnapshot, Dict[str, Any]], Optional[Signal]]

# Registry key type
StrategyKey = Tuple[str, str]  # (strategy_id, strategy_version)


@dataclass
class StrategyMetadata:
    """Metadata for a registered strategy."""
    strategy_id: str
    strategy_version: str
    function: StrategyFunction
    description: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "description": self.description,
        }


# Registry of available strategies: (strategy_id, strategy_version) -> metadata
_STRATEGIES: Dict[StrategyKey, StrategyMetadata] = {}


def register_strategy(
    strategy_id: str,
    strategy_version: str,
    strategy_fn: StrategyFunction,
    description: str = "",
) -> None:
    """
    Register a strategy function with metadata.
    
    Args:
        strategy_id: Stable unique identifier for the strategy (e.g., "ema_rsi_atr")
        strategy_version: Version string (e.g., "1.0.0")
        strategy_fn: Strategy function
        description: Human-readable description
    """
    key = (strategy_id, strategy_version)
    _STRATEGIES[key] = StrategyMetadata(
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        function=strategy_fn,
        description=description,
    )


def get_strategy(strategy_id: str, strategy_version: str) -> StrategyFunction:
    """
    Get a strategy function by ID and version.
    
    Args:
        strategy_id: Strategy identifier
        strategy_version: Strategy version
        
    Returns:
        Strategy function
        
    Raises:
        ValueError: If strategy not found
    """
    key = (strategy_id, strategy_version)
    if key not in _STRATEGIES:
        available = list_strategies()
        raise ValueError(
            f"Strategy '{strategy_id}' v{strategy_version} not found. "
            f"Available: {available}"
        )
    return _STRATEGIES[key].function


def get_strategy_metadata(strategy_id: str, strategy_version: str) -> Optional[StrategyMetadata]:
    """
    Get strategy metadata by ID and version.
    
    Args:
        strategy_id: Strategy identifier
        strategy_version: Strategy version
        
    Returns:
        StrategyMetadata or None if not found
    """
    key = (strategy_id, strategy_version)
    return _STRATEGIES.get(key)


def list_strategies() -> List[Tuple[str, str]]:
    """List all registered strategy (id, version) tuples."""
    return list(_STRATEGIES.keys())


def list_strategies_with_metadata() -> List[Dict[str, Any]]:
    """
    List all registered strategies with their metadata.
    
    Returns:
        List of dicts with strategy_id, strategy_version, description
    """
    return [meta.to_dict() for meta in _STRATEGIES.values()]


def strategy_exists(strategy_id: str, strategy_version: str) -> bool:
    """Check if a strategy is registered."""
    key = (strategy_id, strategy_version)
    return key in _STRATEGIES


# Register built-in strategies on module load
def _register_builtin_strategies():
    """Register all built-in strategies."""
    from . import ema_rsi_atr
    register_strategy(
        strategy_id=ema_rsi_atr.STRATEGY_ID,
        strategy_version=ema_rsi_atr.STRATEGY_DEFAULT_VERSION,
        strategy_fn=ema_rsi_atr.strategy,
        description=ema_rsi_atr.STRATEGY_DESCRIPTION,
    )


# Auto-register on import
_register_builtin_strategies()
