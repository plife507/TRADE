"""
Rationalization Module - Layer 2 State Processing.

Provides transition detection, derived state computation, and regime classification
for the backtest engine.

Architecture Principle: Pure Math
- StateRationalizer defines WHAT to compute
- Engine orchestrates WHEN to call it
- No side effects beyond internal state tracking

Entry Points:
    from src.backtest.rationalization import (
        StateRationalizer,   # Main rationalization class
        RationalizedState,   # Output per bar
        Transition,          # Single state change
        MarketRegime,        # Regime enum
    )

Engine Integration:
    # After structure updates, before snapshot build:
    rationalized = rationalizer.rationalize(bar_idx, incremental_state, bar)
    snapshot.attach_rationalized_state(rationalized)

See: docs/architecture/IDEACARD_VISION.md
"""

from .types import (
    Transition,
    RationalizedState,
    MarketRegime,
    TransitionFilter,
)
from .rationalizer import StateRationalizer
from .transitions import TransitionManager, TRACKED_FIELDS
from .derived import DerivedStateComputer

__all__ = [
    # Core types
    "Transition",
    "RationalizedState",
    "MarketRegime",
    "TransitionFilter",
    # Main class
    "StateRationalizer",
    # Transition detection
    "TransitionManager",
    "TRACKED_FIELDS",
    # Derived state
    "DerivedStateComputer",
]
