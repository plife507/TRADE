"""
Data preparation module for backtest data loading.

This module handles all data loading and preparation logic:
- PreparedFrame: Dataclass holding prepared frame metadata
- MultiTFPreparedFrames: Multi-TF prepared frames with close_ts maps
- prepare_backtest_frame_impl: Prepare single-TF backtest DataFrame
- prepare_multi_tf_frames_impl: Prepare multi-TF DataFrames
- load_data_impl: Load and validate candle data
- timeframe_to_timedelta: Convert timeframe string to timedelta

All functions accept config parameters and return prepared data.
Used by DataBuilder for backtest data preparation.

Gate 1 (Unified Validation): Functions accept optional synthetic_provider parameter
to enable DB-free validation runs using synthetic data.
"""

import pandas as pd
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Protocol

from .runtime.types import FeatureSnapshot, create_not_ready_feature_snapshot
from .runtime.types import Bar as CanonicalBar
from .runtime.timeframe import tf_duration, ceil_to_tf_close
from .runtime.windowing import compute_data_window
from .runtime.cache import build_close_ts_map_from_df
from .system_config import (
    SystemConfig,
    validate_usdt_pair,
    validate_margin_mode_isolated,
    validate_quote_ccy_and_instrument_type,
)
from .indicators import (
    apply_feature_spec_indicators,
    get_warmup_from_specs,
    get_required_indicator_columns_from_specs,
    find_first_valid_bar,
)

from ..data.historical_data_store import get_historical_store, TF_MINUTES
from ..config.constants import DataEnv
from ..utils.logger import get_logger

if TYPE_CHECKING:
    from .types import WindowConfig
    from src.forge.validation.synthetic_provider import SyntheticDataProvider


@dataclass
class PreparedFrame:
    """Result of prepare_backtest_frame with metadata."""
    df: pd.DataFrame  # DataFrame ready for simulation (trimmed to sim_start)
    full_df: pd.DataFrame  # Full DataFrame with indicators (includes warm-up data)
    warmup_bars: int
    max_indicator_lookback: int
    requested_start: datetime
    requested_end: datetime
    loaded_start: datetime
    loaded_end: datetime
    simulation_start: datetime
    sim_start_index: int  # Index in full_df where simulation starts


@dataclass
class MultiTFPreparedFrames:
    """
    Multi-timeframe prepared frames with close_ts maps for data-driven caching.

    Uses 3-feed + exec role system:
    - low_tf, med_tf, high_tf: actual data feeds
    - exec: role pointer to which feed we step on

    DataFrames are keyed by TF string (e.g., "4h", "1h", "15m").
    """
    # TF mapping (low_tf, med_tf, high_tf -> tf string, exec -> role name)
    tf_mapping: dict[str, str]

    # DataFrames with indicators per TF (key = tf string, e.g., "4h", "1h", "15m")
    frames: dict[str, pd.DataFrame] = field(default_factory=dict)

    # Close timestamp sets per TF (for data-driven close detection)
    close_ts_maps: dict[str, set[datetime]] = field(default_factory=dict)

    # Exec frame (the one we step on) - resolved from exec role
    exec_frame: pd.DataFrame | None = None
    exec_sim_start_index: int = 0

    # Warmup metadata
    warmup_bars: int = 0
    max_indicator_lookback: int = 0

    # Window metadata
    requested_start: datetime | None = None
    requested_end: datetime | None = None
    simulation_start: datetime | None = None


def timeframe_to_timedelta(tf: str) -> timedelta:
    """
    Convert timeframe string to timedelta.

    Raises ValueError on unknown timeframe (fail-fast, no silent defaults).

    Args:
        tf: Timeframe string (e.g., "5m", "1h", "4h")

    Returns:
        timedelta for the timeframe

    Raises:
        ValueError: If timeframe is not recognized
    """
    tf_lower = tf.lower()
    if tf_lower not in TF_MINUTES:
        raise ValueError(
            f"Unknown timeframe: '{tf}'. "
            f"Valid timeframes: {sorted(TF_MINUTES.keys())}"
        )
    return timedelta(minutes=TF_MINUTES[tf_lower])


# =============================================================================
# Prepare Frame Helpers (G4.4 Refactor)
# =============================================================================


def _validate_inputs(config: SystemConfig, logger) -> None:
    """Validate config inputs before data fetch (fail fast)."""
    if config.symbol:
        validate_usdt_pair(config.symbol)
    validate_margin_mode_isolated(config.risk_profile.margin_mode)
    validate_quote_ccy_and_instrument_type(
        config.risk_profile.quote_ccy,
        config.risk_profile.instrument_type,
    )


