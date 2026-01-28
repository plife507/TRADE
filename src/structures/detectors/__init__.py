"""
Incremental structure detectors.

This package contains detector implementations that update incrementally
bar-by-bar. Each detector is registered via @register_structure and can
be used in Plays.

Available Detectors:
- rolling_window: O(1) amortized sliding window min/max
- swing: Swing high/low detection with delayed confirmation
- trend: Trend direction classification from swing sequence
- zone: Supply/demand zone tracking from swing pivots
- fibonacci: Fibonacci retracement/extension levels from swing points
- derived_zone: K slots + aggregates pattern for derived zones
- market_structure: ICT-style BOS/CHoCH detection

See: docs/architecture/INCREMENTAL_STATE_ARCHITECTURE.md
"""

# Import detectors to trigger registration
from .derived_zone import IncrementalDerivedZone
from .fibonacci import IncrementalFibonacci
from .market_structure import IncrementalMarketStructure
from .rolling_window import IncrementalRollingWindow
from .swing import IncrementalSwing
from .trend import IncrementalTrend
from .zone import IncrementalZone

__all__ = [
    "IncrementalDerivedZone",
    "IncrementalFibonacci",
    "IncrementalMarketStructure",
    "IncrementalRollingWindow",
    "IncrementalSwing",
    "IncrementalTrend",
    "IncrementalZone",
]
