"""
Indicator vendor wrapper.

This is the ONLY module in the project that imports pandas_ta directly.
All other code must use these wrapper functions.

The wrapper normalizes parameter names and ensures output Series are aligned with input indices.

**Indicator Availability:**
- pandas_ta provides 150+ technical indicators (all available via dynamic wrapper)
- Reference repo: `reference/pandas_ta_repo/`
- Reference doc: `reference/pandas_ta/INDICATORS_REFERENCE.md`

Backend Abstraction:
    This module provides the abstraction layer for swapping TA libraries.
    Currently uses pandas_ta. All 150+ indicators are accessible via the
    dynamic wrapper `compute_indicator()` which handles both single-output
    and multi-output indicators automatically.

    Specific wrapper functions (ema, sma, rsi, etc.) are kept for backward
    compatibility and explicit parameter documentation.
"""

from __future__ import annotations
import pandas as pd
from dataclasses import dataclass, field
from typing import Any

# Backend import - ONLY place pandas_ta is imported
import pandas_ta as ta


# =============================================================================
# Structured Canonicalization Result (Single Source of Truth)
# =============================================================================

@dataclass
class CanonicalizeResult:
    """
    Structured result from canonicalizing pandas_ta multi-output columns.

    This is the single source of truth for output key mapping, used by:
    - Vendor multi-output normalization
    - Toolkit contract audit
    - Snapshot parity audit
    """
    indicator_type: str
    raw_columns: list[str]
    raw_to_canonical: dict[str, str]
    canonical_columns: list[str]
    declared_columns: list[str]
    extras_dropped: list[str] = field(default_factory=list)
    missing_declared: list[str] = field(default_factory=list)
    collisions: dict[str, list[str]] = field(default_factory=dict)  # canonical_key -> [raw_cols]

    @property
    def has_collisions(self) -> bool:
        return len(self.collisions) > 0

    @property
    def has_missing(self) -> bool:
        return len(self.missing_declared) > 0

    @property
    def is_valid(self) -> bool:
        """Valid if no collisions and no missing declared outputs."""
        return not self.has_collisions and not self.has_missing


def canonicalize_indicator_outputs(
    indicator_type: str,
    raw_columns: list[str],
) -> CanonicalizeResult:
    """
    Canonicalize pandas_ta raw column names to registry-declared output keys.

    This is the SINGLE canonicalization implementation used everywhere:
    - Vendor multi-output normalization
    - Toolkit contract audit
    - Snapshot parity audit

    Args:
        indicator_type: Name of the indicator (e.g., 'macd', 'adx', 'bbands')
        raw_columns: List of raw pandas_ta column names

    Returns:
        CanonicalizeResult with all structured data for contract validation

    Error codes raised:
        CANONICAL_COLLISION: Multiple raw columns map to the same canonical key
        MISSING_DECLARED_OUTPUTS: Registry-declared outputs not produced
    """
    from .registry import get_registry
    registry = get_registry()

    # Get registry-declared outputs
    if registry.is_multi_output(indicator_type):
        declared_columns = list(registry.get_output_suffixes(indicator_type))
    else:
        # Single-output indicators don't have explicit output keys
        declared_columns = []

    # Map raw columns to canonical keys
    raw_to_canonical: dict[str, str] = {}
    canonical_to_raw: dict[str, list[str]] = {}

    for raw_col in raw_columns:
        canonical_key = _extract_column_key(raw_col, indicator_type)
        raw_to_canonical[raw_col] = canonical_key

        if canonical_key not in canonical_to_raw:
            canonical_to_raw[canonical_key] = []
        canonical_to_raw[canonical_key].append(raw_col)

    # Detect collisions (multiple raw columns -> same canonical key)
    collisions = {
        canonical_key: raw_cols
        for canonical_key, raw_cols in canonical_to_raw.items()
        if len(raw_cols) > 1
    }

    # Get produced canonical columns
    canonical_columns = list(raw_to_canonical.values())
    canonical_set = set(canonical_columns)
    declared_set = set(declared_columns)

    # Detect extras (produced but not declared)
    extras_dropped = [k for k in canonical_columns if k not in declared_set]

    # Detect missing (declared but not produced)
    missing_declared = [k for k in declared_columns if k not in canonical_set]

    return CanonicalizeResult(
        indicator_type=indicator_type,
        raw_columns=list(raw_columns),
        raw_to_canonical=raw_to_canonical,
        canonical_columns=canonical_columns,
        declared_columns=declared_columns,
        extras_dropped=extras_dropped,
        missing_declared=missing_declared,
        collisions=collisions,
    )


