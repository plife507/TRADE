"""
Indicator Module: Shared technical indicator primitives.

This module provides the canonical indicator computation infrastructure
used by both backtest and live trading systems.

Components:
- registry: Indicator metadata, validation, warmup calculation
- vendor: pandas_ta wrapper (only pandas_ta import point)
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
)

# =============================================================================
# Vendor exports (canonical: src/backtest/indicator_vendor.py)
# =============================================================================
from src.backtest.indicator_vendor import (
    compute_indicator,
    canonicalize_indicator_outputs,
    CanonicalizeResult,
)
# G1.8: Standalone indicator functions (ema, sma, rsi, etc.) removed - use compute_indicator()

# =============================================================================
# Compute exports (canonical: src/backtest/indicators.py)
# =============================================================================
from src.backtest.indicators import (
    get_warmup_from_specs,
    apply_feature_spec_indicators,
    get_required_indicator_columns_from_specs,
    get_validity_check_columns_from_specs,
    RUNTIME_ONLY_INDICATORS,
    find_first_valid_bar,
    get_warmup_from_specs_by_role,
    get_max_warmup_from_specs_by_role,
)

# =============================================================================
# Spec exports (canonical: src/backtest/features/feature_spec.py)
# =============================================================================
from src.backtest.features.feature_spec import (
    FeatureSpec,
    InputSource,
    is_multi_output,
    get_output_names,
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
)

# =============================================================================
# Incremental exports (O(1) live updates)
# =============================================================================
from .incremental import (
    IncrementalIndicator,
    # Original 11 incremental indicators
    IncrementalEMA,
    IncrementalSMA,
    IncrementalRSI,
    IncrementalATR,
    IncrementalMACD,
    IncrementalBBands,
    IncrementalWilliamsR,
    IncrementalCCI,
    IncrementalStochastic,
    IncrementalADX,
    IncrementalSuperTrend,
    IncrementalStochRSI,
    # Phase 1: Trivial indicators
    IncrementalOHLC4,
    IncrementalMidprice,
    IncrementalROC,
    IncrementalMOM,
    IncrementalOBV,
    IncrementalNATR,
    # Phase 2: EMA-composable indicators
    IncrementalDEMA,
    IncrementalTEMA,
    IncrementalPPO,
    IncrementalTRIX,
    IncrementalTSI,
    # Phase 3: SMA/Buffer-based indicators
    IncrementalWMA,
    IncrementalTRIMA,
    IncrementalLINREG,
    IncrementalCMF,
    IncrementalCMO,
    IncrementalMFI,
    # Phase 4: Lookback-based indicators
    IncrementalAROON,
    IncrementalDonchian,
    IncrementalKC,
    IncrementalDM,
    IncrementalVortex,
    # Phase 5: Complex adaptive indicators
    IncrementalKAMA,
    IncrementalALMA,
    IncrementalZLMA,
    IncrementalUO,
    # Phase 6: Stateful multi-output indicators
    IncrementalPSAR,
    IncrementalSqueeze,
    IncrementalFisher,
    # Phase 7: Volume complex indicators
    IncrementalKVO,
    IncrementalVWAP,
    IncrementalAnchoredVWAP,
    # Factory and utilities
    create_incremental_indicator,
    supports_incremental,
    list_incremental_indicators,
)


__all__ = [
    # Registry
    "get_registry",
    "IndicatorRegistry",
    "IndicatorInfo",
    "SUPPORTED_INDICATORS",
    # Vendor
    "compute_indicator",
    "canonicalize_indicator_outputs",
    "CanonicalizeResult",
    # Compute
    "get_warmup_from_specs",
    "apply_feature_spec_indicators",
    "get_required_indicator_columns_from_specs",
    "get_validity_check_columns_from_specs",
    "RUNTIME_ONLY_INDICATORS",
    "find_first_valid_bar",
    "get_warmup_from_specs_by_role",
    "get_max_warmup_from_specs_by_role",
    # Spec
    "FeatureSpec",
    "InputSource",
    "is_multi_output",
    "get_output_names",
    # Builder
    "FeatureFrameBuilder",
    "FeatureArrays",
    "IndicatorCompute",
    "get_compute",
    "build_features_from_play",
    "PlayFeatures",
    # Metadata
    "IndicatorMetadata",
    "canonicalize_params",
    "compute_feature_spec_id",
    "find_first_valid_idx",
    "get_pandas_ta_version",
    "get_code_version",
    # Incremental (all 44 indicators)
    "IncrementalIndicator",
    "IncrementalEMA",
    "IncrementalSMA",
    "IncrementalRSI",
    "IncrementalATR",
    "IncrementalMACD",
    "IncrementalBBands",
    "IncrementalWilliamsR",
    "IncrementalCCI",
    "IncrementalStochastic",
    "IncrementalADX",
    "IncrementalSuperTrend",
    "IncrementalStochRSI",
    "IncrementalOHLC4",
    "IncrementalMidprice",
    "IncrementalROC",
    "IncrementalMOM",
    "IncrementalOBV",
    "IncrementalNATR",
    "IncrementalDEMA",
    "IncrementalTEMA",
    "IncrementalPPO",
    "IncrementalTRIX",
    "IncrementalTSI",
    "IncrementalWMA",
    "IncrementalTRIMA",
    "IncrementalLINREG",
    "IncrementalCMF",
    "IncrementalCMO",
    "IncrementalMFI",
    "IncrementalAROON",
    "IncrementalDonchian",
    "IncrementalKC",
    "IncrementalDM",
    "IncrementalVortex",
    "IncrementalKAMA",
    "IncrementalALMA",
    "IncrementalZLMA",
    "IncrementalUO",
    "IncrementalPSAR",
    "IncrementalSqueeze",
    "IncrementalFisher",
    "IncrementalKVO",
    "IncrementalVWAP",
    "IncrementalAnchoredVWAP",
    "create_incremental_indicator",
    "supports_incremental",
    "list_incremental_indicators",
]
