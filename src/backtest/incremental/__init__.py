"""
Incremental state module for bar-by-bar market structure computation.

DEPRECATED: Use src.structures instead. This module remains for internal
backtest engine dependencies only.

Architecture: O(1) per-bar stateful detection for PRODUCTION USE.
Use Case: Backtest engine, live trading, real-time signals.

See: docs/architecture/INCREMENTAL_STATE_ARCHITECTURE.md
"""

from .base import BarData, BaseIncrementalDetector
from .detectors import (
    IncrementalDerivedZone,
    IncrementalFibonacci,
    IncrementalMarketStructure,
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
    "IncrementalDerivedZone",
    "IncrementalFibonacci",
    "IncrementalMarketStructure",
    "IncrementalRollingWindow",
    "IncrementalSwingDetector",
    "IncrementalTrendDetector",
    "IncrementalZoneDetector",
    # Phase 4: State containers
    "TFIncrementalState",
    "MultiTFIncrementalState",
]