def _get_warmup_config(config: SystemConfig) -> tuple[int, int, list]:
    """
    Get warmup configuration from SystemConfig.

    Returns:
        (warmup_bars, max_lookback, exec_specs)
    """
    warmup_bars_by_role = getattr(config, 'warmup_bars_by_role', {})
    if not warmup_bars_by_role or 'exec' not in warmup_bars_by_role:
        raise ValueError(
            "MISSING_WARMUP_CONFIG: warmup_bars_by_role['exec'] not set. "
            "Preflight gate must run first to compute warmup requirements."
        )
    warmup_bars = warmup_bars_by_role['exec']

    exec_specs = config.feature_specs_by_role.get('exec', [])
    max_lookback = get_warmup_from_specs(exec_specs) if exec_specs else 0

    return warmup_bars, max_lookback, exec_specs


def _compute_data_windows(
    config: SystemConfig,
    window: "WindowConfig",
    warmup_bars_by_role: dict,
) -> tuple[datetime, timedelta, datetime, datetime]:
    """
    Compute data loading windows.

    Returns:
        (extended_start, warmup_span, requested_start, requested_end)
    """
    tf_by_role = {'exec': config.tf}
    data_window = compute_data_window(
        window_start=window.start,
        window_end=window.end,
        warmup_bars_by_role=warmup_bars_by_role,
        tf_by_role=tf_by_role,
    )
    return (
        data_window.data_start,
        data_window.warmup_span,
        window.start,
        window.end,
    )


def _load_ohlcv_data(
    config: SystemConfig,
    extended_start: datetime,
    requested_end: datetime,
    store,
    synthetic_provider: "SyntheticDataProvider | None",
    logger,
) -> pd.DataFrame:
    """Load OHLCV data from synthetic provider or DuckDB."""
    data_source = "SYNTHETIC" if synthetic_provider else "DuckDB"

    if synthetic_provider is not None:
        df = synthetic_provider.get_ohlcv(
            symbol=config.symbol,
            tf=config.tf,
            start=extended_start,
            end=requested_end,
        )
    else:
        df = store.get_ohlcv(
            symbol=config.symbol,
            tf=config.tf,
            start=extended_start,
            end=requested_end,
        )

    if df.empty:
        if synthetic_provider:
            raise ValueError(
                f"No synthetic data found for {config.symbol} {config.tf} "
                f"from {extended_start} to {requested_end}."
            )
        else:
            raise ValueError(
                f"No data found for {config.symbol} {config.tf} "
                f"from {extended_start} to {requested_end}. Run data sync first."
            )

    return df.sort_values("timestamp").reset_index(drop=True)


def _apply_indicators_to_frame(
    df: pd.DataFrame,
    config: SystemConfig,
) -> pd.DataFrame:
    """Apply indicators from FeatureSpecs to DataFrame."""
    if config.feature_specs_by_role:
        exec_specs = config.feature_specs_by_role.get('exec', [])
        if exec_specs:
            return apply_feature_spec_indicators(df, exec_specs)

    raise ValueError(
        "No feature_specs_by_role in config. "
        "Play with declared FeatureSpecs is required."
    )


