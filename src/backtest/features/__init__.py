"""
Feature specification and computation pipeline.

DEPRECATED: Use src.indicators instead. This module remains for internal
backtest engine dependencies only.

See: src/indicators/__init__.py for the canonical API.
"""

from .feature_spec import (
    InputSource,
    FeatureSpec,
    FeatureSpecSet,
    # Multi-output helpers (now delegate to registry)
    is_multi_output,
    get_output_names,
    # Factory functions
    ema_spec,
    sma_spec,
    rsi_spec,
    atr_spec,
    macd_spec,
    bbands_spec,
    stoch_spec,
    stochrsi_spec,
)
from .feature_frame_builder import (
    FeatureFrameBuilder,
    FeatureArrays,
    IndicatorCompute,
    get_compute,
    build_features_from_play,
    PlayFeatures,
)

__all__ = [
    # Core types
    "InputSource",
    "FeatureSpec",
    "FeatureSpecSet",
    # Multi-output helpers
    "is_multi_output",
    "get_output_names",
    # Builder and compute adapter
    "FeatureFrameBuilder",
    "FeatureArrays",
    "IndicatorCompute",
    "get_compute",
    # Play integration
    "build_features_from_play",
    "PlayFeatures",
    # Factory functions
    "ema_spec",
    "sma_spec",
    "rsi_spec",
    "atr_spec",
    "macd_spec",
    "bbands_spec",
    "stoch_spec",
    "stochrsi_spec",
]