# =============================================================================
# Special Indicator Handlers
# =============================================================================


def _compute_vwap_with_datetime_index(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
    ts_open: pd.Series | None = None,
    **kwargs
) -> pd.Series:
    """
    Compute VWAP with DatetimeIndex required by pandas_ta.

    pandas_ta's vwap() requires an ordered DatetimeIndex to determine session
    boundaries (daily reset by default). This function:
    1. Creates a temporary DataFrame with DatetimeIndex from ts_open
    2. Computes VWAP
    3. Resets to original integer index

    Args:
        high, low, close, volume: Price series with integer index
        ts_open: Bar open timestamps (int64 milliseconds or datetime)
        **kwargs: VWAP params (anchor, etc.)

    Returns:
        VWAP Series with original integer index
    """
    original_index = close.index

    if ts_open is None:
        # No timestamps available - return NaN Series with warning
        import warnings
        warnings.warn(
            "VWAP requires timestamps (ts_open) for session boundaries. "
            "Returning NaN series. Pass ts_open to compute_indicator for VWAP.",
            UserWarning
        )
        return pd.Series(index=original_index, dtype=float)

    # Convert ts_open to DatetimeIndex
    if pd.api.types.is_integer_dtype(ts_open):
        # Millisecond timestamps
        dt_index = pd.to_datetime(ts_open, unit='ms', utc=True)
    else:
        dt_index = pd.to_datetime(ts_open, utc=True)

    # Create DataFrame with DatetimeIndex
    df = pd.DataFrame({
        'high': high.values,
        'low': low.values,
        'close': close.values,
        'volume': volume.values,
    }, index=dt_index)

    # Compute VWAP
    vwap_result = ta.vwap(df['high'], df['low'], df['close'], df['volume'], **kwargs)

    if vwap_result is None:
        return pd.Series(index=original_index, dtype=float)

    # Reset to original integer index
    result = pd.Series(vwap_result.values, index=original_index)
    return result


# =============================================================================
# Dynamic Indicator Wrapper (handles ALL pandas_ta indicators)
# =============================================================================