def _compute_sim_start(
    df: pd.DataFrame,
    config: SystemConfig,
    requested_start: datetime,
    requested_end: datetime,
    warmup_bars: int,
    logger,
) -> tuple[datetime, int]:
    """
    Compute simulation start timestamp and index.

    Returns:
        (sim_start_ts, sim_start_idx)
    """
    # Get required indicator columns
    if config.required_indicators_by_role.get('exec'):
        required_cols = list(config.required_indicators_by_role['exec'])
    elif config.feature_specs_by_role:
        exec_specs = config.feature_specs_by_role.get('exec', [])
        required_cols = get_required_indicator_columns_from_specs(exec_specs)
    else:
        required_cols = []

    # Find first valid bar
    first_valid_idx = find_first_valid_bar(df, required_cols)
    if first_valid_idx < 0:
        raise ValueError(
            f"No valid bars found for {config.symbol} {config.tf}. "
            f"All indicator columns have NaN values."
        )

    first_valid_ts = df.iloc[first_valid_idx]["timestamp"]

    # Determine sim start (max of first_valid and requested_start)
    if first_valid_ts >= requested_start:
        sim_start_ts = first_valid_ts
        sim_start_idx = first_valid_idx
    else:
        mask = df["timestamp"] >= requested_start
        if not mask.any():
            raise ValueError(
                f"No data found at or after requested window start {requested_start}."
            )
        sim_start_idx = mask.idxmax()
        sim_start_ts = df.iloc[sim_start_idx]["timestamp"]

    # Apply delay bars if configured
    delay_bars_by_role = getattr(config, 'delay_bars_by_role', {})
    exec_delay_bars = delay_bars_by_role.get('exec', 0)

    if exec_delay_bars > 0:
        aligned_start = ceil_to_tf_close(sim_start_ts, config.tf)
        delay_offset = tf_duration(config.tf) * exec_delay_bars
        eval_start_ts = aligned_start + delay_offset

        eval_mask = df["timestamp"] >= eval_start_ts
        if not eval_mask.any():
            raise ValueError(
                f"Not enough data for delay offset: delay_bars={exec_delay_bars}"
            )
        sim_start_idx = eval_mask.idxmax()
        sim_start_ts = df.iloc[sim_start_idx]["timestamp"]

        logger.info(
            f"Delay offset applied: delay_bars={exec_delay_bars}, eval_start={sim_start_ts}"
        )

    # Validate simulation bounds
    if sim_start_ts > requested_end:
        raise ValueError(
            f"Not enough history to satisfy warm-up + window. "
            f"Simulation would start at {sim_start_ts}, window ends at {requested_end}."
        )

    sim_bars = len(df) - sim_start_idx
    if sim_bars < 10:
        raise ValueError(
            f"Insufficient simulation bars: got {sim_bars}, need at least 10."
        )

    logger.info(
        f"Simulation start: {sim_start_ts} (bar {sim_start_idx}), {sim_bars} bars available"
    )

    return sim_start_ts, sim_start_idx


# =============================================================================
# Main Prepare Function
# =============================================================================


def prepare_backtest_frame_impl(
    config: SystemConfig,
    window: "WindowConfig",
    logger=None,
    synthetic_provider: "SyntheticDataProvider | None" = None,
) -> PreparedFrame:
    """
    Prepare the backtest DataFrame with proper warm-up (G4.4 refactored).

    Orchestrates helper functions for each preparation phase:
    1. Validate inputs (fail fast)
    2. Get warmup config
    3. Compute data windows
    4. Load OHLCV data
    5. Apply indicators
    6. Compute simulation start

    Args:
        config: System configuration
        window: Window configuration with start/end dates
        logger: Optional logger instance
        synthetic_provider: Optional synthetic data provider

    Returns:
        PreparedFrame with DataFrame and metadata
    """
    if logger is None:
        logger = get_logger()

    # 1. Validate inputs (fail fast before data fetch)
    _validate_inputs(config, logger)

    # 2. Get warmup config
    warmup_bars, max_lookback, exec_specs = _get_warmup_config(config)

    # 3. Compute data windows
    warmup_bars_by_role = getattr(config, 'warmup_bars_by_role', {})
    extended_start, warmup_span, requested_start, requested_end = _compute_data_windows(
        config, window, warmup_bars_by_role
    )

    # 4. Load OHLCV data
    store = None if synthetic_provider else get_historical_store(env=config.data_build.env)
    data_source = "SYNTHETIC" if synthetic_provider else "DuckDB"
    logger.info(
        f"Loading data [{data_source}]: {config.symbol} {config.tf} "
        f"from {extended_start} to {requested_end} (warmup: {warmup_bars} bars)"
    )

    df = _load_ohlcv_data(
        config, extended_start, requested_end, store, synthetic_provider, logger
    )

    loaded_start = df["timestamp"].iloc[0]
    loaded_end = df["timestamp"].iloc[-1]
    logger.info(f"Loaded {len(df)} bars: {loaded_start} to {loaded_end}")

    # 5. Apply indicators
    df = _apply_indicators_to_frame(df, config)

    # 6. Compute simulation start
    sim_start_ts, sim_start_idx = _compute_sim_start(
        df, config, requested_start, requested_end, warmup_bars, logger
    )

    return PreparedFrame(
        df=df,
        full_df=df,
        warmup_bars=warmup_bars,
        max_indicator_lookback=max_lookback,
        requested_start=requested_start,
        requested_end=requested_end,
        loaded_start=loaded_start,
        loaded_end=loaded_end,
        simulation_start=sim_start_ts,
        sim_start_index=sim_start_idx,
    )


