"""
Market Structure Engine.

Provides structure detection (swing, trend) and zone computation
for logic-based trading strategies.
"""

from src.backtest.market_structure.types import (
    StructureType,
    ZoneType,
    ZoneState,
    TrendState,
    SWING_OUTPUTS,
    TREND_OUTPUTS,
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
    "SWING_OUTPUTS",
    "TREND_OUTPUTS",
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
