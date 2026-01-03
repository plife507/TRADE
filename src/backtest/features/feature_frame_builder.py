"""
FeatureFrameBuilder: Vectorized indicator computation.

Computes all indicators from a FeatureSpecSet in a single vectorized pass.
Returns FeatureArrays compatible with FeedStore.

Design principles:
- All computation outside hot loop (vectorized via indicator_vendor)
- Output is numpy arrays (float32 preferred for memory efficiency)
- Dependency resolution ensures chained indicators work
- Registry pattern allows backend swapping
- Compatible with FeedStore.indicators dict
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..idea_card import IdeaCard
    from ..runtime.indicator_metadata import IndicatorMetadata

from .feature_spec import (
    FeatureSpec,
    FeatureSpecSet,
    InputSource,
    is_multi_output,
    get_output_names,
)
from ..indicator_vendor import compute_indicator


# Type for indicator compute functions
SingleOutputFn = Callable[..., pd.Series]
MultiOutputFn = Callable[..., dict[str, pd.Series]]
IndicatorFn = SingleOutputFn | MultiOutputFn


@dataclass
class FeatureArrays:
    """
    Container for computed feature arrays.
    
    All arrays are float32 for memory efficiency.
    Length matches the input OHLCV data.
    
    Attributes:
        symbol: Trading symbol
        tf: Timeframe string
        arrays: Dict of output_key -> numpy array (float32)
        length: Number of bars
        warmup_bars: Bars needed for all indicators to be valid
        metadata: Dict of output_key -> IndicatorMetadata (provenance tracking)
    """
    symbol: str
    tf: str
    arrays: dict[str, np.ndarray] = field(default_factory=dict)
    length: int = 0
    warmup_bars: int = 0
    metadata: dict[str, "IndicatorMetadata"] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate arrays and metadata consistency."""
        for key, arr in self.arrays.items():
            if len(arr) != self.length:
                raise ValueError(
                    f"Array '{key}' length {len(arr)} != expected {self.length}"
                )

        # Validate metadata coverage (strict: every array MUST have metadata)
        # This is required for provenance tracking - no silent gaps allowed.
        array_keys = set(self.arrays.keys())
        metadata_keys = set(self.metadata.keys())
        if array_keys != metadata_keys:
            missing = array_keys - metadata_keys
            extra = metadata_keys - array_keys
            if missing:
                raise ValueError(
                    f"Missing metadata for indicators: {missing}. "
                    "All indicators must have provenance metadata."
                )
            if extra:
                raise ValueError(
                    f"Extra metadata without arrays: {extra}. "
                    "Metadata must match arrays exactly."
                )
    
    def get(self, key: str) -> np.ndarray | None:
        """Get array by key, or None if not found."""
        return self.arrays.get(key)
    
    def get_strict(self, key: str) -> np.ndarray:
        """
        Get array by key, or raise KeyError if not found.
        
        Raises:
            KeyError: If key is not found
        """
        if key not in self.arrays:
            raise KeyError(f"Feature key '{key}' not found. Available: {list(self.arrays.keys())}")
        return self.arrays[key]
    
    def keys(self) -> list[str]:
        """Get all output keys."""
        return list(self.arrays.keys())
    
    def has_key(self, key: str) -> bool:
        """Check if key exists."""
        return key in self.arrays
    
    def find_first_valid_index(self, keys: list[str] | None = None) -> int:
        """
        Find the first index where all specified indicators are non-NaN.

        Args:
            keys: List of keys to check (default: all keys)

        Returns:
            First valid index, or -1 if none found
        """
        if keys is None:
            keys = list(self.arrays.keys())
        
        if not keys:
            return 0
        
        # Check each index
        for i in range(self.length):
            all_valid = True
            for key in keys:
                if key in self.arrays:
                    val = self.arrays[key][i]
                    if np.isnan(val):
                        all_valid = False
                        break
            if all_valid:
                return i
        
        return -1

    @classmethod
    def empty(cls, symbol: str, tf: str, length: int = 0) -> "FeatureArrays":
        """
        Factory for empty arrays (no indicators declared).

        Use this instead of creating FeatureArrays with empty dicts directly.
        Ensures metadata consistency for zero-indicator case.

        Args:
            symbol: Trading symbol
            tf: Timeframe string
            length: Number of bars (default: 0)

        Returns:
            FeatureArrays with empty arrays and metadata
        """
        return cls(
            symbol=symbol,
            tf=tf,
            arrays={},
            length=length,
            warmup_bars=0,
            metadata={},
        )