def prepare_multi_tf_frames_impl(
    config: SystemConfig,
    window: "WindowConfig",
    tf_mapping: dict[str, str],
    multi_tf_mode: bool,
    logger=None,
    synthetic_provider: "SyntheticDataProvider | None" = None,
) -> MultiTFPreparedFrames:
    """
    Prepare multi-TF DataFrames with indicators and close_ts maps.

    Phase 3: Loads data for high_tf, med_tf, and low_tf timeframes, applies
    indicators to each, and builds close_ts maps for data-driven
    cache detection.

    Args:
        config: System configuration
        window: Window configuration with start/end dates
        tf_mapping: Dict mapping high_tf/med_tf/low_tf to timeframe strings
        multi_tf_mode: Whether this is true multi-TF mode
        logger: Optional logger instance
        synthetic_provider: Optional synthetic data provider for DB-free validation

    Returns:
        MultiTFPreparedFrames with all TF data and metadata

    Raises:
        ValueError: If data is missing or invalid
    """
    if logger is None:
        logger = get_logger()

    # Only initialize DB store if not using synthetic provider
    store = None if synthetic_provider else get_historical_store(env=config.data_build.env)

    # Get TF mapping (3-feed + exec role system)
    low_tf = tf_mapping["low_tf"]
    med_tf = tf_mapping["med_tf"]
    high_tf = tf_mapping["high_tf"]
    exec_role = tf_mapping["exec"]  # "low_tf", "med_tf", or "high_tf"
    exec_tf = tf_mapping[exec_role]  # Resolve exec role to actual TF string

    # Use Preflight-computed warmup (CANONICAL source via warmup_bars_by_role)
    # Engine MUST NOT compute warmup - FAIL LOUD if not set
    warmup_bars_by_role = getattr(config, 'warmup_bars_by_role', {})
    if not warmup_bars_by_role or 'exec' not in warmup_bars_by_role:
        raise ValueError(
            "MISSING_WARMUP_CONFIG: warmup_bars_by_role['exec'] not set for multi-TF mode. "
            "Preflight gate must run first to compute warmup requirements. "
            "Check that Preflight passed and Runner wired computed_warmup_requirements to SystemConfig."
        )
    warmup_bars = warmup_bars_by_role['exec']

    # HighTF warmup - required for multi-TF mode, optional for single-TF
    #
    # FIX: Single-TF strategies only define warmup_bars_by_role['exec'].
    # They don't have separate HighTF/MedTF roles, so 'high_tf' key won't exist.
    # However, multi_tf_mode is False for single-TF, and all TF mappings
    # point to the same timeframe (e.g., {'high_tf': '15m', 'med_tf': '15m', 'low_tf': '15m'}).
    #
    # Solution: Only require 'high_tf' warmup when actually in multi-TF mode.
    # For single-TF, fall back to exec warmup (which covers all roles since
    # they're all the same timeframe).
    if 'high_tf' not in warmup_bars_by_role:
        if multi_tf_mode:
            # True multi-TF mode: high_tf warmup is required
            raise ValueError(
                "MISSING_WARMUP_CONFIG: warmup_bars_by_role['high_tf'] not set for multi-TF mode. "
                "Preflight gate must compute warmup for HighTF role. "
                "Check Play has high_tf TF config with warmup declared."
            )
        else:
            # Single-TF mode: all roles map to same TF, use exec warmup
            # No high_tf key needed - compute_data_window uses warmup_bars_by_role directly
            pass

    # max_lookback is the raw max warmup from specs (for indicator validation only)
    # SystemConfig.feature_specs_by_role is always defined (default: empty dict)
    exec_specs = config.feature_specs_by_role.get('exec', [])
    max_lookback = get_warmup_from_specs(exec_specs) if exec_specs else 0

    # Compute data window using centralized utility
    tf_by_role = {
        'exec': exec_tf,
        'low_tf': low_tf,
        'med_tf': med_tf,
        'high_tf': high_tf,
    }
    data_window = compute_data_window(
        window_start=window.start,
        window_end=window.end,
        warmup_bars_by_role=warmup_bars_by_role,
        tf_by_role=tf_by_role,
    )
    data_start = data_window.data_start
    warmup_span = data_window.warmup_span
    requested_start = window.start
    requested_end = window.end

    data_source = "SYNTHETIC" if synthetic_provider else "DuckDB"
    logger.info(
        f"Loading multi-TF data [{data_source}]: {config.symbol} "
        f"LowTF={low_tf}, MedTF={med_tf}, HighTF={high_tf}, Exec={exec_role} "
        f"from {data_start} to {requested_end} "
        f"(warmup: {warmup_bars} bars on {exec_tf})"
    )

    # Load data for each unique TF (exclude 'exec' which is a role pointer)
    unique_tfs = {low_tf, med_tf, high_tf}
    frames: dict[str, pd.DataFrame] = {}
    close_ts_maps: dict[str, set[datetime]] = {}

    for tf in unique_tfs:
        # Load from synthetic provider or DuckDB
        if synthetic_provider is not None:
            df = synthetic_provider.get_ohlcv(
                symbol=config.symbol,
                tf=tf,
                start=data_start,
                end=requested_end,
            )
        else:
            assert store is not None
            df = store.get_ohlcv(
                symbol=config.symbol,
                tf=tf,
                start=data_start,
                end=requested_end,
            )

        if df.empty:
            if synthetic_provider:
                raise ValueError(
                    f"No synthetic data found for {config.symbol} {tf} "
                    f"from {data_start} to {requested_end}. "
                    f"Generate synthetic data with required timeframes."
                )
            else:
                raise ValueError(
                    f"No data found for {config.symbol} {tf} "
                    f"from {data_start} to {requested_end}. "
                    f"Run data sync first."
                )

        # Ensure sorted by timestamp
        df = df.sort_values("timestamp").reset_index(drop=True)

        # Apply indicators from Play FeatureSpecs for this TF
        # Map TF back to role (low_tf/med_tf/high_tf) to get correct specs
        tf_role = None
        for role, role_tf in tf_mapping.items():
            if role_tf == tf:
                tf_role = role
                break

        # SystemConfig.feature_specs_by_role is always defined (default: empty dict)
        # Note: feature_specs_by_role is keyed by TF string (e.g., "4h") NOT role (e.g., "high_tf")
        if config.feature_specs_by_role:
            # Try TF-specific specs first (e.g., "4h"), then exec for non-TF-specific features
            specs = config.feature_specs_by_role.get(tf) or \
                    config.feature_specs_by_role.get('exec', [])
            if specs:
                df = apply_feature_spec_indicators(df, specs)
        else:
            raise ValueError(
                f"No feature_specs_by_role in config for TF {tf}. "
                "Play with declared FeatureSpecs is required."
            )

        # Add ts_close column for close detection
        tf_delta = tf_duration(tf)
        df["ts_close"] = df["timestamp"] + tf_delta

        # Build close_ts map from this TF's data
        close_ts_maps[tf] = build_close_ts_map_from_df(df, ts_close_column="ts_close")

        frames[tf] = df

        logger.debug(
            f"Loaded {len(df)} bars for {tf}, "
            f"{len(close_ts_maps[tf])} close timestamps"
        )

    # Get the ExecTF frame for simulation stepping
    exec_tf_frame = frames[exec_tf]

    # Find first valid bar in low_tf where all indicators are ready
    # Use required_indicators from YAML (not all expanded outputs) to avoid
    # issues with mutually exclusive outputs like PSAR long/short or SuperTrend long/short
    # SystemConfig.required_indicators_by_role and feature_specs_by_role are always defined
    if config.required_indicators_by_role.get('exec'):
        required_cols = list(config.required_indicators_by_role['exec'])
    elif config.feature_specs_by_role:
        # Fallback to expanding all feature_specs if no required_indicators declared
        exec_specs = config.feature_specs_by_role.get('exec', [])
        required_cols = get_required_indicator_columns_from_specs(exec_specs)
    else:
        required_cols = []  # Will fail validation

    first_valid_idx = find_first_valid_bar(exec_tf_frame, required_cols)

    if first_valid_idx < 0:
        raise ValueError(
            f"No valid bars found for {config.symbol} {exec_tf}. "
            f"All indicator columns have NaN values."
        )

    first_valid_ts = exec_tf_frame.iloc[first_valid_idx]["timestamp"]

    # Simulation starts at max(first_valid_bar, requested_start)
    if first_valid_ts >= requested_start:
        sim_start_ts = first_valid_ts
        sim_start_idx = first_valid_idx
    else:
        mask = exec_tf_frame["timestamp"] >= requested_start
        if not mask.any():
            raise ValueError(
                f"No data found at or after requested window start {requested_start}."
            )
        sim_start_idx = mask.idxmax()
        sim_start_ts = exec_tf_frame.iloc[sim_start_idx]["timestamp"]

    # =====================================================================
    # DELAY BARS: Apply delay-only evaluation offset (closed-candle aligned)
    # =====================================================================
    # For multi-TF mode, compute max eval_start across all roles
    delay_bars_by_role = getattr(config, 'delay_bars_by_role', {})

    # Compute eval_start per role and take max
    max_eval_start_ts = sim_start_ts
    for role, role_tf in [("exec", exec_tf), ("low_tf", low_tf), ("med_tf", med_tf), ("high_tf", high_tf)]:
        delay_bars = delay_bars_by_role.get(role, 0)
        if delay_bars > 0:
            aligned_start = ceil_to_tf_close(sim_start_ts, role_tf)
            delay_offset = tf_duration(role_tf) * delay_bars
            role_eval_start = aligned_start + delay_offset
            if role_eval_start > max_eval_start_ts:
                max_eval_start_ts = role_eval_start

    if max_eval_start_ts > sim_start_ts:
        # Find the bar index at or after max_eval_start_ts
        eval_mask = exec_tf_frame["timestamp"] >= max_eval_start_ts
        if not eval_mask.any():
            raise ValueError(
                f"Not enough data for delay offset: eval would start at {max_eval_start_ts}, "
                f"but data ends at {exec_tf_frame['timestamp'].iloc[-1]}."
            )
        eval_start_idx = eval_mask.idxmax()
        eval_start_ts_actual = exec_tf_frame.iloc[eval_start_idx]["timestamp"]

        logger.info(
            f"Delay offset applied (multi-TF): "
            f"sim_start={sim_start_ts} -> eval_start={eval_start_ts_actual}"
        )

        sim_start_ts = eval_start_ts_actual
        sim_start_idx = eval_start_idx

    # Validate enough data for simulation
    sim_bars = len(exec_tf_frame) - sim_start_idx
    if sim_bars < 10:
        raise ValueError(
            f"Insufficient simulation bars: got {sim_bars} bars after warm-up."
        )

    logger.info(
        f"Multi-TF simulation start: {sim_start_ts} (bar {sim_start_idx}), "
        f"{sim_bars} ExecTF bars available"
    )

    # Create and return result
    result = MultiTFPreparedFrames(
        tf_mapping=dict(tf_mapping),
        frames=frames,
        close_ts_maps=close_ts_maps,
        exec_frame=exec_tf_frame,
        exec_sim_start_index=sim_start_idx,
        warmup_bars=warmup_bars,
        max_indicator_lookback=max_lookback,
        requested_start=requested_start,
        requested_end=requested_end,
        simulation_start=sim_start_ts,
    )

    return result


