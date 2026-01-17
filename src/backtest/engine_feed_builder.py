"""
FeedStore builder module for BacktestEngine.

This module handles FeedStore construction for the array-backed hot loop:
- build_feed_stores_impl: Build FeedStores from prepared frames
- build_quote_feed_impl: Build 1m quote feed for px.last/px.mark
- Supports both single-TF and multi-TF modes
- Returns MultiTFFeedStore for unified access

All functions accept prepared frames and config as parameters.
The BacktestEngine delegates to these functions, maintaining the same public API.

Phase 2: Adds 1m quote feed for simulator price proxy.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from datetime import datetime
from typing import TYPE_CHECKING

from .runtime.feed_store import FeedStore, MultiTFFeedStore
from .runtime.quote_state import QuoteState
from .indicators import get_required_indicator_columns_from_specs

from ..utils.logger import get_logger

if TYPE_CHECKING:
    from .engine_data_prep import PreparedFrame, MultiTFPreparedFrames
    from .system_config import SystemConfig
    from .play import Play


class FeedStoreBuilderResult:
    """Result from building FeedStores."""

    def __init__(
        self,
        multi_tf_feed_store: MultiTFFeedStore,
        exec_feed: FeedStore,
        high_tf_feed: FeedStore | None,
        med_tf_feed: FeedStore | None,
    ):
        self.multi_tf_feed_store = multi_tf_feed_store
        self.exec_feed = exec_feed
        self.high_tf_feed = high_tf_feed
        self.med_tf_feed = med_tf_feed


def build_feed_stores_impl(
    config: SystemConfig,
    tf_mapping: dict[str, str],
    multi_tf_mode: bool,
    mtf_frames: MultiTFPreparedFrames | None,
    prepared_frame: PreparedFrame | None,
    data: pd.DataFrame | None,
    logger=None,
) -> tuple[MultiTFFeedStore, FeedStore, FeedStore | None, FeedStore | None]:
    """
    Build FeedStores for 3-feed + exec role system.

    Must be called after prepare_multi_tf_frames() or prepare_backtest_frame().
    Creates FeedStore instances with precomputed arrays for O(1) access.

    The 3-feed system:
    - low_tf_feed: Always present (lowest analysis TF)
    - med_tf_feed: None if same as low_tf
    - high_tf_feed: None if same as med_tf or low_tf
    - exec_role: Which feed we step on ("low_tf", "med_tf", or "high_tf")

    Args:
        config: System configuration
        tf_mapping: Dict with low_tf, med_tf, high_tf, exec keys
        multi_tf_mode: Whether this is true multi-TF mode
        mtf_frames: Multi-TF prepared frames (if multi-TF mode)
        prepared_frame: Single-TF prepared frame (if single-TF mode)
        data: Fallback DataFrame if prepared_frame not available
        logger: Optional logger instance

    Returns:
        Tuple of (multi_tf_feed_store, exec_feed, high_tf_feed, med_tf_feed)

    Raises:
        ValueError: If no prepared frames available
    """
    if logger is None:
        logger = get_logger()

    if mtf_frames is None and prepared_frame is None:
        raise ValueError("No prepared frames. Call prepare_multi_tf_frames() first.")

    # SystemConfig.feature_specs_by_role is always defined (default: empty dict)
    specs_by_role = config.feature_specs_by_role

    # Extract TF mapping (3-feed + exec role)
    low_tf = tf_mapping["low_tf"]
    med_tf = tf_mapping["med_tf"]
    high_tf = tf_mapping["high_tf"]
    exec_role = tf_mapping["exec"]  # "low_tf", "med_tf", or "high_tf"
    exec_tf = tf_mapping[exec_role]  # Resolve exec to actual TF string

    low_tf_feed: FeedStore | None = None
    med_tf_feed: FeedStore | None = None
    high_tf_feed: FeedStore | None = None

    if multi_tf_mode and mtf_frames is not None:
        # Multi-TF mode: build feeds for each unique TF
        # Get indicator columns for each TF
        low_tf_cols = get_required_indicator_columns_from_specs(specs_by_role.get(low_tf, specs_by_role.get('exec', [])))
        med_tf_cols = get_required_indicator_columns_from_specs(specs_by_role.get(med_tf, []))
        high_tf_cols = get_required_indicator_columns_from_specs(specs_by_role.get(high_tf, []))

        # Build low_tf feed (always present)
        low_tf_df = mtf_frames.frames.get(low_tf)
        if low_tf_df is not None:
            low_tf_feed = FeedStore.from_dataframe(
                df=low_tf_df,
                tf=low_tf,
                symbol=config.symbol,
                indicator_columns=low_tf_cols,
            )

        # Build med_tf feed (None if same as low_tf)
        if med_tf != low_tf:
            med_tf_df = mtf_frames.frames.get(med_tf)
            if med_tf_df is not None:
                med_tf_feed = FeedStore.from_dataframe(
                    df=med_tf_df,
                    tf=med_tf,
                    symbol=config.symbol,
                    indicator_columns=med_tf_cols,
                )
        # else: med_tf_feed stays None (use low_tf_feed)

        # Build high_tf feed (None if same as med_tf or low_tf)
        if high_tf != med_tf and high_tf != low_tf:
            high_tf_df = mtf_frames.frames.get(high_tf)
            if high_tf_df is not None:
                high_tf_feed = FeedStore.from_dataframe(
                    df=high_tf_df,
                    tf=high_tf,
                    symbol=config.symbol,
                    indicator_columns=high_tf_cols,
                )
        # else: high_tf_feed stays None (use med_tf_feed or low_tf_feed)
    else:
        # Single-TF mode: all feeds are the same
        exec_cols = get_required_indicator_columns_from_specs(specs_by_role.get('exec', []))
        df = prepared_frame.df if prepared_frame else data

        low_tf_feed = FeedStore.from_dataframe(
            df=df,
            tf=config.tf,
            symbol=config.symbol,
            indicator_columns=exec_cols,
        )
        # med_tf_feed and high_tf_feed stay None (use low_tf_feed)

    # Create MultiTFFeedStore with 3-feed + exec_role
    multi_tf_feed_store = MultiTFFeedStore(
        low_tf_feed=low_tf_feed,
        med_tf_feed=med_tf_feed,
        high_tf_feed=high_tf_feed,
        tf_mapping=tf_mapping,
        exec_role=exec_role,
    )

    # Get resolved exec_feed for backward compat return
    exec_feed = multi_tf_feed_store.exec_feed

    logger.info(
        f"Built FeedStores: low_tf={low_tf_feed.length} bars, "
        f"med_tf={med_tf_feed.length if med_tf_feed else 'shared'}, "
        f"high_tf={high_tf_feed.length if high_tf_feed else 'shared'}, "
        f"exec={exec_role}"
    )

    return multi_tf_feed_store, exec_feed, high_tf_feed, med_tf_feed


# =============================================================================
# Phase 2: 1m Quote Feed
# =============================================================================


def build_quote_feed_impl(
    df_1m: pd.DataFrame,
    symbol: str,
    logger=None,
) -> FeedStore:
    """
    Build a 1m quote FeedStore for px.last/px.mark price proxy.

    The quote feed provides O(1) access to 1m bar data for:
    - px.last: Last trade proxy (1m close)
    - px.mark: Mark price (1m close, approximated from OHLCV)
    - px.last.high_1m / px.last.low_1m: For zone touch detection

    Args:
        df_1m: DataFrame with 1m OHLCV data (must have timestamp, open, high, low, close, volume)
        symbol: Trading symbol
        logger: Optional logger instance

    Returns:
        FeedStore with 1m bar data (no indicators, just OHLCV)

    Raises:
        ValueError: If DataFrame is empty or missing required columns
    """
    if logger is None:
        logger = get_logger()

    if df_1m is None or df_1m.empty:
        raise ValueError("Cannot build quote feed: 1m DataFrame is empty")

    required_cols = {"timestamp", "open", "high", "low", "close", "volume"}
    missing_cols = required_cols - set(df_1m.columns)
    if missing_cols:
        raise ValueError(f"1m DataFrame missing columns: {missing_cols}")

    # Build FeedStore with no indicators (just OHLCV)
    quote_feed = FeedStore.from_dataframe(
        df=df_1m,
        tf="1m",
        symbol=symbol,
        indicator_columns=[],  # No indicators for quote feed
    )

    logger.info(f"Built quote feed: {quote_feed.length} 1m bars for {symbol}")

    return quote_feed


def get_quote_at_exec_close(
    quote_feed: FeedStore,
    exec_ts_close: datetime,
    mark_source: str = "approx_from_ohlcv_1m",
) -> QuoteState | None:
    """
    Get the most recent closed 1m quote at or before an exec TF close.

    Uses O(log n) binary search to find the last 1m bar that closed
    at or before the exec TF close time.

    Args:
        quote_feed: 1m FeedStore
        exec_ts_close: Exec TF close timestamp
        mark_source: Mark price source ("mark_1m" or "approx_from_ohlcv_1m")

    Returns:
        QuoteState if found, None if no 1m bar at or before exec_ts_close

    Example:
        # At each exec bar close, get the current quote
        quote = get_quote_at_exec_close(quote_feed, bar.ts_close)
        if quote:
            entry_price = quote.last  # px.last.value
    """
    # Find last 1m bar closed at or before exec_ts_close
    idx = quote_feed.get_last_closed_idx_at_or_before(exec_ts_close)

    if idx is None:
        return None

    # Extract 1m bar data
    ts_close = quote_feed.get_ts_close_datetime(idx)
    if isinstance(ts_close, np.datetime64):
        ts_ms = int(pd.Timestamp(ts_close).timestamp() * 1000)
    else:
        ts_ms = int(ts_close.timestamp() * 1000)

    return QuoteState(
        ts_ms=ts_ms,
        last=float(quote_feed.close[idx]),
        open_1m=float(quote_feed.open[idx]),
        high_1m=float(quote_feed.high[idx]),
        low_1m=float(quote_feed.low[idx]),
        mark=float(quote_feed.close[idx]),  # Phase 2: approx from OHLCV
        mark_source=mark_source,
        volume_1m=float(quote_feed.volume[idx]),
    )


# =============================================================================
# Phase 12: Funding Rate and Open Interest Array Building
# =============================================================================


def build_market_data_arrays_impl(
    funding_df: pd.DataFrame | None,
    oi_df: pd.DataFrame | None,
    exec_feed: FeedStore,
    logger=None,
) -> tuple[np.ndarray | None, np.ndarray | None, set[int]]:
    """
    Build funding_rate and open_interest arrays aligned to exec bar timestamps.

    Funding rate behavior:
    - Value is the rate that applies at funding settlement time
    - Between settlements: value is the last known rate (for strategy access)
    - Settlement detection: returns set of epoch_ms for O(1) hot loop check

    Open interest behavior:
    - Forward-filled to exec bar granularity
    - Each exec bar gets the last known OI value at or before its ts_close

    Args:
        funding_df: DataFrame with timestamp, funding_rate (or None)
        oi_df: DataFrame with timestamp, open_interest (or None)
        exec_feed: The exec FeedStore with ts_close array
        logger: Optional logger instance

    Returns:
        Tuple of (funding_rate_array, open_interest_array, funding_settlement_times)
        Arrays are np.ndarray aligned to exec_feed, or None if no data
        funding_settlement_times is set of epoch_ms for funding settlement timestamps
    """
    if logger is None:
        logger = get_logger()

    funding_rate_array: np.ndarray | None = None
    open_interest_array: np.ndarray | None = None
    funding_settlement_times: set[int] = set()

    n_bars = exec_feed.length

    # Build funding rate array
    if funding_df is not None and not funding_df.empty:
        funding_rate_array = np.zeros(n_bars, dtype=np.float64)

        # Sort funding events by timestamp
        funding_df = funding_df.sort_values("timestamp").reset_index(drop=True)

        # Convert funding timestamps to epoch ms for O(1) lookup
        funding_ts_ms_to_rate: dict[int, float] = {}
        for _, row in funding_df.iterrows():
            ts = row["timestamp"]
            if hasattr(ts, "timestamp"):
                ts_ms = int(ts.timestamp() * 1000)
            else:
                ts_ms = int(pd.Timestamp(ts).timestamp() * 1000)
            funding_ts_ms_to_rate[ts_ms] = float(row["funding_rate"])
            funding_settlement_times.add(ts_ms)

        # For each exec bar, find the last funding rate at or before ts_close
        # Also mark which bars are funding settlement times
        last_rate = 0.0
        funding_idx = 0
        funding_timestamps = funding_df["timestamp"].values
        funding_rates = funding_df["funding_rate"].values

        for i in range(n_bars):
            # Get exec bar ts_close
            ts_close = exec_feed.ts_close[i]
            if isinstance(ts_close, np.datetime64):
                ts_close_dt = pd.Timestamp(ts_close).to_pydatetime()
            else:
                ts_close_dt = ts_close

            # Advance through funding events up to ts_close
            while funding_idx < len(funding_timestamps):
                funding_ts = funding_timestamps[funding_idx]
                if hasattr(funding_ts, "to_pydatetime"):
                    funding_ts = funding_ts.to_pydatetime()
                elif isinstance(funding_ts, np.datetime64):
                    funding_ts = pd.Timestamp(funding_ts).to_pydatetime()

                if funding_ts <= ts_close_dt:
                    last_rate = float(funding_rates[funding_idx])
                    funding_idx += 1
                else:
                    break

            funding_rate_array[i] = last_rate

        logger.info(
            f"Built funding rate array: {n_bars} bars, "
            f"{len(funding_settlement_times)} settlement times"
        )

    # Build open interest array
    if oi_df is not None and not oi_df.empty:
        open_interest_array = np.zeros(n_bars, dtype=np.float64)

        # Sort OI data by timestamp
        oi_df = oi_df.sort_values("timestamp").reset_index(drop=True)

        # For each exec bar, forward-fill from last OI at or before ts_close
        last_oi = 0.0
        oi_idx = 0
        oi_timestamps = oi_df["timestamp"].values
        oi_values = oi_df["open_interest"].values

        for i in range(n_bars):
            # Get exec bar ts_close
            ts_close = exec_feed.ts_close[i]
            if isinstance(ts_close, np.datetime64):
                ts_close_dt = pd.Timestamp(ts_close).to_pydatetime()
            else:
                ts_close_dt = ts_close

            # Advance through OI records up to ts_close
            while oi_idx < len(oi_timestamps):
                oi_ts = oi_timestamps[oi_idx]
                if hasattr(oi_ts, "to_pydatetime"):
                    oi_ts = oi_ts.to_pydatetime()
                elif isinstance(oi_ts, np.datetime64):
                    oi_ts = pd.Timestamp(oi_ts).to_pydatetime()

                if oi_ts <= ts_close_dt:
                    last_oi = float(oi_values[oi_idx])
                    oi_idx += 1
                else:
                    break

            open_interest_array[i] = last_oi

        logger.info(
            f"Built open interest array: {n_bars} bars, "
            f"range [{open_interest_array.min():.0f}, {open_interest_array.max():.0f}]"
        )

    return funding_rate_array, open_interest_array, funding_settlement_times
