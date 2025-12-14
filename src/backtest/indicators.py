"""
Technical indicators for backtesting.

Provides indicator application for backtest DataFrames.
All indicator math is delegated to indicator_vendor (the only pandas_ta import point).

The engine uses only values available at or before the current bar (no look-ahead).
"""

import pandas as pd
from typing import Dict, List, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .features.feature_spec import FeatureSpec

from . import indicator_vendor as vendor
from .features.feature_spec import MULTI_OUTPUT_KEYS, IndicatorType


# Default warm-up multiplier for indicator stabilization
# Extra bars = max_lookback_bars * warmup_multiplier
DEFAULT_WARMUP_MULTIPLIER = 5

# NOTE: No default indicator columns — all indicators must be explicitly requested
# via FeatureSpec or IdeaCard. Indicators are declared explicitly, never inferred.


def get_warmup_from_specs(specs: List["FeatureSpec"], warmup_multiplier: int = None) -> int:
    """
    Compute warmup bars from FeatureSpecs.
    
    This is the canonical way to compute warmup for IdeaCard-based backtests.
    Uses each spec's warmup_bars property which computes proper warmup per indicator type.
    
    Args:
        specs: List of FeatureSpec objects
        warmup_multiplier: Optional multiplier (default: 1, no multiplier)
        
    Returns:
        Maximum warmup bars needed across all specs
    """
    if not specs:
        return 0
    
    multiplier = warmup_multiplier if warmup_multiplier is not None else 1
    max_warmup = max(spec.warmup_bars for spec in specs)
    return max_warmup * multiplier


def get_warmup_from_specs_by_role(
    specs_by_role: Dict[str, List["FeatureSpec"]],
    warmup_multiplier: int = None,
) -> Dict[str, int]:
    """
    Compute warmup bars for each TF role from feature specs.
    
    Args:
        specs_by_role: Dict mapping role -> list of FeatureSpecs
        warmup_multiplier: Optional multiplier (default: 1)
        
    Returns:
        Dict mapping role -> warmup bars
    """
    result = {}
    for role, specs in specs_by_role.items():
        result[role] = get_warmup_from_specs(specs, warmup_multiplier)
    return result


def get_max_warmup_from_specs_by_role(
    specs_by_role: Dict[str, List["FeatureSpec"]],
    warmup_multiplier: int = None,
) -> int:
    """
    Get the maximum warmup bars across all TF roles.
    
    Args:
        specs_by_role: Dict mapping role -> list of FeatureSpecs
        warmup_multiplier: Optional multiplier (default: 1)
        
    Returns:
        Maximum warmup bars across all roles
    """
    warmups = get_warmup_from_specs_by_role(specs_by_role, warmup_multiplier)
    return max(warmups.values()) if warmups else 0