def load_data_impl(
    config: SystemConfig,
    window: "WindowConfig",
    logger=None,
) -> pd.DataFrame:
    """
    Load and validate candle data from DuckDB.

    Delegates to prepare_backtest_frame_impl() which handles warm-up properly.

    Args:
        config: System configuration
        window: Window configuration with start/end dates
        logger: Optional logger instance

    Returns:
        DataFrame with OHLCV data and indicators

    Raises:
        ValueError: If data is empty, has gaps, or is invalid
    """
    prepared = prepare_backtest_frame_impl(config, window, logger)
    return prepared.df


def get_tf_features_at_close_impl(
    tf: str,
    ts_close: datetime,
    bar: CanonicalBar,
    multi_tf_frames: MultiTFPreparedFrames,
    tf_mapping: dict[str, str],
    config: SystemConfig,
) -> FeatureSnapshot:
    """
    Get FeatureSnapshot for a TF at a specific close timestamp.

    Looks up the bar in the TF DataFrame that closed at ts_close
    and extracts its indicator features.

    Args:
        tf: Timeframe string
        ts_close: Close timestamp to look up
        bar: Current bar (for fallback if not found)
        multi_tf_frames: Multi-TF prepared frames
        tf_mapping: Dict mapping high_tf/med_tf/low_tf to timeframe strings
        config: System configuration (for feature specs)

    Returns:
        FeatureSnapshot with indicator values
    """
    # Get the DataFrame for this TF
    df = multi_tf_frames.frames.get(tf) if multi_tf_frames else None

    if df is None or "ts_close" not in df.columns:
        return create_not_ready_feature_snapshot(
            tf=tf,
            ts_close=ts_close,
            bar=bar,
            reason=f"No data for {tf}",
        )

    # Find the row with this ts_close
    mask = df["ts_close"] == ts_close
    if not mask.any():
        return create_not_ready_feature_snapshot(
            tf=tf,
            ts_close=ts_close,
            bar=bar,
            reason=f"No bar at {ts_close} for {tf}",
        )

    row = df[mask].iloc[-1]  # Take last matching row

    # Extract ALL numeric features (not hardcoded list)
    features = {}
    ohlcv_cols = {"timestamp", "open", "high", "low", "close", "volume", "ts_close"}
    for col in row.index:
        if col not in ohlcv_cols and pd.notna(row[col]):
            try:
                features[col] = float(row[col])
            except (ValueError, TypeError):
                pass

    # Check if required indicators are valid (not NaN)
    # Use required_indicators from YAML (not all expanded outputs) to avoid
    # issues with mutually exclusive outputs like PSAR long/short or SuperTrend long/short
    tf_role = None
    for role, role_tf in tf_mapping.items():
        if role_tf == tf:
            tf_role = role
            break

    # Try to use required_indicators from YAML first (handles mutually exclusive outputs)
    # SystemConfig.required_indicators_by_role and feature_specs_by_role are always defined
    required_cols = []
    if tf_role and config.required_indicators_by_role.get(tf_role):
        required_cols = list(config.required_indicators_by_role[tf_role])
    elif config.feature_specs_by_role:
        # Fallback to expanding all feature_specs if no required_indicators declared
        specs = (config.feature_specs_by_role.get(tf_role) if tf_role else None) or \
                config.feature_specs_by_role.get('exec', [])
        required_cols = get_required_indicator_columns_from_specs(specs)

    all_valid = all(col in features for col in required_cols)

    # Create the Bar for this TF
    tf_delta = tf_duration(tf)
    ts_open = row["timestamp"]
    if hasattr(ts_open, "to_pydatetime"):
        ts_open = ts_open.to_pydatetime()
    tf_ts_close = row["ts_close"]
    if hasattr(tf_ts_close, "to_pydatetime"):
        tf_ts_close = tf_ts_close.to_pydatetime()

    tf_bar = CanonicalBar(
        symbol=config.symbol,
        tf=tf,
        ts_open=ts_open,
        ts_close=tf_ts_close,
        open=row["open"],
        high=row["high"],
        low=row["low"],
        close=row["close"],
        volume=row["volume"],
    )

    if not all_valid:
        return create_not_ready_feature_snapshot(
            tf=tf,
            ts_close=tf_ts_close,
            bar=tf_bar,
            reason=f"Indicators warming up for {tf}",
        )

    return FeatureSnapshot(
        tf=tf,
        ts_close=tf_ts_close,
        bar=tf_bar,
        features=features,
        ready=True,
    )