def compute_indicator(
    indicator_name: str,
    close: pd.Series | None = None,
    high: pd.Series | None = None,
    low: pd.Series | None = None,
    open_: pd.Series | None = None,
    volume: pd.Series | None = None,
    ts_open: pd.Series | None = None,
    **kwargs
) -> pd.Series | dict[str, pd.Series]:
    """
    Dynamic wrapper for supported indicators (FAIL LOUD on unsupported).

    Uses IndicatorRegistry to determine input requirements. Only indicators
    explicitly declared in the registry are allowed - no heuristic fallbacks.

    Args:
        indicator_name: Name of the indicator (e.g., 'ema', 'macd', 'adx')
        close: Close price series
        high: High price series
        low: Low price series
        open_: Open price series
        volume: Volume series
        ts_open: Bar open timestamps (required for VWAP session boundaries)
        **kwargs: Indicator-specific parameters (length, fast, slow, etc.)

    Returns:
        pd.Series for single-output indicators
        dict[str, pd.Series] for multi-output indicators (column names normalized)

    Raises:
        ValueError: If indicator_name is not in IndicatorRegistry (UNSUPPORTED_INDICATOR_TYPE)

    Example:
        # Single-output
        ema_result = compute_indicator('ema', close=close, length=20)

        # Multi-output
        macd_result = compute_indicator('macd', close=close, fast=12, slow=26, signal=9)
        # Returns: {'macd': Series, 'signal': Series, 'histogram': Series}

        # With high/low/close
        adx_result = compute_indicator('adx', high=high, low=low, close=close, length=14)
        # Returns: {'adx': Series, 'dmp': Series, 'dmn': Series}
    """
    # Get the indicator function from pandas_ta
    indicator_fn = getattr(ta, indicator_name, None)
    if indicator_fn is None:
        raise ValueError(f"Unknown indicator: {indicator_name}. Check pandas_ta documentation.")

    # Get registry for input requirements (FAIL LOUD - no fallback)
    from .registry import get_registry
    registry = get_registry()

    # Determine input requirements - FAIL LOUD if not in registry
    if not registry.is_supported(indicator_name):
        supported = registry.list_indicators()
        raise ValueError(
            f"UNSUPPORTED_INDICATOR_TYPE: '{indicator_name}' is not in IndicatorRegistry. "
            f"Supported: {supported}. "
            f"Run 'backtest indicators --print-keys' for available indicators."
        )

    # Use registry-defined inputs (only path - no fallback)
    info = registry.get_indicator_info(indicator_name)
    required_inputs = info.input_series

    # Build positional args based on what the registry says the indicator needs
    # The order matters for pandas_ta: high, low, close, open, volume (standard order)
    positional_args = []

    if "high" in required_inputs:
        if high is None:
            raise ValueError(f"Indicator '{indicator_name}' requires 'high' price series")
        positional_args.append(high)

    if "low" in required_inputs:
        if low is None:
            raise ValueError(f"Indicator '{indicator_name}' requires 'low' price series")
        positional_args.append(low)

    if "close" in required_inputs:
        if close is None:
            raise ValueError(f"Indicator '{indicator_name}' requires 'close' price series")
        positional_args.append(close)

    if "open" in required_inputs:
        if open_ is None:
            raise ValueError(f"Indicator '{indicator_name}' requires 'open' price series")
        positional_args.append(open_)

    if "volume" in required_inputs:
        if volume is None:
            raise ValueError(f"Indicator '{indicator_name}' requires 'volume' series")
        positional_args.append(volume)

    # If no required inputs specified (close-only indicators), use close
    if not positional_args:
        if close is None:
            raise ValueError(f"Indicator '{indicator_name}' requires at least 'close' price series")
        positional_args.append(close)

    # Special handling for VWAP: requires DatetimeIndex for session boundaries
    if indicator_name == "vwap":
        result = _compute_vwap_with_datetime_index(
            high=high, low=low, close=close, volume=volume, ts_open=ts_open, **kwargs
        )
    else:
        # Compute indicator
        result = indicator_fn(*positional_args, **kwargs)

    if result is None:
        # Return empty Series with correct index
        index = close.index if close is not None else (high.index if high is not None else pd.RangeIndex(0))
        return pd.Series(index=index, dtype=float)

    # Handle result type
    if isinstance(result, pd.DataFrame):
        # Multi-output: normalize column names
        return _normalize_multi_output(result, indicator_name)
    elif isinstance(result, pd.Series):
        # Single-output
        return result
    else:
        raise ValueError(f"Unexpected result type from {indicator_name}: {type(result)}")


def _normalize_multi_output(df: pd.DataFrame, indicator_name: str) -> dict[str, pd.Series]:
    """
    Normalize multi-output DataFrame column names to registry-declared keys.

    Enforces the contract:
    - FAIL LOUD on canonical collisions
    - FAIL LOUD on missing declared outputs
    - DROP extras (not returned, but they were computed)

    pandas_ta returns columns like 'MACD_12_26_9', 'MACDh_12_26_9', 'MACDs_12_26_9'.
    We normalize these to 'macd', 'histogram', 'signal' for consistent access.
    """
    # Use the structured canonicalizer
    canon_result = canonicalize_indicator_outputs(indicator_name, list(df.columns))

    # FAIL LOUD on collisions
    if canon_result.has_collisions:
        collision_details = "; ".join(
            f"{canonical_key} <- {raw_cols}"
            for canonical_key, raw_cols in canon_result.collisions.items()
        )
        raise ValueError(
            f"CANONICAL_COLLISION: Indicator '{indicator_name}' has multiple raw columns "
            f"mapping to the same canonical key. Collisions: {collision_details}"
        )

    # FAIL LOUD on missing declared outputs
    if canon_result.has_missing:
        raise ValueError(
            f"MISSING_DECLARED_OUTPUTS: Indicator '{indicator_name}' did not produce "
            f"registry-declared outputs: {canon_result.missing_declared}. "
            f"Produced: {canon_result.canonical_columns}, "
            f"Declared: {canon_result.declared_columns}"
        )

    # Build result with only declared outputs (drop extras)
    result = {}
    declared_set = set(canon_result.declared_columns)

    for raw_col, canonical_key in canon_result.raw_to_canonical.items():
        if canonical_key in declared_set:
            result[canonical_key] = df[raw_col]
        # else: extra output, dropped (not in declared_set)

    return result