# =============================================================================
# Indicator Compute Adapter
# =============================================================================

class IndicatorCompute:
    """
    Compute adapter for indicator calculation in FeatureFrameBuilder.

    **ALL pandas_ta indicators are available dynamically!**
    No static registration needed - indicators are computed on-demand based
    on what the IdeaCard declares in its FeatureSpecs.

    Note: This is distinct from IndicatorRegistry in indicator_registry.py,
    which is the SINGLE SOURCE OF TRUTH for indicator metadata and validation.
    This class wraps computation logic and delegates validation to the main registry.

    Reference: `reference/pandas_ta_repo/` for source code

    Usage:
        compute = IndicatorCompute()

        # Compute any indicator dynamically based on IdeaCard FeatureSpec
        ema_series = compute.compute("ema", close=close, length=20)
        adx_dict = compute.compute("adx", high=high, low=low, close=close, length=14)

        # Custom overrides still supported
        compute.register("ema", custom_ema_fn)
    """

    def __init__(self):
        """Initialize registry (no static registrations - all dynamic)."""
        self._custom_registry: dict[str, IndicatorFn] = {}

    def register(self, indicator_type: str, fn: IndicatorFn):
        """
        Register a custom compute function for an indicator type.

        Use this to override the default pandas_ta implementation
        or add completely custom indicators.

        Args:
            indicator_type: Type to register (string)
            fn: Compute function
        """
        self._custom_registry[indicator_type.lower()] = fn

    def has(self, indicator_type: str) -> bool:
        """
        Check if indicator type is available.

        Returns True for ALL valid indicator types since
        compute_indicator() handles any pandas_ta indicator dynamically.
        Validates against the indicator_registry module for supported types.
        """
        from ..indicator_registry import get_registry as get_main_registry
        return get_main_registry().is_supported(indicator_type.lower())

    def compute(
        self,
        indicator_type: str,
        close: pd.Series | None = None,
        high: pd.Series | None = None,
        low: pd.Series | None = None,
        open_: pd.Series | None = None,
        volume: pd.Series | None = None,
        **kwargs,
    ) -> pd.Series | dict[str, pd.Series]:
        """
        Compute an indicator dynamically.

        Uses pandas_ta compute_indicator() to handle ANY indicator type
        declared in the IdeaCard's FeatureSpecs. Custom overrides take
        precedence if registered.

        Args:
            indicator_type: Type to compute (string, e.g., "ema", "macd")
            close: Close price series
            high: High price series
            low: Low price series
            open_: Open price series
            volume: Volume series
            **kwargs: Indicator-specific parameters (length, fast, slow, etc.)

        Returns:
            pd.Series for single-output, dict[str, pd.Series] for multi-output
        """
        key = indicator_type.lower()

        # Check for custom override first
        if key in self._custom_registry:
            fn = self._custom_registry[key]
            return fn(close=close, high=high, low=low, open_=open_, volume=volume, **kwargs)

        # Dynamic computation for ALL indicators via compute_indicator()
        return compute_indicator(
            indicator_name=key,
            close=close,
            high=high,
            low=low,
            open_=open_,
            volume=volume,
            **kwargs,
        )

    def list_types(self) -> list[str]:
        """List all available indicator types (from main registry)."""
        from ..indicator_registry import get_registry as get_main_registry
        return get_main_registry().list_indicators()

    def list_custom_overrides(self) -> list[str]:
        """List indicator types with custom overrides registered."""
        return list(self._custom_registry.keys())


# Global compute adapter instance
_default_compute = IndicatorCompute()


def get_compute() -> IndicatorCompute:
    """Get the default indicator compute adapter."""
    return _default_compute


# Backwards compatibility alias (deprecated - use get_compute() instead)
def get_registry() -> IndicatorCompute:
    """Get the default indicator compute adapter (deprecated - use get_compute())."""
    return _default_compute


# Backwards compatibility alias for import (deprecated - use IndicatorCompute instead)
IndicatorRegistry = IndicatorCompute