# =============================================================================
# Phase 2: 1m Quote Data Loading
# =============================================================================


def load_1m_data_impl(
    symbol: str,
    window_start: datetime,
    window_end: datetime,
    warmup_bars_1m: int,
    data_env: str = "live",
    logger=None,
    synthetic_provider: "SyntheticDataProvider | None" = None,
) -> pd.DataFrame:
    """
    Load 1m OHLCV data for quote feed.

    Loads 1m bars covering the backtest window plus warmup buffer.
    This data is used to build the quote FeedStore for px.last/px.mark.

    Args:
        symbol: Trading symbol (e.g., "SOLUSDT")
        window_start: Backtest window start
        window_end: Backtest window end
        warmup_bars_1m: Number of 1m warmup bars to load before window_start
        data_env: Data environment ("live" or "demo")
        logger: Optional logger instance
        synthetic_provider: Optional synthetic data provider for DB-free validation

    Returns:
        DataFrame with 1m OHLCV data

    Raises:
        ValueError: If no data found or data is insufficient
    """
    if logger is None:
        logger = get_logger()

    # Only initialize DB store if not using synthetic provider
    store = None if synthetic_provider else get_historical_store(env=data_env)

    # Calculate extended start with warmup
    warmup_span = timedelta(minutes=warmup_bars_1m)
    extended_start = window_start - warmup_span

    data_source = "SYNTHETIC" if synthetic_provider else "DuckDB"
    logger.info(
        f"Loading 1m quote data [{data_source}]: {symbol} "
        f"from {extended_start} to {window_end} "
        f"(warmup: {warmup_bars_1m} bars)"
    )

    # Load 1m data (from synthetic provider or DuckDB)
    if synthetic_provider is not None:
        df = synthetic_provider.get_1m_quotes(
            symbol=symbol,
            start=extended_start,
            end=window_end,
        )
    else:
        assert store is not None
        df = store.get_ohlcv(
            symbol=symbol,
            tf="1m",
            start=extended_start,
            end=window_end,
        )

    if df is None or df.empty:
        if synthetic_provider:
            raise ValueError(
                f"No synthetic 1m data found for {symbol} from {extended_start} to {window_end}. "
                f"Generate synthetic data with '1m' timeframe."
            )
        else:
            raise ValueError(
                f"No 1m data found for {symbol} from {extended_start} to {window_end}. "
                f"Run: python trade_cli.py data sync-range --symbol {symbol} --tf 1m "
                f"--start {extended_start.strftime('%Y-%m-%d')} --end {window_end.strftime('%Y-%m-%d')}"
            )

    # Ensure sorted by timestamp
    df = df.sort_values("timestamp").reset_index(drop=True)

    logger.info(
        f"Loaded {len(df)} 1m bars for {symbol}: "
        f"{df['timestamp'].iloc[0]} to {df['timestamp'].iloc[-1]}"
    )

    return df


