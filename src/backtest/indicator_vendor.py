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
from typing import Dict, Tuple, Union, Any, Optional, List

# Backend import - ONLY place pandas_ta is imported
import pandas_ta as ta


# =============================================================================
# Dynamic Indicator Wrapper (handles ALL pandas_ta indicators)
# =============================================================================

def compute_indicator(
    indicator_name: str,
    close: Optional[pd.Series] = None,
    high: Optional[pd.Series] = None,
    low: Optional[pd.Series] = None,
    open_: Optional[pd.Series] = None,
    volume: Optional[pd.Series] = None,
    **kwargs
) -> Union[pd.Series, Dict[str, pd.Series]]:
    """
    Dynamic wrapper for supported indicators.
    
    Uses IndicatorRegistry to determine input requirements (not hardcoded sets).
    For supported indicators, validates params and uses registry-defined inputs.
    For unsupported indicators, falls back to heuristic detection.
    
    Args:
        indicator_name: Name of the indicator (e.g., 'ema', 'macd', 'adx')
        close: Close price series
        high: High price series
        low: Low price series
        open_: Open price series
        volume: Volume series
        **kwargs: Indicator-specific parameters (length, fast, slow, etc.)
        
    Returns:
        pd.Series for single-output indicators
        Dict[str, pd.Series] for multi-output indicators (column names normalized)
        
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
    
    # Try to use registry for input requirements (preferred path)
    from .indicator_registry import get_registry
    registry = get_registry()
    
    # Determine input requirements
    if registry.is_supported(indicator_name):
        # Use registry-defined inputs
        info = registry.get_indicator_info(indicator_name)
        input_series = info.input_series
        needs_hlc = info.requires_hlc
        needs_volume = info.requires_volume
    else:
        # Fallback for unsupported indicators (legacy heuristic)
        needs_hlc = indicator_name in {
            'atr', 'true_range', 'natr', 'adx', 'aroon', 'chop', 'cksp', 'dm',
            'kc', 'donchian', 'accbands', 'massi', 'aberration', 'hwc', 'thermo',
            'stoch', 'kdj', 'uo', 'willr', 'eri', 'psar', 'supertrend', 'vortex',
            'squeeze', 'squeeze_pro', 'kvo', 'eom', 'mfi', 'pmax', 'ttm_trend',
            'ad', 'adosc', 'cmf', 'efi', 'aobv', 'obv', 'pvt', 'pvol', 'pvr',
            'vp', 'vfi', 'nvi', 'pvi', 'ha', 'cdl_doji', 'cdl_inside', 'cdl_pattern', 'cdl_z',
            'hilo', 'hl2', 'hlc3', 'ohlc4', 'midpoint', 'midprice', 'wcp',
            'ichimoku', 'vwap', 'vwma', 'pvo'
        }
        needs_volume = indicator_name in {
            'ad', 'adosc', 'aobv', 'cmf', 'efi', 'kvo', 'mfi', 'nvi', 'obv',
            'pvi', 'pvol', 'pvr', 'pvt', 'vfi', 'vp', 'vwap', 'vwma', 'pvo', 'vwmacd'
        }
    
    try:
        if needs_hlc and high is not None and low is not None and close is not None:
            if needs_volume and volume is not None:
                result = indicator_fn(high, low, close, volume, **kwargs)
            else:
                result = indicator_fn(high, low, close, **kwargs)
        elif close is not None:
            if needs_volume and volume is not None:
                result = indicator_fn(close, volume, **kwargs)
            else:
                result = indicator_fn(close, **kwargs)
        else:
            raise ValueError(f"Indicator {indicator_name} requires at least 'close' price series")
    except TypeError as e:
        # Try alternative parameter orderings for indicators with different signatures
        error_msg = str(e).lower()
        try:
            # Some indicators expect (high, low, close) but weren't in our needs_hlc list
            if high is not None and low is not None and close is not None:
                if 'high' in error_msg or 'low' in error_msg or 'missing' in error_msg:
                    if needs_volume and volume is not None:
                        result = indicator_fn(high, low, close, volume, **kwargs)
                    else:
                        result = indicator_fn(high, low, close, **kwargs)
                else:
                    raise
            else:
                raise
        except TypeError:
            # Last resort - try with just close
            try:
                result = indicator_fn(close, **kwargs)
            except Exception:
                raise ValueError(f"Failed to compute indicator {indicator_name}: {e}")
    
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


def _normalize_multi_output(df: pd.DataFrame, indicator_name: str) -> Dict[str, pd.Series]:
    """
    Normalize multi-output DataFrame column names to simple keys.
    
    pandas_ta returns columns like 'MACD_12_26_9', 'MACDh_12_26_9', 'MACDs_12_26_9'.
    We normalize these to 'macd', 'histogram', 'signal' for consistent access.
    """
    result = {}
    
    for col in df.columns:
        # Normalize column name to lowercase and extract meaningful suffix
        col_lower = col.lower()
        
        # Extract the meaningful part of the column name
        # Common patterns: MACD_12_26_9 -> macd, MACDh_12_26_9 -> histogram
        # ADX_14 -> adx, DMP_14 -> dmp, DMN_14 -> dmn
        # BBL_20_2.0 -> lower, BBM_20_2.0 -> mid, BBU_20_2.0 -> upper
        
        key = _extract_column_key(col, indicator_name)
        result[key] = df[col]
    
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
        # MACD
        'macdh': 'histogram',
        'macds': 'signal',
        # Bollinger Bands
        'bbl': 'lower',
        'bbm': 'mid',
        'bbu': 'upper',
        'bbb': 'bandwidth',
        'bbp': 'percent_b',
        # Stochastic
        'stochk': 'k',
        'stochd': 'd',
        'stochrsik': 'k',
        'stochrsid': 'd',
        # Keltner Channel
        'kcl': 'lower',
        'kcb': 'basis',
        'kcu': 'upper',
        # Donchian
        'dcl': 'lower',
        'dcm': 'mid',
        'dcu': 'upper',
        # ADX
        'adx': 'adx',
        'dmp': 'dmp',
        'dmn': 'dmn',
        # Aroon
        'aroonu': 'up',
        'aroond': 'down',
        'aroono': 'osc',
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
        # Squeeze
        'sqz': 'sqz',
        'sqz_on': 'sqz_on',
        'sqz_off': 'sqz_off',
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


def get_available_indicators() -> List[str]:
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
) -> Dict[str, pd.Series]:
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
) -> Dict[str, pd.Series]:
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
    
    # pandas_ta returns columns like BBL_20_2.0, BBM_20_2.0, BBU_20_2.0, BBB_20_2.0, BBP_20_2.0
    std_str = f"{std:.1f}" if std == int(std) else str(std)
    lower_col = f"BBL_{length}_{std_str}"
    mid_col = f"BBM_{length}_{std_str}"
    upper_col = f"BBU_{length}_{std_str}"
    bw_col = f"BBB_{length}_{std_str}"
    pct_col = f"BBP_{length}_{std_str}"
    
    empty = pd.Series(index=close.index, dtype=float)
    return {
        "upper": result[upper_col] if upper_col in result.columns else empty.copy(),
        "middle": result[mid_col] if mid_col in result.columns else empty.copy(),
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
) -> Dict[str, pd.Series]:
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
) -> Dict[str, pd.Series]:
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
# Warmup Calculation Helpers
# =============================================================================

def get_ema_warmup(length: int, stabilization_factor: int = 3) -> int:
    """
    Calculate warmup bars for EMA.
    
    EMA theoretically needs only length-1 bars, but for stabilization
    we use a multiplier (default 3x).
    
    Args:
        length: EMA period
        stabilization_factor: Multiplier for stabilization (default: 3)
        
    Returns:
        Warmup bars needed
    """
    return length * stabilization_factor


def get_sma_warmup(length: int) -> int:
    """Calculate warmup bars for SMA (exactly length)."""
    return length


def get_rsi_warmup(length: int) -> int:
    """Calculate warmup bars for RSI (length + 1 for first delta)."""
    return length + 1


def get_atr_warmup(length: int) -> int:
    """Calculate warmup bars for ATR (length + 1 for previous close)."""
    return length + 1


def get_macd_warmup(fast: int, slow: int, signal: int) -> int:
    """
    Calculate warmup bars for MACD.
    
    MACD needs slow period for the slow EMA, plus signal period for
    signal line smoothing, with EMA stabilization factor.
    """
    return slow * 3 + signal


def get_bbands_warmup(length: int) -> int:
    """Calculate warmup bars for Bollinger Bands (same as SMA)."""
    return length


def get_stoch_warmup(k: int, d: int, smooth_k: int) -> int:
    """Calculate warmup bars for Stochastic."""
    return k + smooth_k + d


def get_stochrsi_warmup(length: int, rsi_length: int, k: int, d: int) -> int:
    """Calculate warmup bars for StochRSI."""
    return rsi_length + length + max(k, d)