def _extract_column_key(col_name: str, indicator_name: str) -> str:
    """
    Extract a simple key from a pandas_ta column name.

    Examples:
        'MACD_12_26_9' -> 'macd'
        'MACDh_12_26_9' -> 'histogram'
        'MACDs_12_26_9' -> 'signal'
        'ADX_14' -> 'adx'
        'DMP_14' -> 'dmp'
        'BBL_20_2.0' -> 'lower'
        'STOCHk_14_3_3' -> 'k'
    """
    col_lower = col_name.lower()

    # Special mappings for common indicators
    column_mappings = {
        # TRIX
        'trixs': 'signal',
        # PPO
        'ppoh': 'histogram',
        'ppos': 'signal',
        # MACD
        'macdh': 'histogram',
        'macds': 'signal',
        # Bollinger Bands
        'bbl': 'lower',
        'bbm': 'middle',
        'bbu': 'upper',
        'bbb': 'bandwidth',
        'bbp': 'percent_b',
        # Stochastic
        'stochk': 'k',
        'stochd': 'd',
        'stochrsik': 'k',
        'stochrsid': 'd',
        # Keltner Channel (kcle/kcbe/kcue for EMA variant)
        'kcl': 'lower',
        'kcle': 'lower',
        'kcb': 'basis',
        'kcbe': 'basis',
        'kcu': 'upper',
        'kcue': 'upper',
        # Donchian
        'dcl': 'lower',
        'dcm': 'middle',
        'dcu': 'upper',
        # ADX
        'adx': 'adx',
        'adxr': 'adxr',
        'dmp': 'dmp',
        'dmn': 'dmn',
        # Aroon
        'aroonu': 'up',
        'aroond': 'down',
        'aroono': 'osc',
        'aroonosc': 'osc',
        # Vortex
        'vtxp': 'vip',
        'vtxm': 'vim',
        # PSAR
        'psarl': 'long',
        'psars': 'short',
        'psaraf': 'af',
        'psarr': 'reversal',
        # Supertrend
        'supert': 'trend',
        'supertd': 'direction',
        'supertl': 'long',
        'superts': 'short',
        # KDJ
        'k': 'k',
        'd': 'd',
        'j': 'j',
        # Fisher
        'fishert': 'fisher',
        'fisherts': 'signal',
        # TSI
        'tsi': 'tsi',
        'tsis': 'signal',
        # KVO
        'kvo': 'kvo',
        'kvos': 'signal',
        # Squeeze (multiple outputs: sqz value, on/off indicators)
        # Columns: SQZ_ON, SQZ_OFF, SQZ_NO, SQZ_20_2.0_20_1.5 (main value)
        'sqz_on': 'on',
        'sqz_off': 'off',
        'sqz_no': 'no_sqz',
        # Heikin-Ashi
        'ha_open': 'open',
        'ha_high': 'high',
        'ha_low': 'low',
        'ha_close': 'close',
        # Ichimoku (simplified)
        'isa': 'isa',
        'isb': 'isb',
        'its': 'its',
        'iks': 'iks',
        'ics': 'ics',
    }

    # First try to match a known prefix
    for prefix, key in column_mappings.items():
        if col_lower.startswith(prefix):
            # Check if it's followed by underscore and numbers
            rest = col_lower[len(prefix):]
            if rest == '' or rest.startswith('_'):
                return key

    # If not found in mappings, use the part before first underscore
    parts = col_lower.split('_')
    if len(parts) > 0:
        return parts[0]

    return col_lower


def get_available_indicators() -> list[str]:
    """
    Get list of all available pandas_ta indicators.

    Returns:
        List of indicator names that can be used with compute_indicator()
    """
    # Get all callable attributes from pandas_ta that aren't private/utility
    excluded = {
        'help', 'version', 'indicators', 'study', 'Strategy', 'AnalysisIndicators',
        'Study', 'camelCase2Title', 'category_files', 'create_dir', 'import_dir',
        'get_time', 'final_time', 'total_time', 'ms2secs', 'to_utc', 'unix_convert',
        'combination', 'simplify_columns', 'speed_test', 'pascals_triangle',
        'symmetric_triangle', 'weights', 'remap', 'strided_window', 'signed_series',
        'unsigned_differences', 'sum_signed_rolling_deltas', 'non_zero_range'
    }

    indicators = []
    for name in dir(ta):
        if name.startswith('_'):
            continue
        if name.startswith('v_') or name.startswith('df_') or name.startswith('nb_'):
            continue
        if name in excluded:
            continue
        attr = getattr(ta, name)
        if callable(attr):
            indicators.append(name)

    return sorted(indicators)


