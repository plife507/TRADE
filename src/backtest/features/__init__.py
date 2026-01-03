"""
Feature specification and computation pipeline.

This module provides:
- FeatureSpec: Declarative indicator specification (string-based indicator types)
- FeatureFrameBuilder: Vectorized indicator computation
- IndicatorCompute: Backend-swappable compute adapter for indicator calculation

All indicators are computed outside the hot loop, vectorized,
and stored in FeedStore-compatible arrays.

**Registry vs Compute (2026-01-02):**
- IndicatorRegistry (in indicator_registry.py): SINGLE SOURCE OF TRUTH for indicator
  metadata and validation. Use this for checking supported indicators, params, etc.
- IndicatorCompute (in this module): Compute adapter that wraps pandas_ta calls and
  delegates validation to the main registry.

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
    IndicatorCompute,
    IndicatorRegistry,  # Deprecated alias for IndicatorCompute
    get_compute,
    get_registry,  # Deprecated alias for get_compute
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
    # Builder and compute adapter
    "FeatureFrameBuilder",
    "FeatureArrays",
    "IndicatorCompute",
    "get_compute",
    # Deprecated aliases (for backwards compatibility)
    "IndicatorRegistry",  # Use IndicatorCompute instead
    "get_registry",  # Use get_compute instead
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
