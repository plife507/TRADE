"""
Incremental state module for bar-by-bar market structure computation.

Provides O(1) hot-loop operations for:
- Rolling window min/max (via MonotonicDeque)
- Fixed-window lookback (via RingBuffer)
- Market structure detection (swing, trend, zone, fibonacci)

This module enables live-compatible incremental state that can be
updated bar-by-bar without recomputing entire history.

Phase 1 (Primitives):
- MonotonicDeque: O(1) amortized sliding window min/max
- RingBuffer: Fixed-size circular buffer

Phase 2 (Base + Registry):
- BarData: Immutable bar data for structure updates
- BaseIncrementalDetector: Abstract base class for detectors
- STRUCTURE_REGISTRY: Global registry of detector classes
- register_structure: Decorator to register detectors
- get_structure_info: Get metadata about a structure type
- list_structure_types: List all registered types

Phase 3 (Detectors):
- IncrementalSwingDetector: Swing high/low with delayed confirmation
- IncrementalFibonacci: Fibonacci retracement/extension levels
- IncrementalRollingWindow: O(1) rolling min/max
- IncrementalZoneDetector: Demand/supply zone tracking
- IncrementalTrendDetector: Trend classification from swing sequence

Phase 4 (State Containers):
- TFIncrementalState: Single timeframe state container
- MultiTFIncrementalState: Unified container for exec + HTF states

Future Phases:
- IdeaCard schema + parser integration
- Engine integration
- Batch code removal

See: docs/architecture/INCREMENTAL_STATE_ARCHITECTURE.md
"""

from .base import BarData, BaseIncrementalDetector
from .detectors import (
    IncrementalFibonacci,
    IncrementalRollingWindow,
    IncrementalSwingDetector,
    IncrementalTrendDetector,
    IncrementalZoneDetector,
)
from .primitives import MonotonicDeque, RingBuffer
from .registry import (
    STRUCTURE_REGISTRY,
    get_structure_info,
    list_structure_types,
    register_structure,
    unregister_structure,
)
from .state import MultiTFIncrementalState, TFIncrementalState

__all__ = [
    # Phase 1: Core primitives
    "MonotonicDeque",
    "RingBuffer",
    # Phase 2: Base class and data structures
    "BarData",
    "BaseIncrementalDetector",
    # Phase 2: Registry
    "STRUCTURE_REGISTRY",
    "register_structure",
    "unregister_structure",
    "get_structure_info",
    "list_structure_types",
    # Phase 3: Detectors
    "IncrementalFibonacci",
    "IncrementalRollingWindow",
    "IncrementalSwingDetector",
    "IncrementalTrendDetector",
    "IncrementalZoneDetector",
    # Phase 4: State containers
    "TFIncrementalState",
    "MultiTFIncrementalState",
]