# =============================================================================
# Phase 12: Funding Rate and Open Interest Data Loading
# =============================================================================


def load_funding_data_impl(
    symbol: str,
    window_start: datetime,
    window_end: datetime,
    data_env: str = "live",
    logger=None,
) -> pd.DataFrame:
    """
    Load funding rate data for the backtest window.

    Funding rates are recorded at 8-hour intervals (00:00, 08:00, 16:00 UTC).
    This function loads all funding events within the backtest window.

    Args:
        symbol: Trading symbol (e.g., "SOLUSDT")
        window_start: Backtest window start
        window_end: Backtest window end
        data_env: Data environment ("live" or "demo")
        logger: Optional logger instance

    Returns:
        DataFrame with columns: timestamp, funding_rate
        Sorted by timestamp ascending. Empty DataFrame if no data.
    """
    if logger is None:
        logger = get_logger()

    store = get_historical_store(env=data_env)

    logger.info(
        f"Loading funding data: {symbol} from {window_start} to {window_end}"
    )

    df = store.get_funding(
        symbol=symbol,
        start=window_start,
        end=window_end,
    )

    if df is None or df.empty:
        logger.warning(
            f"No funding data found for {symbol} from {window_start} to {window_end}. "
            f"Funding settlements will be skipped. "
            f"To sync: python trade_cli.py data sync-funding --symbol {symbol}"
        )
        return pd.DataFrame(columns=pd.Index(["timestamp", "funding_rate"]))

    # Ensure sorted by timestamp
    df = df.sort_values("timestamp").reset_index(drop=True)

    logger.info(
        f"Loaded {len(df)} funding events for {symbol}: "
        f"{df['timestamp'].iloc[0]} to {df['timestamp'].iloc[-1]}"
    )

    return df