def apply_feature_spec_indicators(
    df: pd.DataFrame,
    feature_specs: List,
) -> pd.DataFrame:
    """
    Apply indicators from FeatureSpecs to a DataFrame.
    
    This is the IdeaCard-based indicator computation.
    Supports all indicator types in the FeatureSpec system.
    
    Args:
        df: OHLCV DataFrame
        feature_specs: List of FeatureSpec objects
        
    Returns:
        DataFrame with added indicator columns
    """
    df = df.copy()
    
    for spec in feature_specs:
        ind_type = spec.indicator_type.lower()
        output_key = spec.output_key
        params = spec.params
        
        # Get input source (defaults to 'close')
        input_col = spec.input_source if hasattr(spec, 'input_source') else 'close'
        if input_col not in df.columns:
            input_col = 'close'
        
        # Apply indicator based on type
        if ind_type == "ema":
            length = params.get("length", 20)
            df[output_key] = vendor.ema(df[input_col], length=length)
            
        elif ind_type == "sma":
            length = params.get("length", 20)
            df[output_key] = vendor.sma(df[input_col], length=length)
            
        elif ind_type == "rsi":
            length = params.get("length", 14)
            df[output_key] = vendor.rsi(df[input_col], length=length)
            
        elif ind_type == "atr":
            length = params.get("length", 14)
            df[output_key] = vendor.atr(df["high"], df["low"], df["close"], length=length)
            
        elif ind_type == "macd":
            fast = params.get("fast", 12)
            slow = params.get("slow", 26)
            signal_param = params.get("signal", 9)
            macd_result = vendor.macd(df[input_col], fast=fast, slow=slow, signal=signal_param)
            if macd_result is not None:
                # Get output names from MULTI_OUTPUT_KEYS
                output_names = MULTI_OUTPUT_KEYS.get(IndicatorType.MACD, ("macd", "signal", "histogram"))
                if isinstance(macd_result, dict):
                    for name in output_names:
                        df[f"{output_key}_{name}"] = macd_result.get(name, pd.Series(index=df.index))
                elif hasattr(macd_result, 'columns'):
                    for i, name in enumerate(output_names):
                        if i < len(macd_result.columns):
                            df[f"{output_key}_{name}"] = macd_result.iloc[:, i]
            
        elif ind_type == "bbands":
            length = params.get("length", 20)
            std = params.get("std", 2.0)
            bb_result = vendor.bbands(df[input_col], length=length, std=std)
            if bb_result is not None:
                # Get output names from MULTI_OUTPUT_KEYS
                output_names = MULTI_OUTPUT_KEYS.get(IndicatorType.BBANDS, ("lower", "middle", "upper", "bandwidth", "percent_b"))
                if isinstance(bb_result, dict):
                    for name in output_names:
                        df[f"{output_key}_{name}"] = bb_result.get(name, pd.Series(index=df.index))
                elif hasattr(bb_result, 'columns'):
                    for i, name in enumerate(output_names):
                        if i < len(bb_result.columns):
                            df[f"{output_key}_{name}"] = bb_result.iloc[:, i]
            
        elif ind_type == "stoch":
            k_param = params.get("k", 14)
            d_param = params.get("d", 3)
            smooth_k = params.get("smooth_k", 3)
            stoch_result = vendor.stoch(df["high"], df["low"], df["close"], k=k_param, d=d_param, smooth_k=smooth_k)
            if stoch_result is not None:
                # Get output names from MULTI_OUTPUT_KEYS
                output_names = MULTI_OUTPUT_KEYS.get(IndicatorType.STOCH, ("k", "d"))
                if isinstance(stoch_result, dict):
                    for name in output_names:
                        df[f"{output_key}_{name}"] = stoch_result.get(name, pd.Series(index=df.index))
                elif hasattr(stoch_result, 'columns'):
                    for i, name in enumerate(output_names):
                        if i < len(stoch_result.columns):
                            df[f"{output_key}_{name}"] = stoch_result.iloc[:, i]
                
        elif ind_type == "stochrsi":
            length = params.get("length", 14)
            rsi_length = params.get("rsi_length", 14)
            k_param = params.get("k", 3)
            d_param = params.get("d", 3)
            stochrsi_result = vendor.stochrsi(df[input_col], length=length, rsi_length=rsi_length, k=k_param, d=d_param)
            if stochrsi_result is not None:
                # Get output names from MULTI_OUTPUT_KEYS
                output_names = MULTI_OUTPUT_KEYS.get(IndicatorType.STOCHRSI, ("k", "d"))
                if isinstance(stochrsi_result, dict):
                    for name in output_names:
                        df[f"{output_key}_{name}"] = stochrsi_result.get(name, pd.Series(index=df.index))
                elif hasattr(stochrsi_result, 'columns'):
                    for i, name in enumerate(output_names):
                        if i < len(stochrsi_result.columns):
                            df[f"{output_key}_{name}"] = stochrsi_result.iloc[:, i]
        
        # Add more indicator types as needed
    
    return df


def get_required_indicator_columns_from_specs(feature_specs: List) -> List[str]:
    """
    Get list of indicator columns from FeatureSpecs.
    
    Used to determine which columns must be non-NaN for simulation to start.
    Uses the FeatureSpec's output_keys_list property for consistency with
    the actual computed column names (including multi-output expansion).
    
    Args:
        feature_specs: List of FeatureSpec objects
        
    Returns:
        List of indicator column names
    """
    columns = []
    
    for spec in feature_specs:
        # Use the FeatureSpec's output key generation for consistency
        # output_keys_list returns single key for single-output, list for multi-output
        columns.extend(spec.output_keys_list)
    
    return columns




def find_first_valid_bar(df: pd.DataFrame, indicator_columns: List[str]) -> int:
    """
    Find the first bar index where all specified indicators are non-NaN.
    
    Args:
        df: DataFrame with indicator columns
        indicator_columns: List of column names that must be valid
        
    Returns:
        Index of first valid bar, or -1 if none found
    """
    if not indicator_columns:
        return 0  # No indicators required, start immediately
    
    # Filter to columns that exist in DataFrame
    existing_cols = [c for c in indicator_columns if c in df.columns]
    
    if not existing_cols:
        return 0  # No indicator columns present, start immediately
    
    # Find first row where all required indicators are non-NaN
    valid_mask = df[existing_cols].notna().all(axis=1)
    valid_indices = valid_mask[valid_mask].index.tolist()
    
    if not valid_indices:
        return -1  # No valid bars found
    
    return valid_indices[0]