# =============================================================================
# FeatureFrameBuilder
# =============================================================================

class FeatureFrameBuilder:
    """
    Builder that computes features from FeatureSpecSet.

    Given OHLCV data and a FeatureSpecSet, computes all indicators
    in dependency order and returns FeatureArrays.

    Uses IndicatorCompute for computation, allowing backend swapping.

    Usage:
        builder = FeatureFrameBuilder()
        arrays = builder.build(df, spec_set)

        # Access arrays
        ema_20 = arrays.get("ema_20")
        macd_line = arrays.get("macd_macd")  # Multi-output

        # Or with custom compute adapter
        custom_compute = IndicatorCompute()
        custom_compute.register("ema", my_custom_ema)
        builder = FeatureFrameBuilder(compute=custom_compute)

    Performance:
        - All computation is vectorized (via indicator_vendor)
        - Output arrays are float32 for memory efficiency
        - No computation in hot loop
    """

    def __init__(
        self,
        prefer_float32: bool = True,
        compute: IndicatorCompute | None = None,
        registry: IndicatorCompute | None = None,  # Deprecated alias for compute
    ):
        """
        Initialize builder.

        Args:
            prefer_float32: If True, convert arrays to float32 (default: True)
            compute: Custom indicator compute adapter (default: global adapter)
            registry: Deprecated alias for compute (use compute instead)
        """
        self.prefer_float32 = prefer_float32
        # Support both 'compute' and legacy 'registry' parameter
        self.compute = compute or registry or get_compute()
        # Backwards compatibility: keep registry attribute pointing to compute
        self.registry = self.compute
    
    def build(
        self,
        df: pd.DataFrame,
        spec_set: FeatureSpecSet,
        tf_role: str = "exec",
    ) -> FeatureArrays:
        """
        Compute all features from spec_set.
        
        Args:
            df: OHLCV DataFrame with columns: timestamp, open, high, low, close, volume
            spec_set: FeatureSpecSet with indicator specifications
            tf_role: TF role context (exec/htf/mtf) for metadata provenance
            
        Returns:
            FeatureArrays with computed indicators and metadata
            
        Raises:
            KeyError: If an indicator type is not registered
            ValueError: If required feature key is missing from result
        """
        # Import here to avoid circular imports
        from ..runtime.indicator_metadata import (
            IndicatorMetadata,
            canonicalize_params,
            compute_feature_spec_id,
            find_first_valid_idx,
            get_pandas_ta_version,
            get_code_version,
        )
        
        if df.empty:
            return FeatureArrays.empty(spec_set.symbol, spec_set.tf)
        
        # Sort by timestamp to ensure correct order
        df = df.sort_values("timestamp").reset_index(drop=True)
        length = len(df)
        
        # Build intermediate results dict for chained indicators
        computed: dict[str, pd.Series] = {}

        # Metadata collection (key -> IndicatorMetadata)
        metadata_dict: dict[str, IndicatorMetadata] = {}
        
        # Cache version info (computed once per build)
        pandas_ta_ver = get_pandas_ta_version()
        code_ver = get_code_version()
        computed_at = datetime.now(timezone.utc)
        
        # Extract OHLCV columns
        ohlcv = {
            "open": df["open"],
            "high": df["high"],
            "low": df["low"],
            "close": df["close"],
            "volume": df["volume"] if "volume" in df.columns else pd.Series(np.zeros(length)),
        }
        
        # Compute derived sources
        ohlcv["hlc3"] = (ohlcv["high"] + ohlcv["low"] + ohlcv["close"]) / 3
        ohlcv["ohlc4"] = (ohlcv["open"] + ohlcv["high"] + ohlcv["low"] + ohlcv["close"]) / 4
        
        # Get timestamps for metadata (optional)
        timestamps = df["timestamp"].values if "timestamp" in df.columns else None
        
        # Process specs in order (dependencies already validated)
        for spec in spec_set.specs:
            self._compute_and_store_with_metadata(
                spec=spec,
                ohlcv=ohlcv,
                computed=computed,
                metadata_dict=metadata_dict,
                spec_set=spec_set,
                tf_role=tf_role,
                length=length,
                timestamps=timestamps,
                pandas_ta_ver=pandas_ta_ver,
                code_ver=code_ver,
                computed_at=computed_at,
            )
        
        # Convert to numpy arrays (float32 if preferred)
        dtype = np.float32 if self.prefer_float32 else np.float64
        arrays = {}
        for key, series in computed.items():
            arr = series.values.astype(dtype)
            # Ensure C-contiguous for optimal access
            if not arr.flags["C_CONTIGUOUS"]:
                arr = np.ascontiguousarray(arr)
            arrays[key] = arr
        
        # Validate all expected keys are present
        expected_keys = set(spec_set.output_keys)
        actual_keys = set(arrays.keys())
        missing = expected_keys - actual_keys
        if missing:
            raise ValueError(f"Missing required feature keys: {missing}")
        
        return FeatureArrays(
            symbol=spec_set.symbol,
            tf=spec_set.tf,
            arrays=arrays,
            length=length,
            warmup_bars=spec_set.max_warmup_bars,
            metadata=metadata_dict,
        )
    
    def _compute_and_store(
        self,
        spec: FeatureSpec,
        ohlcv: dict[str, pd.Series],
        computed: dict[str, pd.Series],
    ):
        """
        Compute indicator and store results in computed dict.

        Handles both single-output and multi-output indicators.
        NOTE: This method does NOT capture metadata. Use _compute_and_store_with_metadata
        for the full metadata-enabled path.

        Args:
            spec: FeatureSpec to compute
            ohlcv: Dict of OHLCV series
            computed: Dict to store computed indicator series
        """
        ind_type = spec.indicator_type
        ind_type_str = spec.indicator_type.lower()

        # Check if indicator type is registered
        if not self.registry.has(ind_type):
            raise KeyError(
                f"Unknown indicator type: {ind_type_str}. "
                f"Registered types: {self.registry.list_types()}"
            )

        if is_multi_output(ind_type):
            # Multi-output indicator
            result = self._compute_multi_output(spec, ohlcv, computed)
            output_names = get_output_names(ind_type)

            for name in output_names:
                key = spec.get_output_key(name)
                if name in result:
                    computed[key] = result[name]
                else:
                    raise ValueError(
                        f"Multi-output indicator {ind_type_str} did not produce output '{name}'"
                    )
        else:
            # Single-output indicator
            series = self._compute_single_output(spec, ohlcv, computed)
            computed[spec.output_key] = series
    
    def _compute_and_store_with_metadata(
        self,
        spec: FeatureSpec,
        ohlcv: dict[str, pd.Series],
        computed: dict[str, pd.Series],
        metadata_dict: dict[str, "IndicatorMetadata"],
        spec_set: FeatureSpecSet,
        tf_role: str,
        length: int,
        timestamps: np.ndarray | None,
        pandas_ta_ver: str,
        code_ver: str,
        computed_at: datetime,
    ):
        """
        Compute indicator, store results, and capture metadata.
        
        This is the metadata-enabled version of _compute_and_store.
        Creates IndicatorMetadata for each output key at computation time.
        
        For multi-output indicators, all outputs share the same feature_spec_id.
        
        Args:
            spec: FeatureSpec to compute
            ohlcv: Dict of OHLCV series
            computed: Dict to store computed indicator series
            metadata_dict: Dict to store IndicatorMetadata per output key
            spec_set: Parent FeatureSpecSet (for symbol, tf)
            tf_role: TF role context (exec/htf/mtf)
            length: Total number of bars
            timestamps: Optional array of timestamps for start_ts/end_ts
            pandas_ta_ver: pandas_ta version string
            code_ver: Code version (git SHA)
            computed_at: Computation timestamp
        """
        from ..runtime.indicator_metadata import (
            IndicatorMetadata,
            canonicalize_params,
            compute_feature_spec_id,
            find_first_valid_idx,
        )

        ind_type = spec.indicator_type
        ind_type_str = spec.indicator_type.lower()

        # Check if indicator type is registered
        if not self.registry.has(ind_type):
            raise KeyError(
                f"Unknown indicator type: {ind_type_str}. "
                f"Registered types: {self.registry.list_types()}"
            )
        
        # Prepare canonical params for metadata
        params = dict(spec.params) if spec.params else {}
        if spec.length and "length" not in params:
            params["length"] = spec.length
        canonical_params = canonicalize_params(params)
        
        # Get input_source as string
        input_source_str = spec.input_source.value
        if spec.input_source == InputSource.INDICATOR:
            input_source_str = f"indicator:{spec.input_indicator_key}"
        
        # Compute feature_spec_id (shared for multi-output)
        feature_spec_id = compute_feature_spec_id(
            indicator_type=ind_type_str,
            params=canonical_params,
            input_source=input_source_str,
        )
        
        # Helper to create metadata for a single output key
        def create_metadata(output_key: str, arr: np.ndarray) -> IndicatorMetadata:
            first_valid = find_first_valid_idx(arr)
            start_bar_idx = first_valid if first_valid >= 0 else 0
            end_bar_idx = length - 1 if length > 0 else 0
            
            # Timestamps (optional)
            start_ts = None
            end_ts = None
            if timestamps is not None and len(timestamps) > 0:
                try:
                    if start_bar_idx < len(timestamps):
                        ts_val = timestamps[start_bar_idx]
                        if isinstance(ts_val, np.datetime64):
                            start_ts = pd.Timestamp(ts_val).to_pydatetime()
                        elif isinstance(ts_val, datetime):
                            start_ts = ts_val
                    if end_bar_idx < len(timestamps):
                        ts_val = timestamps[end_bar_idx]
                        if isinstance(ts_val, np.datetime64):
                            end_ts = pd.Timestamp(ts_val).to_pydatetime()
                        elif isinstance(ts_val, datetime):
                            end_ts = ts_val
                except Exception:
                    pass  # Timestamps are optional, don't fail
            
            return IndicatorMetadata(
                indicator_key=output_key,
                feature_spec_id=feature_spec_id,
                indicator_type=ind_type_str,
                params=canonical_params,
                input_source=input_source_str,
                symbol=spec_set.symbol,
                tf=spec_set.tf,
                tf_role=tf_role,
                warmup_bars_declared=spec.warmup_bars,
                first_valid_idx_observed=first_valid,
                start_bar_idx=start_bar_idx,
                end_bar_idx=end_bar_idx,
                start_ts=start_ts,
                end_ts=end_ts,
                pandas_ta_version=pandas_ta_ver,
                code_version=code_ver,
                computed_at_utc=computed_at,
            )

        if is_multi_output(ind_type):
            # Multi-output indicator
            result = self._compute_multi_output(spec, ohlcv, computed)
            output_names = get_output_names(ind_type)

            for name in output_names:
                key = spec.get_output_key(name)
                if name in result:
                    series = result[name]
                    computed[key] = series
                    # Create metadata for this output
                    metadata_dict[key] = create_metadata(key, series.values)
                else:
                    raise ValueError(
                        f"Multi-output indicator {ind_type_str} did not produce output '{name}'"
                    )
        else:
            # Single-output indicator
            series = self._compute_single_output(spec, ohlcv, computed)
            key = spec.output_key
            computed[key] = series
            # Create metadata for this output
            metadata_dict[key] = create_metadata(key, series.values)
    
    def _compute_single_output(
        self,
        spec: FeatureSpec,
        ohlcv: dict[str, pd.Series],
        computed: dict[str, pd.Series],
    ) -> pd.Series:
        """
        Compute a single-output indicator from spec.
        
        All indicators are computed dynamically via compute_indicator().
        OHLCV data and params are passed based on the FeatureSpec.
        
        Args:
            spec: FeatureSpec to compute
            ohlcv: Dict of OHLCV series
            computed: Dict of already-computed indicator series
            
        Returns:
            Computed indicator series
        """
        ind_type = spec.indicator_type
        params = dict(spec.params) if spec.params else {}
        
        # Add length from spec if not in params
        if spec.length and "length" not in params:
            params["length"] = spec.length
        
        # Get input series based on spec's input_source
        input_series = self._get_input_series(spec, ohlcv, computed)
        
        # Pass input_series as the primary input - single-input indicators use it directly
        # Multi-input indicators (ATR, MACD) use their own required inputs from registry
        return self.registry.compute(
            ind_type,
            close=input_series,
            high=ohlcv["high"],
            low=ohlcv["low"],
            open_=ohlcv["open"],
            volume=ohlcv.get("volume"),
            **params,
        )
    
    def _compute_multi_output(
        self,
        spec: FeatureSpec,
        ohlcv: dict[str, pd.Series],
        computed: dict[str, pd.Series],
    ) -> dict[str, pd.Series]:
        """
        Compute a multi-output indicator from spec.
        
        All multi-output indicators are computed dynamically via compute_indicator().
        OHLCV data and params are passed based on the FeatureSpec.
        
        Args:
            spec: FeatureSpec to compute
            ohlcv: Dict of OHLCV series
            computed: Dict of already-computed indicator series
            
        Returns:
            Dict of output name -> series
        """
        ind_type = spec.indicator_type
        params = dict(spec.params) if spec.params else {}
        
        # Add length from spec if not in params
        if spec.length and "length" not in params:
            params["length"] = spec.length
        
        # Get input series for indicators that use a primary input
        input_series = self._get_input_series(spec, ohlcv, computed)
        
        # Pass input_series as the primary input - single-input indicators use it directly
        # Multi-input indicators (ATR, MACD) use their own required inputs from registry
        return self.registry.compute(
            ind_type,
            close=input_series,
            high=ohlcv["high"],
            low=ohlcv["low"],
            open_=ohlcv["open"],
            volume=ohlcv.get("volume"),
            **params,
        )
    
    def _get_input_series(
        self,
        spec: FeatureSpec,
        ohlcv: dict[str, pd.Series],
        computed: dict[str, pd.Series],
    ) -> pd.Series:
        """
        Get the input series for an indicator.
        
        Args:
            spec: FeatureSpec
            ohlcv: Dict of OHLCV series
            computed: Dict of computed indicator series
            
        Returns:
            Input series for the indicator
        """
        source = spec.input_source
        
        if source == InputSource.INDICATOR:
            key = spec.input_indicator_key
            if key not in computed:
                raise ValueError(
                    f"Input indicator '{key}' not found for '{spec.output_key}'"
                )
            return computed[key]
        
        # Map source to OHLCV key
        source_map = {
            InputSource.OPEN: "open",
            InputSource.HIGH: "high",
            InputSource.LOW: "low",
            InputSource.CLOSE: "close",
            InputSource.VOLUME: "volume",
            InputSource.HLC3: "hlc3",
            InputSource.OHLC4: "ohlc4",
        }
        
        key = source_map.get(source)
        if key is None:
            raise ValueError(f"Unknown input source: {source}")
        
        return ohlcv[key]
    
    def build_from_specs(
        self,
        df: pd.DataFrame,
        symbol: str,
        tf: str,
        specs: list[FeatureSpec],
        tf_role: str = "exec",
    ) -> FeatureArrays:
        """
        Convenience method to build from a list of specs.
        
        Args:
            df: OHLCV DataFrame
            symbol: Trading symbol
            tf: Timeframe string
            specs: List of FeatureSpecs
            tf_role: TF role context (exec/htf/mtf) for metadata provenance
            
        Returns:
            FeatureArrays with computed indicators and metadata
        """
        spec_set = FeatureSpecSet(symbol=symbol, tf=tf, specs=specs)
        return self.build(df, spec_set, tf_role=tf_role)