def load_open_interest_data_impl(
    symbol: str,
    window_start: datetime,
    window_end: datetime,
    data_env: str = "live",
    logger=None,
) -> pd.DataFrame:
    """
    Load open interest data for the backtest window.

    Open interest data is recorded at various intervals (5min to 1D).
    This function loads all OI records within the backtest window.

    Args:
        symbol: Trading symbol (e.g., "SOLUSDT")
        window_start: Backtest window start
        window_end: Backtest window end
        data_env: Data environment ("live" or "demo")
        logger: Optional logger instance

    Returns:
        DataFrame with columns: timestamp, open_interest
        Sorted by timestamp ascending. Empty DataFrame if no data.
    """
    if logger is None:
        logger = get_logger()

    store = get_historical_store(env=data_env)

    logger.info(
        f"Loading open interest data: {symbol} from {window_start} to {window_end}"
    )

    df = store.get_open_interest(
        symbol=symbol,
        start=window_start,
        end=window_end,
    )

    if df is None or df.empty:
        logger.warning(
            f"No open interest data found for {symbol} from {window_start} to {window_end}. "
            f"Open interest features will be unavailable. "
            f"To sync: python trade_cli.py data sync-oi --symbol {symbol}"
        )
        return pd.DataFrame(columns=["timestamp", "open_interest"])

    # Ensure sorted by timestamp
    df = df.sort_values("timestamp").reset_index(drop=True)

    logger.info(
        f"Loaded {len(df)} open interest records for {symbol}: "
        f"{df['timestamp'].iloc[0]} to {df['timestamp'].iloc[-1]}"
    )

    return df
