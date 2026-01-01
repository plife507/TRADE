"""
Data preparation module for BacktestEngine.

This module handles all data loading and preparation logic:
- PreparedFrame: Dataclass holding prepared frame metadata
- MultiTFPreparedFrames: Multi-TF prepared frames with close_ts maps
- prepare_backtest_frame_impl: Prepare single-TF backtest DataFrame
- prepare_multi_tf_frames_impl: Prepare multi-TF DataFrames
- load_data_impl: Load and validate candle data
- timeframe_to_timedelta: Convert timeframe string to timedelta

All functions accept engine state/config as parameters and return prepared data.
The BacktestEngine delegates to these functions, maintaining the same public API.
"""

import pandas as pd
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Dict, Set, TYPE_CHECKING

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
from ..utils.logger import get_logger

if TYPE_CHECKING:
    from .types import WindowConfig


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

    Phase 3: Supports HTF/MTF/LTF data loading and indicator precomputation.
    """
    # TF mapping (htf, mtf, ltf -> tf string)
    tf_mapping: Dict[str, str]

    # DataFrames with indicators per TF (key = tf string, e.g., "4h", "1h", "5m")
    frames: Dict[str, pd.DataFrame] = field(default_factory=dict)

    # Close timestamp sets per TF (for data-driven close detection)
    close_ts_maps: Dict[str, Set[datetime]] = field(default_factory=dict)

    # LTF is the primary (simulation stepping)
    ltf_frame: Optional[pd.DataFrame] = None
    ltf_sim_start_index: int = 0

    # Warmup metadata
    warmup_bars: int = 0
    warmup_multiplier: int = 5
    max_indicator_lookback: int = 0

    # Window metadata
    requested_start: Optional[datetime] = None
    requested_end: Optional[datetime] = None
    simulation_start: Optional[datetime] = None

    # Note: HTF/MTF/LTF close timestamps are accessed directly via close_ts_maps.get(tf, set())
    # Dead helper methods (get_htf_close_ts, get_mtf_close_ts, get_ltf_close_ts) removed 2025-12-31


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


def prepare_backtest_frame_impl(
    config: SystemConfig,
    window: "WindowConfig",
    logger=None,
) -> PreparedFrame:
    """
    Prepare the backtest DataFrame with proper warm-up.

    This function:
    1. Validates symbol and mode locks (fail fast before data fetch)
    2. Computes warmup_bars based on strategy params and multiplier
    3. Extends the query range by warmup_span before window_start
    4. Loads extended DataFrame from DuckDB
    5. Applies indicators to the full extended DataFrame
    6. Finds the first bar where all required indicators are valid
    7. Sets simulation start to max(first_valid_bar, window_start)
    8. Returns PreparedFrame with all metadata

    Args:
        config: System configuration
        window: Window configuration with start/end dates
        logger: Optional logger instance

    Returns:
        PreparedFrame with DataFrame and metadata

    Raises:
        ValueError: If not enough data for warm-up + window, or invalid config
    """
    if logger is None:
        logger = get_logger()

    # =====================================================================
    # Mode Lock Validations (BEFORE data fetch)
    # Fail fast without downloading data for invalid configs.
    # =====================================================================
    if config.symbol:
        validate_usdt_pair(config.symbol)
    validate_margin_mode_isolated(config.risk_profile.margin_mode)
    validate_quote_ccy_and_instrument_type(
        config.risk_profile.quote_ccy,
        config.risk_profile.instrument_type,
    )

    store = get_historical_store(env=config.data_build.env)

    # Use Preflight-computed warmup (CANONICAL source via warmup_bars_by_role)
    # Engine MUST NOT compute warmup - it reads only from SystemConfig (set by Runner from Preflight)
    warmup_bars_by_role = getattr(config, 'warmup_bars_by_role', {})
    if not warmup_bars_by_role or 'exec' not in warmup_bars_by_role:
        raise ValueError(
            "MISSING_WARMUP_CONFIG: warmup_bars_by_role['exec'] not set. "
            "Preflight gate must run first to compute warmup requirements. "
            "Check that Preflight passed and Runner wired computed_warmup_requirements to SystemConfig."
        )
    warmup_bars = warmup_bars_by_role['exec']

    # max_lookback is the raw max warmup from specs (for indicator validation only)
    exec_specs = config.feature_specs_by_role.get('exec', []) if hasattr(config, 'feature_specs_by_role') else []
    max_lookback = get_warmup_from_specs(exec_specs) if exec_specs else 0

    # Compute data window using centralized utility
    tf_by_role = {'exec': config.tf}
    data_window = compute_data_window(
        window_start=window.start,
        window_end=window.end,
        warmup_bars_by_role=warmup_bars_by_role,
        tf_by_role=tf_by_role,
    )
    extended_start = data_window.data_start
    warmup_span = data_window.warmup_span
    requested_start = window.start
    requested_end = window.end

    logger.info(
        f"Loading data: {config.symbol} {config.tf} "
        f"from {extended_start} to {requested_end} "
        f"(warm-up: {warmup_bars} bars = {warmup_span})"
    )

    # Load extended data
    df = store.get_ohlcv(
        symbol=config.symbol,
        tf=config.tf,
        start=extended_start,
        end=requested_end,
    )

    # Validate data exists
    if df.empty:
        raise ValueError(
            f"No data found for {config.symbol} {config.tf} "
            f"from {extended_start} to {requested_end}. "
            f"Run data sync first: sync_symbols(['{config.symbol}'], "
            f"period='{config.data_build.period}')"
        )

    # Ensure sorted by timestamp
    df = df.sort_values("timestamp").reset_index(drop=True)

    # Track actual loaded range (may be clamped to dataset boundaries)
    loaded_start = df["timestamp"].iloc[0]
    loaded_end = df["timestamp"].iloc[-1]

    logger.info(
        f"Loaded {len(df)} bars: {loaded_start} to {loaded_end}"
    )

    # Apply indicators from IdeaCard FeatureSpecs (ONLY supported path)
    # No legacy params-based indicators - IdeaCard is the single source of truth
    if hasattr(config, 'feature_specs_by_role') and config.feature_specs_by_role:
        exec_specs = config.feature_specs_by_role.get('exec', [])
        if exec_specs:
            df = apply_feature_spec_indicators(df, exec_specs)
    else:
        raise ValueError(
            "No feature_specs_by_role in config. "
            "IdeaCard with declared FeatureSpecs is required. "
            "Legacy params-based indicators are not supported."
        )

    # Find first bar where all required indicators are valid
    # Use required_indicators from YAML (not all expanded outputs) to avoid
    # issues with mutually exclusive outputs like PSAR long/short or SuperTrend long/short
    required_indicators_by_role = getattr(config, 'required_indicators_by_role', {})
    if required_indicators_by_role.get('exec'):
        required_cols = list(required_indicators_by_role['exec'])
    elif hasattr(config, 'feature_specs_by_role') and config.feature_specs_by_role:
        # Fallback to expanding all feature_specs if no required_indicators declared
        exec_specs = config.feature_specs_by_role.get('exec', [])
        required_cols = get_required_indicator_columns_from_specs(exec_specs)
    else:
        required_cols = []  # Will fail validation

    first_valid_idx = find_first_valid_bar(df, required_cols)

    if first_valid_idx < 0:
        raise ValueError(
            f"No valid bars found for {config.symbol} {config.tf}. "
            f"All indicator columns have NaN values. Check data quality."
        )

    first_valid_ts = df.iloc[first_valid_idx]["timestamp"]

    # Simulation starts at max(first_valid_bar, requested_start)
    # We never start before the requested window, even if indicators are valid earlier
    if first_valid_ts >= requested_start:
        sim_start_ts = first_valid_ts
        sim_start_idx = first_valid_idx
    else:
        # Find the first bar >= requested_start
        mask = df["timestamp"] >= requested_start
        if not mask.any():
            raise ValueError(
                f"No data found at or after requested window start {requested_start}. "
                f"Loaded data ends at {loaded_end}."
            )
        sim_start_idx = mask.idxmax()
        sim_start_ts = df.iloc[sim_start_idx]["timestamp"]

    # =====================================================================
    # DELAY BARS: Apply delay-only evaluation offset (closed-candle aligned)
    # =====================================================================
    # Delay is applied AFTER indicator/data readiness check
    # Engine loads data from data_start, but begins EVALUATION at delay-offset start
    # Lookback is for data loading only - NOT applied here again
    delay_bars_by_role = getattr(config, 'delay_bars_by_role', {})
    exec_delay_bars = delay_bars_by_role.get('exec', 0)

    if exec_delay_bars > 0:
        # Align to TF close boundary first, then add delay offset
        aligned_start = ceil_to_tf_close(sim_start_ts, config.tf)
        delay_offset = tf_duration(config.tf) * exec_delay_bars
        eval_start_ts = aligned_start + delay_offset

        # Find the bar index at or after eval_start_ts
        eval_mask = df["timestamp"] >= eval_start_ts
        if not eval_mask.any():
            raise ValueError(
                f"Not enough data for delay offset: delay_bars={exec_delay_bars} "
                f"would start evaluation at {eval_start_ts}, but data ends at {loaded_end}."
            )
        eval_start_idx = eval_mask.idxmax()
        eval_start_ts_actual = df.iloc[eval_start_idx]["timestamp"]

        logger.info(
            f"Delay offset applied: delay_bars={exec_delay_bars}, "
            f"sim_start={sim_start_ts} -> eval_start={eval_start_ts_actual}"
        )

        # Update sim_start to delay-offset value
        sim_start_ts = eval_start_ts_actual
        sim_start_idx = eval_start_idx

    # Validate we have enough data for simulation
    if sim_start_ts > requested_end:
        raise ValueError(
            f"Not enough history for {config.symbol} {config.tf} "
            f"to satisfy warm-up + window. Simulation would start at {sim_start_ts}, "
            f"but requested window ends at {requested_end}. "
            f"Adjust warmup_multiplier (current: {warmup_multiplier}) or window dates."
        )

    # Check we have at least some bars for simulation
    sim_bars = len(df) - sim_start_idx
    if sim_bars < 10:
        raise ValueError(
            f"Insufficient simulation bars: got {sim_bars} bars after warm-up, "
            f"need at least 10 trading bars."
        )

    logger.info(
        f"Simulation start: {sim_start_ts} (bar {sim_start_idx}), "
        f"{sim_bars} bars available for trading"
    )

    # Create PreparedFrame
    prepared = PreparedFrame(
        df=df,  # Full DF with indicators, engine will handle sim_start_idx
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

    return prepared


def prepare_multi_tf_frames_impl(
    config: SystemConfig,
    window: "WindowConfig",
    tf_mapping: Dict[str, str],
    multi_tf_mode: bool,
    logger=None,
) -> MultiTFPreparedFrames:
    """
    Prepare multi-TF DataFrames with indicators and close_ts maps.

    Phase 3: Loads data for HTF, MTF, and LTF timeframes, applies
    indicators to each, and builds close_ts maps for data-driven
    cache detection.

    Args:
        config: System configuration
        window: Window configuration with start/end dates
        tf_mapping: Dict mapping htf/mtf/ltf to timeframe strings
        multi_tf_mode: Whether this is true multi-TF mode
        logger: Optional logger instance

    Returns:
        MultiTFPreparedFrames with all TF data and metadata

    Raises:
        ValueError: If data is missing or invalid
    """
    if logger is None:
        logger = get_logger()

    store = get_historical_store(env=config.data_build.env)

    # Get TF mapping
    ltf_tf = tf_mapping["ltf"]
    htf_tf = tf_mapping["htf"]

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

    # HTF warmup - required for multi-TF mode, optional for single-TF
    #
    # FIX: Single-TF strategies only define warmup_bars_by_role['exec'].
    # They don't have separate HTF/MTF roles, so 'htf' key won't exist.
    # However, multi_tf_mode is False for single-TF, and all TF mappings
    # point to the same timeframe (e.g., {'htf': '15m', 'mtf': '15m', 'ltf': '15m'}).
    #
    # Solution: Only require 'htf' warmup when actually in multi-TF mode.
    # For single-TF, fall back to exec warmup (which covers all roles since
    # they're all the same timeframe).
    if 'htf' not in warmup_bars_by_role:
        if multi_tf_mode:
            # True multi-TF mode: htf warmup is required
            raise ValueError(
                "MISSING_WARMUP_CONFIG: warmup_bars_by_role['htf'] not set for multi-TF mode. "
                "Preflight gate must compute warmup for HTF role. "
                "Check IdeaCard has htf TF config with warmup declared."
            )
        else:
            # Single-TF mode: all roles map to same TF, use exec warmup
            pass  # htf_warmup_bars will be computed below

    # warmup_multiplier is legacy - Preflight now computes the final warmup_bars
    # We keep the field for PreparedFrame/MultiTFPreparedFrames compatibility but always use 1
    warmup_multiplier = 1

    # max_lookback is the raw max warmup from specs (for indicator validation only)
    specs_by_role = config.feature_specs_by_role if hasattr(config, 'feature_specs_by_role') else {}
    exec_specs = specs_by_role.get('exec', [])
    max_lookback = get_warmup_from_specs(exec_specs, warmup_multiplier=1) if exec_specs else 0

    # Compute data window using centralized utility
    tf_by_role = {
        'exec': ltf_tf,
        'htf': htf_tf,
        'mtf': tf_mapping.get('mtf', ltf_tf),
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

    logger.info(
        f"Loading multi-TF data: {config.symbol} "
        f"HTF={htf_tf}, MTF={tf_mapping['mtf']}, LTF={ltf_tf} "
        f"from {data_start} to {requested_end} "
        f"(warmup: {warmup_bars} LTF bars)"
    )

    # Load data for each unique TF
    unique_tfs = set(tf_mapping.values())
    frames: Dict[str, pd.DataFrame] = {}
    close_ts_maps: Dict[str, Set[datetime]] = {}

    for tf in unique_tfs:
        df = store.get_ohlcv(
            symbol=config.symbol,
            tf=tf,
            start=data_start,
            end=requested_end,
        )

        if df.empty:
            raise ValueError(
                f"No data found for {config.symbol} {tf} "
                f"from {data_start} to {requested_end}. "
                f"Run data sync first."
            )

        # Ensure sorted by timestamp
        df = df.sort_values("timestamp").reset_index(drop=True)

        # Apply indicators from IdeaCard FeatureSpecs for this TF
        # Map TF back to role (htf/mtf/exec) to get correct specs
        tf_role = None
        for role, role_tf in tf_mapping.items():
            if role_tf == tf:
                tf_role = role
                break

        if hasattr(config, 'feature_specs_by_role') and config.feature_specs_by_role:
            # Try role-specific specs first, fallback to exec
            specs = config.feature_specs_by_role.get(tf_role) or \
                    config.feature_specs_by_role.get('exec', [])
            if specs:
                df = apply_feature_spec_indicators(df, specs)
        else:
            raise ValueError(
                f"No feature_specs_by_role in config for TF {tf}. "
                "IdeaCard with declared FeatureSpecs is required."
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

    # Get the LTF frame for simulation stepping
    ltf_frame = frames[ltf_tf]

    # Find first valid bar in LTF where all indicators are ready
    # Use required_indicators from YAML (not all expanded outputs) to avoid
    # issues with mutually exclusive outputs like PSAR long/short or SuperTrend long/short
    required_indicators_by_role = getattr(config, 'required_indicators_by_role', {})
    if required_indicators_by_role.get('exec'):
        required_cols = list(required_indicators_by_role['exec'])
    elif hasattr(config, 'feature_specs_by_role') and config.feature_specs_by_role:
        # Fallback to expanding all feature_specs if no required_indicators declared
        exec_specs = config.feature_specs_by_role.get('exec', [])
        required_cols = get_required_indicator_columns_from_specs(exec_specs)
    else:
        required_cols = []  # Will fail validation

    first_valid_idx = find_first_valid_bar(ltf_frame, required_cols)

    if first_valid_idx < 0:
        raise ValueError(
            f"No valid bars found for {config.symbol} {ltf_tf}. "
            f"All indicator columns have NaN values."
        )

    first_valid_ts = ltf_frame.iloc[first_valid_idx]["timestamp"]

    # Simulation starts at max(first_valid_bar, requested_start)
    if first_valid_ts >= requested_start:
        sim_start_ts = first_valid_ts
        sim_start_idx = first_valid_idx
    else:
        mask = ltf_frame["timestamp"] >= requested_start
        if not mask.any():
            raise ValueError(
                f"No data found at or after requested window start {requested_start}."
            )
        sim_start_idx = mask.idxmax()
        sim_start_ts = ltf_frame.iloc[sim_start_idx]["timestamp"]

    # =====================================================================
    # DELAY BARS: Apply delay-only evaluation offset (closed-candle aligned)
    # =====================================================================
    # For multi-TF mode, compute max eval_start across all roles
    delay_bars_by_role = getattr(config, 'delay_bars_by_role', {})

    # Compute eval_start per role and take max
    max_eval_start_ts = sim_start_ts
    for role, role_tf in [("exec", ltf_tf), ("htf", htf_tf), ("mtf", tf_mapping.get("mtf", ltf_tf))]:
        delay_bars = delay_bars_by_role.get(role, 0)
        if delay_bars > 0:
            aligned_start = ceil_to_tf_close(sim_start_ts, role_tf)
            delay_offset = tf_duration(role_tf) * delay_bars
            role_eval_start = aligned_start + delay_offset
            if role_eval_start > max_eval_start_ts:
                max_eval_start_ts = role_eval_start

    if max_eval_start_ts > sim_start_ts:
        # Find the bar index at or after max_eval_start_ts
        eval_mask = ltf_frame["timestamp"] >= max_eval_start_ts
        if not eval_mask.any():
            raise ValueError(
                f"Not enough data for delay offset: eval would start at {max_eval_start_ts}, "
                f"but data ends at {ltf_frame['timestamp'].iloc[-1]}."
            )
        eval_start_idx = eval_mask.idxmax()
        eval_start_ts_actual = ltf_frame.iloc[eval_start_idx]["timestamp"]

        logger.info(
            f"Delay offset applied (multi-TF): "
            f"sim_start={sim_start_ts} -> eval_start={eval_start_ts_actual}"
        )

        sim_start_ts = eval_start_ts_actual
        sim_start_idx = eval_start_idx

    # Validate enough data for simulation
    sim_bars = len(ltf_frame) - sim_start_idx
    if sim_bars < 10:
        raise ValueError(
            f"Insufficient simulation bars: got {sim_bars} bars after warm-up."
        )

    logger.info(
        f"Multi-TF simulation start: {sim_start_ts} (bar {sim_start_idx}), "
        f"{sim_bars} LTF bars available"
    )

    # Create and return result
    result = MultiTFPreparedFrames(
        tf_mapping=dict(tf_mapping),
        frames=frames,
        close_ts_maps=close_ts_maps,
        ltf_frame=ltf_frame,
        ltf_sim_start_index=sim_start_idx,
        warmup_bars=warmup_bars,
        warmup_multiplier=warmup_multiplier,
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
    mtf_frames: MultiTFPreparedFrames,
    tf_mapping: Dict[str, str],
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
        mtf_frames: Multi-TF prepared frames
        tf_mapping: Dict mapping htf/mtf/ltf to timeframe strings
        config: System configuration (for feature specs)

    Returns:
        FeatureSnapshot with indicator values
    """
    # Get the DataFrame for this TF
    df = mtf_frames.frames.get(tf) if mtf_frames else None

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
    required_indicators_by_role = getattr(config, 'required_indicators_by_role', {})
    required_cols = []
    if tf_role and required_indicators_by_role.get(tf_role):
        required_cols = list(required_indicators_by_role[tf_role])
    elif hasattr(config, 'feature_specs_by_role') and config.feature_specs_by_role:
        # Fallback to expanding all feature_specs if no required_indicators declared
        specs = config.feature_specs_by_role.get(tf_role) or \
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

    Returns:
        DataFrame with 1m OHLCV data

    Raises:
        ValueError: If no data found or data is insufficient
    """
    if logger is None:
        logger = get_logger()

    store = get_historical_store(env=data_env)

    # Calculate extended start with warmup
    warmup_span = timedelta(minutes=warmup_bars_1m)
    extended_start = window_start - warmup_span

    logger.info(
        f"Loading 1m quote data: {symbol} "
        f"from {extended_start} to {window_end} "
        f"(warmup: {warmup_bars_1m} bars)"
    )

    # Load 1m data
    df = store.get_ohlcv(
        symbol=symbol,
        tf="1m",
        start=extended_start,
        end=window_end,
    )

    if df is None or df.empty:
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