def build_features_from_preloaded_dfs(
    idea_card: "IdeaCard",
    dfs: dict[str, pd.DataFrame],
    symbol: str,
) -> dict[str, FeatureArrays]:
    """
    Build FeatureArrays for all TFs defined in an IdeaCard using pre-loaded DataFrames.

    NOTE: For canonical feature building, use build_features_from_idea_card() which
    takes a data_loader and returns IdeaCardFeatures.

    Args:
        idea_card: IdeaCard with TF configs and feature specs
        dfs: Dict mapping tf -> OHLCV DataFrame (pre-loaded)
        symbol: Symbol to build for

    Returns:
        Dict mapping TF role -> FeatureArrays
        e.g., {"exec": FeatureArrays(...), "htf": FeatureArrays(...)}

    Raises:
        ValueError: If required TF data is missing
    """
    builder = FeatureFrameBuilder()
    result: dict[str, FeatureArrays] = {}
    
    for role, tf_config in idea_card.tf_configs.items():
        tf = tf_config.tf
        
        # Check data is available
        if tf not in dfs:
            raise ValueError(
                f"IdeaCard requires {tf} data for '{role}' TF, but it was not provided. "
                f"Available TFs: {list(dfs.keys())}"
            )
        
        df = dfs[tf]
        
        # Get FeatureSpecSet from IdeaCard
        spec_set = idea_card.get_feature_spec_set(role, symbol)
        
        if spec_set is None or not spec_set.specs:
            # No features for this TF - create empty arrays
            result[role] = FeatureArrays.empty(
                symbol=symbol,
                tf=tf,
                length=len(df) if not df.empty else 0,
            )
        else:
            # Build features with tf_role for metadata provenance
            result[role] = builder.build(df, spec_set, tf_role=role)
    
    return result


