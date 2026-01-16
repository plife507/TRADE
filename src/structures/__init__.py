"""
Shared structure detection module.

This module provides incremental O(1) structure detectors that can be used
by both backtest and live trading systems. All detectors update bar-by-bar
with constant-time amortized complexity.

Public API:
-----------

Types (from types.py):
    StructureType    - Enum of supported structure types
    ZoneType         - Enum of zone types (demand/supply)
    ZoneState        - Enum of zone states (NONE, ACTIVE, BROKEN)
    TrendState       - Enum of trend states (UNKNOWN, UP, DOWN)

Primitives (from primitives.py):
    MonotonicDeque   - O(1) amortized sliding window min/max
    RingBuffer       - Fixed-size circular buffer

Base Classes (from base.py):
    BarData                   - Immutable bar data passed to detectors
    BaseIncrementalDetector   - Abstract base class for all detectors

Registry (from registry.py):
    STRUCTURE_REGISTRY        - Global registry of detector classes
    register_structure        - Decorator to register detector classes
    unregister_structure      - Remove a detector from registry
    get_structure_info        - Get metadata about a registered structure
    list_structure_types      - List all registered structure types
    get_structure_warmup      - Get warmup bars needed for a structure
    get_structure_output_type - Get output type for a structure field
    STRUCTURE_OUTPUT_TYPES    - Maps structure fields to output types
    STRUCTURE_WARMUP_FORMULAS - Maps structure types to warmup formulas

State Containers (from state.py):
    TFIncrementalState        - Container for single-timeframe structures
    MultiTFIncrementalState   - Container for multi-timeframe structures

Batch Wrapper (from batch_wrapper.py):
    run_detector_batch        - Run detector in batch mode over OHLCV data
    create_detector_with_deps - Create detector with instantiated dependencies

Detectors (from detectors/):
    IncrementalSwingDetector  - Swing high/low detection with pivot pairing
    IncrementalTrendDetector  - Trend direction classification
    IncrementalZoneDetector   - Demand/supply zone detection
    IncrementalFibonacci      - Fibonacci retracement/extension levels
    IncrementalRollingWindow  - Rolling window min/max
    IncrementalDerivedZone    - Derived zones with K slots + aggregates

Example Usage:
--------------

    from src.structures import (
        MultiTFIncrementalState,
        IncrementalSwingDetector,
        BarData,
        STRUCTURE_REGISTRY,
    )

    # Create multi-TF state with swing and trend
    state = MultiTFIncrementalState(
        exec_tf="15m",
        exec_specs=[
            {"type": "swing", "key": "swing", "params": {"left": 5, "right": 5}},
            {"type": "trend", "key": "trend", "depends_on": {"swing": "swing"}},
        ],
    )

    # Update with bar data
    bar = BarData(idx=0, open=100, high=105, low=95, close=102, volume=1000, indicators={})
    state.update_exec(bar)

    # Access structure values
    swing_high = state.get_value("exec.swing.high_level")
    trend_dir = state.get_value("exec.trend.direction")

See: docs/architecture/INCREMENTAL_STATE_ARCHITECTURE.md
"""

# Types
from .types import (
    StructureType,
    ZoneType,
    ZoneState,
    TrendState,
    FeatureOutputType,
)

# Primitives
from .primitives import (
    MonotonicDeque,
    RingBuffer,
)

# Base classes
from .base import (
    BarData,
    BaseIncrementalDetector,
)

# Registry
from .registry import (
    STRUCTURE_REGISTRY,
    register_structure,
    unregister_structure,
    get_structure_info,
    list_structure_types,
    get_structure_warmup,
    get_structure_output_type,
    STRUCTURE_OUTPUT_TYPES,
    STRUCTURE_WARMUP_FORMULAS,
)

# State containers
from .state import (
    TFIncrementalState,
    MultiTFIncrementalState,
)

# Batch wrapper
from .batch_wrapper import (
    run_detector_batch,
    create_detector_with_deps,
)

# Detectors (imports trigger registration)
from .detectors import (
    IncrementalSwingDetector,
    IncrementalTrendDetector,
    IncrementalZoneDetector,
    IncrementalFibonacci,
    IncrementalMarketStructure,
    IncrementalRollingWindow,
    IncrementalDerivedZone,
)

__all__ = [
    # Types
    "StructureType",
    "ZoneType",
    "ZoneState",
    "TrendState",
    "FeatureOutputType",
    # Primitives
    "MonotonicDeque",
    "RingBuffer",
    # Base classes
    "BarData",
    "BaseIncrementalDetector",
    # Registry
    "STRUCTURE_REGISTRY",
    "register_structure",
    "unregister_structure",
    "get_structure_info",
    "list_structure_types",
    "get_structure_warmup",
    "get_structure_output_type",
    "STRUCTURE_OUTPUT_TYPES",
    "STRUCTURE_WARMUP_FORMULAS",
    # State containers
    "TFIncrementalState",
    "MultiTFIncrementalState",
    # Batch wrapper
    "run_detector_batch",
    "create_detector_with_deps",
    # Detectors
    "IncrementalSwingDetector",
    "IncrementalTrendDetector",
    "IncrementalZoneDetector",
    "IncrementalFibonacci",
    "IncrementalMarketStructure",
    "IncrementalRollingWindow",
    "IncrementalDerivedZone",
]
