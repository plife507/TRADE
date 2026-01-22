"""
Indicator Module: Shared technical indicator primitives.

This module provides the canonical indicator computation infrastructure
used by both backtest and live trading systems.

Components:
- registry: Indicator metadata, validation, warmup calculation
- vendor: pandas_ta wrapper (only pandas_ta import point)
- compute: DataFrame-based indicator application
- spec: FeatureSpec declarative indicator definitions
- builder: FeatureFrameBuilder for vectorized computation
- metadata: Provenance tracking for indicator values

Usage:
    from src.indicators import get_registry, compute_indicator, FeatureSpec

    # Registry API
    registry = get_registry()
    if registry.is_supported("macd"):
        warmup = registry.get_warmup_bars("macd", {"fast": 12, "slow": 26})

    # Compute indicators
    result = compute_indicator("ema", close=close_series, length=20)

    # Define indicator specs
    spec = FeatureSpec(
        indicator_type="ema",
        output_key="ema_20",
        params={"length": 20},
    )
"""

# =============================================================================
# Registry exports (canonical: src/backtest/indicator_registry.py)
# =============================================================================
from src.backtest.indicator_registry import (
    get_registry,
    IndicatorRegistry,
    IndicatorInfo,
    SUPPORTED_INDICATORS,
    INDICATOR_OUTPUT_TYPES,
    validate_indicator_type,
    validate_indicator_params,
)

# =============================================================================
# Vendor exports (canonical: src/backtest/indicator_vendor.py)
# =============================================================================
from src.backtest.indicator_vendor import (
    compute_indicator,
    canonicalize_indicator_outputs,
    CanonicalizeResult,
    # Single-output indicator functions
    ema,
    sma,
    rsi,
    atr,
    # Multi-output indicator functions
    macd,
    bbands,
    stoch,
    stochrsi,
)

# =============================================================================
# Compute exports (DataFrame-based application)
# =============================================================================
from .compute import (
    get_warmup_from_specs,
    apply_feature_spec_indicators,
    get_required_indicator_columns_from_specs,
    find_first_valid_bar,
    get_warmup_from_specs_by_role,
    get_max_warmup_from_specs_by_role,
)

# =============================================================================
# Spec exports (canonical: src/backtest/features/feature_spec.py)
# =============================================================================
from src.backtest.features.feature_spec import (
    FeatureSpec,
    FeatureSpecSet,
    InputSource,
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

# =============================================================================
# Builder exports (canonical: src/backtest/features/feature_frame_builder.py)
# =============================================================================
from src.backtest.features.feature_frame_builder import (
    FeatureFrameBuilder,
    FeatureArrays,
    IndicatorCompute,
    get_compute,
    build_features_from_play,
    build_features_from_preloaded_dfs,
    PlayFeatures,
)

# =============================================================================
# Metadata exports (provenance tracking)
# =============================================================================
from .metadata import (
    IndicatorMetadata,
    canonicalize_params,
    compute_feature_spec_id,
    find_first_valid_idx,
    get_pandas_ta_version,
    get_code_version,
    validate_metadata_coverage,
    validate_feature_spec_ids,
    MetadataValidationResult,
    export_metadata_jsonl,
    export_metadata_json,
    export_metadata_csv,
)

# =============================================================================
# Incremental exports (O(1) live updates)
# =============================================================================
from .incremental import (
    IncrementalIndicator,
    IncrementalEMA,
    IncrementalSMA,
    IncrementalRSI,
    IncrementalATR,
    IncrementalMACD,
    IncrementalBBands,
    create_incremental_indicator,
    supports_incremental,
    INCREMENTAL_INDICATORS,
)


__all__ = [
    # Registry
    "get_registry",
    "IndicatorRegistry",
    "IndicatorInfo",
    "SUPPORTED_INDICATORS",
    "INDICATOR_OUTPUT_TYPES",
    "validate_indicator_type",
    "validate_indicator_params",
    # Vendor
    "compute_indicator",
    "canonicalize_indicator_outputs",
    "CanonicalizeResult",
    "ema",
    "sma",
    "rsi",
    "atr",
    "macd",
    "bbands",
    "stoch",
    "stochrsi",
    # Compute
    "get_warmup_from_specs",
    "apply_feature_spec_indicators",
    "get_required_indicator_columns_from_specs",
    "find_first_valid_bar",
    "get_warmup_from_specs_by_role",
    "get_max_warmup_from_specs_by_role",
    # Spec
    "FeatureSpec",
    "FeatureSpecSet",
    "InputSource",
    "is_multi_output",
    "get_output_names",
    "ema_spec",
    "sma_spec",
    "rsi_spec",
    "atr_spec",
    "macd_spec",
    "bbands_spec",
    "stoch_spec",
    "stochrsi_spec",
    # Builder
    "FeatureFrameBuilder",
    "FeatureArrays",
    "IndicatorCompute",
    "get_compute",
    "build_features_from_play",
    "build_features_from_preloaded_dfs",
    "PlayFeatures",
    # Metadata
    "IndicatorMetadata",
    "canonicalize_params",
    "compute_feature_spec_id",
    "find_first_valid_idx",
    "get_pandas_ta_version",
    "get_code_version",
    "validate_metadata_coverage",
    "validate_feature_spec_ids",
    "MetadataValidationResult",
    "export_metadata_jsonl",
    "export_metadata_json",
    "export_metadata_csv",
    # Incremental
    "IncrementalIndicator",
    "IncrementalEMA",
    "IncrementalSMA",
    "IncrementalRSI",
    "IncrementalATR",
    "IncrementalMACD",
    "IncrementalBBands",
    "create_incremental_indicator",
    "supports_incremental",
    "INCREMENTAL_INDICATORS",
]