# =============================================================================
# IdeaCard Feature Building
# =============================================================================

@dataclass
class IdeaCardFeatures:
    """
    Container for features computed from an IdeaCard.
    
    Holds FeatureArrays for each TF role (exec, htf, mtf).
    """
    idea_card_id: str
    symbol: str
    
    # FeatureArrays per TF role
    exec_features: FeatureArrays | None = None
    htf_features: FeatureArrays | None = None
    mtf_features: FeatureArrays | None = None

    # Raw DataFrames per TF (for engine use)
    exec_df: pd.DataFrame | None = None
    htf_df: pd.DataFrame | None = None
    mtf_df: pd.DataFrame | None = None

    def get_features_for_role(self, role: str) -> FeatureArrays | None:
        """Get FeatureArrays for a TF role."""
        if role == "exec":
            return self.exec_features
        elif role == "htf":
            return self.htf_features
        elif role == "mtf":
            return self.mtf_features
        return None
    
    def get_df_for_role(self, role: str) -> pd.DataFrame | None:
        """Get DataFrame for a TF role."""
        if role == "exec":
            return self.exec_df
        elif role == "htf":
            return self.htf_df
        elif role == "mtf":
            return self.mtf_df
        return None


def build_features_from_idea_card(
    idea_card: "IdeaCard",
    data_loader: Callable[[str, str], pd.DataFrame],
    symbol: str | None = None,
    builder: FeatureFrameBuilder | None = None,
) -> IdeaCardFeatures:
    """
    Build all features for an IdeaCard.
    
    Loads data for each TF configured in the IdeaCard and computes
    indicators using FeatureFrameBuilder.
    
    This is the canonical path for feature computation:
    IdeaCard → FeatureSpecSets → FeatureFrameBuilder → FeatureArrays
    
    Args:
        idea_card: The IdeaCard defining features
        data_loader: Function(symbol, tf) -> DataFrame with OHLCV data
        symbol: Override symbol (default: first in symbol_universe)
        builder: Optional FeatureFrameBuilder (default: create new)
        
    Returns:
        IdeaCardFeatures with FeatureArrays per TF role
        
    Raises:
        ValueError: If data_loader returns empty DataFrame
    """
    if symbol is None:
        if not idea_card.symbol_universe:
            raise ValueError("IdeaCard has no symbols in symbol_universe")
        symbol = idea_card.symbol_universe[0]
    
    if builder is None:
        builder = FeatureFrameBuilder()
    
    result = IdeaCardFeatures(
        idea_card_id=idea_card.id,
        symbol=symbol,
    )
    
    # Process each TF role
    for role, tf_config in idea_card.tf_configs.items():
        tf = tf_config.tf
        
        # Load data
        df = data_loader(symbol, tf)
        if df is None or df.empty:
            raise ValueError(
                f"data_loader returned empty data for {symbol} {tf}. "
                f"Ensure data exists before calling build_features_from_idea_card."
            )
        
        # Build FeatureSpecSet from IdeaCard's TFConfig
        spec_set = idea_card.get_feature_spec_set(role, symbol)
        
        if spec_set and spec_set.specs:
            # Compute features with tf_role for metadata provenance
            arrays = builder.build(df, spec_set, tf_role=role)
        else:
            # No features declared for this TF - just use OHLCV
            arrays = FeatureArrays.empty(symbol=symbol, tf=tf, length=len(df))
        
        # Store by role
        if role == "exec":
            result.exec_features = arrays
            result.exec_df = df
        elif role == "htf":
            result.htf_features = arrays
            result.htf_df = df
        elif role == "mtf":
            result.mtf_features = arrays
            result.mtf_df = df
    
    return result