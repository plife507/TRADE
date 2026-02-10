"""
Technical indicators for backtesting.

Provides indicator application for backtest DataFrames.
All indicator math is delegated to vendor (the only pandas_ta import point).

The engine uses only values available at or before the current bar (no look-ahead).
"""

import pandas as pd
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.backtest.features.feature_spec import FeatureSpec

from src.backtest import indicator_vendor as vendor
from src.backtest.indicator_registry import get_registry


# NOTE: No default indicator columns - all indicators must be explicitly requested
# via FeatureSpec or Play. Indicators are declared explicitly, never inferred.


def get_warmup_from_specs(specs: list["FeatureSpec"]) -> int:
    """
    Compute warmup bars from FeatureSpecs.

    This is the canonical way to compute warmup for Play-based backtests.
    Uses each spec's warmup_bars property which computes proper warmup per indicator type.

    Args:
        specs: List of FeatureSpec objects

    Returns:
        Maximum warmup bars needed across all specs
    """
    if not specs:
        return 0
    return max(spec.warmup_bars for spec in specs)


def get_warmup_from_specs_by_role(
    specs_by_role: dict[str, list["FeatureSpec"]],
) -> dict[str, int]:
    """
    Compute warmup bars for each TF role from feature specs.

    Args:
        specs_by_role: Dict mapping role -> list of FeatureSpecs

    Returns:
        Dict mapping role -> warmup bars
    """
    result = {}
    for role, specs in specs_by_role.items():
        result[role] = get_warmup_from_specs(specs)
    return result


def get_max_warmup_from_specs_by_role(
    specs_by_role: dict[str, list["FeatureSpec"]],
) -> int:
    """
    Get the maximum warmup bars across all TF roles.

    Args:
        specs_by_role: Dict mapping role -> list of FeatureSpecs

    Returns:
        Maximum warmup bars across all roles
    """
    warmups = get_warmup_from_specs_by_role(specs_by_role)
    return max(warmups.values()) if warmups else 0


def apply_feature_spec_indicators(
    df: pd.DataFrame,
    feature_specs: list,
) -> pd.DataFrame:
    """
    Apply indicators from FeatureSpecs to a DataFrame.

    This is the Play-based indicator computation.
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

        # Get input source - FAIL LOUD if not declared
        if not hasattr(spec, 'input_source') or spec.input_source is None:
            raise ValueError(
                f"MISSING_INPUT_SOURCE: Indicator '{output_key}' has no input_source. "
                "All FeatureSpecs MUST declare input_source explicitly."
            )

        # Convert enum to string value
        input_source = spec.input_source
        if hasattr(input_source, 'value'):
            input_col = input_source.value  # Enum -> string
        else:
            input_col = str(input_source).lower()

        # Handle synthetic sources (hlc3, ohlc4) - compute on demand
        if input_col == 'hlc3':
            if 'hlc3' not in df.columns:
                df['hlc3'] = (df['high'] + df['low'] + df['close']) / 3
        elif input_col == 'ohlc4':
            if 'ohlc4' not in df.columns:
                df['ohlc4'] = (df['open'] + df['high'] + df['low'] + df['close']) / 4

        # FAIL LOUD if column doesn't exist
        if input_col not in df.columns:
            raise ValueError(
                f"INVALID_INPUT_SOURCE: Indicator '{output_key}' requests input_source='{input_col}' "
                f"but column not found. Available: {list(df.columns)}"
            )

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
                # Get output names from registry
                output_names = get_registry().get_output_suffixes("macd")
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
                # Get output names from registry
                output_names = get_registry().get_output_suffixes("bbands")
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
                # Get output names from registry
                output_names = get_registry().get_output_suffixes("stoch")
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
                # Get output names from registry
                output_names = get_registry().get_output_suffixes("stochrsi")
                if isinstance(stochrsi_result, dict):
                    for name in output_names:
                        df[f"{output_key}_{name}"] = stochrsi_result.get(name, pd.Series(index=df.index))
                elif hasattr(stochrsi_result, 'columns'):
                    for i, name in enumerate(output_names):
                        if i < len(stochrsi_result.columns):
                            df[f"{output_key}_{name}"] = stochrsi_result.iloc[:, i]

        else:
            # Generic fallback for any indicator supported by the registry
            # Uses compute_indicator() which handles all registered indicator types
            # Pass input_col as the primary input (close parameter) for single-input indicators
            try:
                # Get ts_open for VWAP (requires DatetimeIndex for session boundaries)
                ts_open = df.get("ts_open") if "ts_open" in df.columns else df.get("timestamp")
                result = vendor.compute_indicator(
                    ind_type,
                    close=df[input_col],  # Use input_col, not always "close"
                    high=df["high"],
                    low=df["low"],
                    open_=df["open"],
                    volume=df.get("volume"),
                    ts_open=ts_open,  # For VWAP session boundaries
                    **params
                )

                if isinstance(result, dict):
                    # Multi-output: add each output as separate column
                    for name, series in result.items():
                        df[f"{output_key}_{name}"] = series
                elif isinstance(result, pd.Series):
                    # Single-output: add directly
                    df[output_key] = result
            except Exception as e:
                # FAIL LOUD - indicator computation failures must be surfaced
                raise ValueError(
                    f"INDICATOR_COMPUTATION_FAILED: {ind_type} (output_key={output_key}) failed: {e}. "
                    f"Check params={params} and input_source={input_col}."
                ) from e

    return df


def get_required_indicator_columns_from_specs(feature_specs: list) -> list[str]:
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



def find_first_valid_bar(df: pd.DataFrame, indicator_columns: list[str]) -> int:
    """
    Find the first bar index where all specified indicators are non-NaN.

    For mutually exclusive indicator outputs (e.g., SuperTrend's long/short or PSAR's
    long/short), only ONE of the group needs to be valid at each bar, not ALL.
    This is because by design, these indicators produce a value in only one output
    at a time (e.g., uptrend = long has value, short is NaN).

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

    # Get mutually exclusive groups from the registry
    registry = get_registry()
    exclusive_groups = registry.get_mutually_exclusive_groups(existing_cols)

    # Build set of columns that are in exclusive groups
    cols_in_exclusive_groups = set()
    for group in exclusive_groups:
        cols_in_exclusive_groups.update(group)

    # Split columns into regular (must all be valid) and exclusive groups
    regular_cols = [c for c in existing_cols if c not in cols_in_exclusive_groups]

    # Start with all True mask (all bars potentially valid)
    valid_mask = pd.Series(True, index=df.index)

    # For regular columns: ALL must be non-NaN
    if regular_cols:
        valid_mask &= df[regular_cols].notna().all(axis=1)

    # For each exclusive group: AT LEAST ONE must be non-NaN
    for group in exclusive_groups:
        group_cols = [c for c in group if c in df.columns]
        if group_cols:
            # any() across columns - at least one must be valid
            valid_mask &= df[group_cols].notna().any(axis=1)

    valid_indices = valid_mask[valid_mask].index.tolist()

    if not valid_indices:
        return -1  # No valid bars found

    return valid_indices[0]