# =============================================================================
# Single-Output Indicators
# =============================================================================

def ema(close: pd.Series, length: int) -> pd.Series:
    """
    Compute Exponential Moving Average.

    Warmup: ~2-3x length for stabilization (theoretical: length-1)

    Args:
        close: Close price series
        length: EMA period

    Returns:
        EMA series aligned with input index
    """
    result = ta.ema(close, length=length)
    if result is None:
        return pd.Series(index=close.index, dtype=float)
    return result


def sma(close: pd.Series, length: int) -> pd.Series:
    """
    Compute Simple Moving Average.

    Warmup: exactly length-1 bars

    Args:
        close: Close price series
        length: SMA period

    Returns:
        SMA series aligned with input index
    """
    result = ta.sma(close, length=length)
    if result is None:
        return pd.Series(index=close.index, dtype=float)
    return result


def rsi(close: pd.Series, length: int) -> pd.Series:
    """
    Compute Relative Strength Index.

    Warmup: length + 1 (needs first price delta)

    Args:
        close: Close price series
        length: RSI period

    Returns:
        RSI series (0-100 scale) aligned with input index
    """
    result = ta.rsi(close, length=length)
    if result is None:
        return pd.Series(index=close.index, dtype=float)
    return result


def atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int) -> pd.Series:
    """
    Compute Average True Range.

    Warmup: length + 1 (needs previous close for true range)

    Args:
        high: High price series
        low: Low price series
        close: Close price series
        length: ATR period

    Returns:
        ATR series aligned with input index
    """
    result = ta.atr(high, low, close, length=length)
    if result is None:
        return pd.Series(index=close.index, dtype=float)
    return result


# =============================================================================
# Multi-Output Indicators
# =============================================================================

def macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> dict[str, pd.Series]:
    """
    Compute MACD (Moving Average Convergence Divergence).

    Warmup: slow + signal (for signal line to stabilize)

    Args:
        close: Close price series
        fast: Fast EMA period (default: 12)
        slow: Slow EMA period (default: 26)
        signal: Signal EMA period (default: 9)

    Returns:
        Dict with keys: 'macd', 'signal', 'histogram'
    """
    result = ta.macd(close, fast=fast, slow=slow, signal=signal)

    if result is None or result.empty:
        empty = pd.Series(index=close.index, dtype=float)
        return {"macd": empty.copy(), "signal": empty.copy(), "histogram": empty.copy()}

    # pandas_ta returns DataFrame with columns like MACD_12_26_9, MACDh_12_26_9, MACDs_12_26_9
    macd_col = f"MACD_{fast}_{slow}_{signal}"
    hist_col = f"MACDh_{fast}_{slow}_{signal}"
    signal_col = f"MACDs_{fast}_{slow}_{signal}"

    return {
        "macd": result[macd_col] if macd_col in result.columns else pd.Series(index=close.index, dtype=float),
        "signal": result[signal_col] if signal_col in result.columns else pd.Series(index=close.index, dtype=float),
        "histogram": result[hist_col] if hist_col in result.columns else pd.Series(index=close.index, dtype=float),
    }


