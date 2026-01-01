"""
Feature specification and computation pipeline.

This module provides:
- FeatureSpec: Declarative indicator specification (string-based indicator types)
- FeatureFrameBuilder: Vectorized indicator computation
- IndicatorRegistry: Backend-swappable indicator registry

All indicators are computed outside the hot loop, vectorized,
and stored in FeedStore-compatible arrays.

**Registry Consolidation (2025-12-31):**
- Indicator types are now STRINGS validated against IndicatorRegistry
- IndicatorType enum has been REMOVED
- MULTI_OUTPUT_KEYS dict has been REMOVED
- All metadata lives in SUPPORTED_INDICATORS dict in indicator_registry.py
- Use registry.is_multi_output() and registry.get_output_suffixes() for queries

**Indicator Availability:**
- Registered: 42 indicators with warmup formulas in indicator_registry.py
- Available from pandas_ta: 189 indicators total
- See `reference/pandas_ta/INDICATORS_REFERENCE.md` for complete list

Multi-output indicators (MACD, BBANDS, STOCH, STOCHRSI) produce multiple
output arrays with automatic key naming based on output_key prefix.
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
    IndicatorRegistry,
    get_registry,
    build_features_from_idea_card,
    IdeaCardFeatures,
)

__all__ = [
    # Core types
    "InputSource",
    "FeatureSpec",
    "FeatureSpecSet",
    # Multi-output helpers
    "is_multi_output",
    "get_output_names",
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
