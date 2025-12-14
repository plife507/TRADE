"""
Feature specification and computation pipeline.

This module provides:
- FeatureSpec: Declarative indicator specification
- FeatureFrameBuilder: Vectorized indicator computation
- IndicatorRegistry: Backend-swappable indicator registry
- IndicatorType: Supported indicator types (single and multi-output)

All indicators are computed outside the hot loop, vectorized,
and stored in FeedStore-compatible arrays.

**Indicator Availability:**
- Currently implemented: 8 indicators (EMA, SMA, RSI, ATR, MACD, BBANDS, STOCH, STOCHRSI)
- Available from pandas_ta: 189 indicators total
- See `reference/pandas_ta/INDICATORS_REFERENCE.md` for complete list

Multi-output indicators (MACD, BBANDS, STOCH, STOCHRSI) produce multiple
output arrays with automatic key naming based on output_key prefix.
"""

from .feature_spec import (
    IndicatorType,
    InputSource,
    FeatureSpec,
    FeatureSpecSet,
    # Multi-output helpers
    is_multi_output,
    get_output_names,
    MULTI_OUTPUT_KEYS,
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
    IndicatorRegistry,
    get_registry,
    build_features_from_idea_card,
    IdeaCardFeatures,
)

__all__ = [
    # Core types
    "IndicatorType",
    "InputSource",
    "FeatureSpec",
    "FeatureSpecSet",
    # Multi-output helpers
    "is_multi_output",
    "get_output_names",
    "MULTI_OUTPUT_KEYS",
    # Builder and registry
    "FeatureFrameBuilder",
    "FeatureArrays",
    "IndicatorRegistry",
    "get_registry",
    # IdeaCard integration
    "build_features_from_idea_card",
    "IdeaCardFeatures",
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
