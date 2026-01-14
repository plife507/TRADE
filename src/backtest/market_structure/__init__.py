"""
Market Structure Engine - BATCH PROCESSING.

Provides structure detection (swing, trend) and zone computation
for logic-based trading strategies.

Architecture: Batch-oriented, processes entire DataFrame using numpy arrays.
Use Case: Smoke tests, offline analysis, visualization.

For O(1) per-bar detection (live trading / backtest engine), see:
    src/backtest/incremental/

Type definitions (canonical location): src/backtest/structure_types.py
"""

from src.backtest.market_structure.types import (
    StructureType,
    ZoneType,
    ZoneState,
    TrendState,
)
from src.backtest.market_structure.spec import (
    ConfirmationConfig,
    StructureSpec,
    ZoneSpec,
)
from src.backtest.market_structure.registry import (
    STRUCTURE_REGISTRY,
    BaseDetector,
    register_detectors,
    get_detector,
    validate_structure_type,
    validate_structure_params,
    get_structure_outputs,
)
from src.backtest.market_structure.builder import (
    StructureBuilder,
    StructureStore,
    StructureManifestEntry,
    Stage2ValidationError,
    validate_stage2_exec_only,
)
from src.backtest.market_structure.detectors import (
    SwingDetector,
    SwingState,
    detect_swing_pivots,
    TrendClassifier,
    classify_single_swing_update,
)

__all__ = [
    # Types
    "StructureType",
    "ZoneType",
    "ZoneState",
    "TrendState",
    # Specs
    "ConfirmationConfig",
    "StructureSpec",
    "ZoneSpec",
    # Registry
    "STRUCTURE_REGISTRY",
    "BaseDetector",
    "register_detectors",
    "get_detector",
    "validate_structure_type",
    "validate_structure_params",
    "get_structure_outputs",
    # Builder
    "StructureBuilder",
    "StructureStore",
    "StructureManifestEntry",
    "Stage2ValidationError",
    "validate_stage2_exec_only",
    # Detectors
    "SwingDetector",
    "SwingState",
    "detect_swing_pivots",
    "TrendClassifier",
    "classify_single_swing_update",
]
