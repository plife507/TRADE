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
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from ..idea_card import IdeaCard

from .feature_spec import (
    FeatureSpec,
    FeatureSpecSet,
    IndicatorType,
    InputSource,
    is_multi_output,
    get_output_names,
)
from ..indicator_vendor import compute_indicator


# Type for indicator compute functions
SingleOutputFn = Callable[..., pd.Series]
MultiOutputFn = Callable[..., Dict[str, pd.Series]]
IndicatorFn = Union[SingleOutputFn, MultiOutputFn]


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
    """
    symbol: str
    tf: str
    arrays: Dict[str, np.ndarray] = field(default_factory=dict)
    length: int = 0
    warmup_bars: int = 0
    
    def __post_init__(self):
        """Validate arrays."""
        for key, arr in self.arrays.items():
            if len(arr) != self.length:
                raise ValueError(
                    f"Array '{key}' length {len(arr)} != expected {self.length}"
                )
    
    def get(self, key: str) -> Optional[np.ndarray]:
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
    
    def keys(self) -> List[str]:
        """Get all output keys."""
        return list(self.arrays.keys())
    
    def has_key(self, key: str) -> bool:
        """Check if key exists."""
        return key in self.arrays
    
    def find_first_valid_index(self, keys: Optional[List[str]] = None) -> int:
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


# =============================================================================
# Indicator Registry
# =============================================================================

class IndicatorRegistry:
    """
    Dynamic registry for computing indicators declared in IdeaCard FeatureSpecs.
    
    **ALL pandas_ta indicators are available dynamically!**
    No static registration needed - indicators are computed on-demand based
    on what the IdeaCard declares in its FeatureSpecs.
    
    Reference: `reference/pandas_ta_repo/` for source code
    
    Usage:
        registry = IndicatorRegistry()
        
        # Compute any indicator dynamically based on IdeaCard FeatureSpec
        ema_series = registry.compute(IndicatorType.EMA, close=close, length=20)
        adx_dict = registry.compute(IndicatorType.ADX, high=high, low=low, close=close, length=14)
        kc_dict = registry.compute(IndicatorType.KC, high=high, low=low, close=close, length=20, scalar=2.0)
        
        # Custom overrides still supported
        registry.register(IndicatorType.EMA, custom_ema_fn)
    """
    
    def __init__(self):
        """Initialize registry (no static registrations - all dynamic)."""
        self._custom_registry: Dict[IndicatorType, IndicatorFn] = {}
    
    def register(self, indicator_type: IndicatorType, fn: IndicatorFn):
        """
        Register a custom compute function for an indicator type.
        
        Use this to override the default pandas_ta implementation
        or add completely custom indicators.
        
        Args:
            indicator_type: Type to register
            fn: Compute function
        """
        self._custom_registry[indicator_type] = fn
    
    def has(self, indicator_type: IndicatorType) -> bool:
        """
        Check if indicator type is available.
        
        Returns True for ALL valid IndicatorType values since
        compute_indicator() handles any pandas_ta indicator dynamically.
        """
        return isinstance(indicator_type, IndicatorType)
    
    def compute(
        self,
        indicator_type: IndicatorType,
        close: Optional[pd.Series] = None,
        high: Optional[pd.Series] = None,
        low: Optional[pd.Series] = None,
        open_: Optional[pd.Series] = None,
        volume: Optional[pd.Series] = None,
        **kwargs,
    ) -> Union[pd.Series, Dict[str, pd.Series]]:
        """
        Compute an indicator dynamically.
        
        Uses pandas_ta compute_indicator() to handle ANY indicator type
        declared in the IdeaCard's FeatureSpecs. Custom overrides take
        precedence if registered.
        
        Args:
            indicator_type: Type to compute (from IndicatorType enum)
            close: Close price series
            high: High price series
            low: Low price series
            open_: Open price series
            volume: Volume series
            **kwargs: Indicator-specific parameters (length, fast, slow, etc.)
            
        Returns:
            pd.Series for single-output, Dict[str, pd.Series] for multi-output
        """
        # Check for custom override first
        if indicator_type in self._custom_registry:
            fn = self._custom_registry[indicator_type]
            return fn(close=close, high=high, low=low, open_=open_, volume=volume, **kwargs)
        
        # Dynamic computation for ALL indicators via compute_indicator()
        return compute_indicator(
            indicator_name=indicator_type.value,
            close=close,
            high=high,
            low=low,
            open_=open_,
            volume=volume,
            **kwargs,
        )
    
    def list_types(self) -> List[IndicatorType]:
        """List all available indicator types (all IndicatorType enum values)."""
        return list(IndicatorType)
    
    def list_custom_overrides(self) -> List[IndicatorType]:
        """List indicator types with custom overrides registered."""
        return list(self._custom_registry.keys())


# Global registry instance
_default_registry = IndicatorRegistry()


def get_registry() -> IndicatorRegistry:
    """Get the default indicator registry."""
    return _default_registry


# =============================================================================
# FeatureFrameBuilder
# =============================================================================

class FeatureFrameBuilder:
    """
    Builder that computes features from FeatureSpecSet.
    
    Given OHLCV data and a FeatureSpecSet, computes all indicators
    in dependency order and returns FeatureArrays.
    
    Uses the IndicatorRegistry for computation, allowing backend swapping.
    
    Usage:
        builder = FeatureFrameBuilder()
        arrays = builder.build(df, spec_set)
        
        # Access arrays
        ema_20 = arrays.get("ema_20")
        macd_line = arrays.get("macd_macd")  # Multi-output
        
        # Or with custom registry
        custom_registry = IndicatorRegistry()
        custom_registry.register(IndicatorType.EMA, my_custom_ema)
        builder = FeatureFrameBuilder(registry=custom_registry)
    
    Performance:
        - All computation is vectorized (via indicator_vendor)
        - Output arrays are float32 for memory efficiency
        - No computation in hot loop
    """
    
    def __init__(
        self,
        prefer_float32: bool = True,
        registry: Optional[IndicatorRegistry] = None,
    ):
        """
        Initialize builder.
        
        Args:
            prefer_float32: If True, convert arrays to float32 (default: True)
            registry: Custom indicator registry (default: global registry)
        """
        self.prefer_float32 = prefer_float32
        self.registry = registry or get_registry()
    
    def build(
        self,
        df: pd.DataFrame,
        spec_set: FeatureSpecSet,
    ) -> FeatureArrays:
        """
        Compute all features from spec_set.
        
        Args:
            df: OHLCV DataFrame with columns: timestamp, open, high, low, close, volume
            spec_set: FeatureSpecSet with indicator specifications
            
        Returns:
            FeatureArrays with computed indicators
            
        Raises:
            KeyError: If an indicator type is not registered
            ValueError: If required feature key is missing from result
        """
        if df.empty:
            return FeatureArrays(
                symbol=spec_set.symbol,
                tf=spec_set.tf,
                arrays={},
                length=0,
                warmup_bars=0,
            )
        
        # Sort by timestamp to ensure correct order
        df = df.sort_values("timestamp").reset_index(drop=True)
        length = len(df)
        
        # Build intermediate results dict for chained indicators
        computed: Dict[str, pd.Series] = {}
        
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
        
        # Process specs in order (dependencies already validated)
        for spec in spec_set.specs:
            self._compute_and_store(spec, ohlcv, computed)
        
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
        )
    
    def _compute_and_store(
        self,
        spec: FeatureSpec,
        ohlcv: Dict[str, pd.Series],
        computed: Dict[str, pd.Series],
    ):
        """
        Compute indicator and store results in computed dict.
        
        Handles both single-output and multi-output indicators.
        
        Args:
            spec: FeatureSpec to compute
            ohlcv: Dict of OHLCV series
            computed: Dict to store computed indicator series
        """
        ind_type = spec.indicator_type
        
        # Check if indicator type is registered
        if not self.registry.has(ind_type):
            raise KeyError(
                f"Unknown indicator type: {ind_type.value}. "
                f"Registered types: {[t.value for t in self.registry.list_types()]}"
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
                        f"Multi-output indicator {ind_type.value} did not produce output '{name}'"
                    )
        else:
            # Single-output indicator
            series = self._compute_single_output(spec, ohlcv, computed)
            computed[spec.output_key] = series
    
    def _compute_single_output(
        self,
        spec: FeatureSpec,
        ohlcv: Dict[str, pd.Series],
        computed: Dict[str, pd.Series],
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
        
        # Dynamic computation - pass all OHLCV data, indicator will use what it needs
        return self.registry.compute(
            ind_type,
            close=input_series if spec.input_source == InputSource.CLOSE else ohlcv["close"],
            high=ohlcv["high"],
            low=ohlcv["low"],
            open_=ohlcv["open"],
            volume=ohlcv.get("volume"),
            **params,
        )
    
    def _compute_multi_output(
        self,
        spec: FeatureSpec,
        ohlcv: Dict[str, pd.Series],
        computed: Dict[str, pd.Series],
    ) -> Dict[str, pd.Series]:
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
        
        # Dynamic computation - pass all OHLCV data, indicator will use what it needs
        return self.registry.compute(
            ind_type,
            close=input_series if spec.input_source == InputSource.CLOSE else ohlcv["close"],
            high=ohlcv["high"],
            low=ohlcv["low"],
            open_=ohlcv["open"],
            volume=ohlcv.get("volume"),
            **params,
        )
    
    def _get_input_series(
        self,
        spec: FeatureSpec,
        ohlcv: Dict[str, pd.Series],
        computed: Dict[str, pd.Series],
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
        specs: List[FeatureSpec],
    ) -> FeatureArrays:
        """
        Convenience method to build from a list of specs.
        
        Args:
            df: OHLCV DataFrame
            symbol: Trading symbol
            tf: Timeframe string
            specs: List of FeatureSpecs
            
        Returns:
            FeatureArrays with computed indicators
        """
        spec_set = FeatureSpecSet(symbol=symbol, tf=tf, specs=specs)
        return self.build(df, spec_set)


def build_features_from_idea_card(
    idea_card: "IdeaCard",
    dfs: Dict[str, pd.DataFrame],
    symbol: str,
) -> Dict[str, FeatureArrays]:
    """
    Build FeatureArrays for all TFs defined in an IdeaCard.
    
    Args:
        idea_card: IdeaCard with TF configs and feature specs
        dfs: Dict mapping tf -> OHLCV DataFrame
        symbol: Symbol to build for
        
    Returns:
        Dict mapping TF role -> FeatureArrays
        e.g., {"exec": FeatureArrays(...), "htf": FeatureArrays(...)}
        
    Raises:
        ValueError: If required TF data is missing
    """
    builder = FeatureFrameBuilder()
    result: Dict[str, FeatureArrays] = {}
    
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
            result[role] = FeatureArrays(
                symbol=symbol,
                tf=tf,
                arrays={},
                length=len(df) if not df.empty else 0,
                warmup_bars=0,
            )
        else:
            # Build features
            result[role] = builder.build(df, spec_set)
    
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
    exec_features: Optional[FeatureArrays] = None
    htf_features: Optional[FeatureArrays] = None
    mtf_features: Optional[FeatureArrays] = None
    
    # Raw DataFrames per TF (for engine use)
    exec_df: Optional[pd.DataFrame] = None
    htf_df: Optional[pd.DataFrame] = None
    mtf_df: Optional[pd.DataFrame] = None
    
    def get_features_for_role(self, role: str) -> Optional[FeatureArrays]:
        """Get FeatureArrays for a TF role."""
        if role == "exec":
            return self.exec_features
        elif role == "htf":
            return self.htf_features
        elif role == "mtf":
            return self.mtf_features
        return None
    
    def get_df_for_role(self, role: str) -> Optional[pd.DataFrame]:
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
    symbol: Optional[str] = None,
    builder: Optional[FeatureFrameBuilder] = None,
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
            # Compute features
            arrays = builder.build(df, spec_set)
        else:
            # No features declared for this TF - just use OHLCV
            arrays = FeatureArrays(
                symbol=symbol,
                tf=tf,
                arrays={},
                length=len(df),
                warmup_bars=0,
            )
        
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