def bbands(
    close: pd.Series,
    length: int = 20,
    std: float = 2.0,
) -> dict[str, pd.Series]:
    """
    Compute Bollinger Bands.

    Warmup: length (same as SMA)

    Args:
        close: Close price series
        length: SMA period (default: 20)
        std: Standard deviation multiplier (default: 2.0)

    Returns:
        Dict with keys: 'upper', 'middle', 'lower', 'bandwidth', 'percent_b'
    """
    result = ta.bbands(close, length=length, std=std)

    if result is None or result.empty:
        empty = pd.Series(index=close.index, dtype=float)
        return {
            "upper": empty.copy(),
            "middle": empty.copy(),
            "lower": empty.copy(),
            "bandwidth": empty.copy(),
            "percent_b": empty.copy(),
        }

    # pandas_ta returns columns like BBL_20_2.0_2.0 (length_lower_std_upper_std)
    # Format: BB{L/M/U/B/P}_{length}_{lower_std}_{upper_std}
    # NOTE: pandas_ta always uses float format (2.0) even if int (2) is passed
    std_str = f"{float(std)}"
    lower_col = f"BBL_{length}_{std_str}_{std_str}"
    middle_col = f"BBM_{length}_{std_str}_{std_str}"
    upper_col = f"BBU_{length}_{std_str}_{std_str}"
    bw_col = f"BBB_{length}_{std_str}_{std_str}"
    pct_col = f"BBP_{length}_{std_str}_{std_str}"

    empty = pd.Series(index=close.index, dtype=float)
    return {
        "upper": result[upper_col] if upper_col in result.columns else empty.copy(),
        "middle": result[middle_col] if middle_col in result.columns else empty.copy(),
        "lower": result[lower_col] if lower_col in result.columns else empty.copy(),
        "bandwidth": result[bw_col] if bw_col in result.columns else empty.copy(),
        "percent_b": result[pct_col] if pct_col in result.columns else empty.copy(),
    }


def stoch(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    k: int = 14,
    d: int = 3,
    smooth_k: int = 3,
) -> dict[str, pd.Series]:
    """
    Compute Stochastic Oscillator.

    Warmup: k + smooth_k + d

    Args:
        high: High price series
        low: Low price series
        close: Close price series
        k: %K lookback period (default: 14)
        d: %D smoothing period (default: 3)
        smooth_k: %K smoothing period (default: 3)

    Returns:
        Dict with keys: 'k', 'd'
    """
    result = ta.stoch(high, low, close, k=k, d=d, smooth_k=smooth_k)

    if result is None or result.empty:
        empty = pd.Series(index=close.index, dtype=float)
        return {"k": empty.copy(), "d": empty.copy()}

    # pandas_ta returns columns like STOCHk_14_3_3, STOCHd_14_3_3
    k_col = f"STOCHk_{k}_{d}_{smooth_k}"
    d_col = f"STOCHd_{k}_{d}_{smooth_k}"

    empty = pd.Series(index=close.index, dtype=float)
    return {
        "k": result[k_col] if k_col in result.columns else empty.copy(),
        "d": result[d_col] if d_col in result.columns else empty.copy(),
    }


def stochrsi(
    close: pd.Series,
    length: int = 14,
    rsi_length: int = 14,
    k: int = 3,
    d: int = 3,
) -> dict[str, pd.Series]:
    """
    Compute Stochastic RSI.

    Warmup: rsi_length + length + max(k, d)

    Args:
        close: Close price series
        length: Stochastic lookback on RSI (default: 14)
        rsi_length: RSI period (default: 14)
        k: %K smoothing period (default: 3)
        d: %D smoothing period (default: 3)

    Returns:
        Dict with keys: 'k', 'd'
    """
    result = ta.stochrsi(close, length=length, rsi_length=rsi_length, k=k, d=d)

    if result is None or result.empty:
        empty = pd.Series(index=close.index, dtype=float)
        return {"k": empty.copy(), "d": empty.copy()}

    # pandas_ta returns columns like STOCHRSIk_14_14_3_3, STOCHRSId_14_14_3_3
    k_col = f"STOCHRSIk_{length}_{rsi_length}_{k}_{d}"
    d_col = f"STOCHRSId_{length}_{rsi_length}_{k}_{d}"

    empty = pd.Series(index=close.index, dtype=float)
    return {
        "k": result[k_col] if k_col in result.columns else empty.copy(),
        "d": result[d_col] if d_col in result.columns else empty.copy(),
    }


# =============================================================================
# Warmup Calculation
# =============================================================================
# CANONICAL SOURCE: Warmup bars are computed via IndicatorRegistry.get_warmup_bars()
# in src/indicators/registry.py. Use FeatureSpec.warmup_bars property
# or registry.get_warmup_bars(indicator_type, params) for warmup calculations.
#
# Dead code removed: get_ema_warmup, get_sma_warmup, get_rsi_warmup, get_atr_warmup,
# get_macd_warmup, get_bbands_warmup, get_stoch_warmup, get_stochrsi_warmup
# These were shadowing the registry implementations and never called.
