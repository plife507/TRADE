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

import numpy as np
import pandas as pd
from datetime import datetime
from typing import Optional, Dict, List, Tuple, TYPE_CHECKING

from .runtime.feed_store import FeedStore, MultiTFFeedStore
from .runtime.quote_state import QuoteState
from .indicators import get_required_indicator_columns_from_specs

from ..utils.logger import get_logger

if TYPE_CHECKING:
    from .engine_data_prep import PreparedFrame, MultiTFPreparedFrames
    from .system_config import SystemConfig


class FeedStoreBuilderResult:
    """Result from building FeedStores."""

    def __init__(
        self,
        multi_tf_feed_store: MultiTFFeedStore,
        exec_feed: FeedStore,
        htf_feed: Optional[FeedStore],
        mtf_feed: Optional[FeedStore],
    ):
        self.multi_tf_feed_store = multi_tf_feed_store
        self.exec_feed = exec_feed
        self.htf_feed = htf_feed
        self.mtf_feed = mtf_feed


def build_feed_stores_impl(
    config: "SystemConfig",
    tf_mapping: Dict[str, str],
    multi_tf_mode: bool,
    mtf_frames: Optional["MultiTFPreparedFrames"],
    prepared_frame: Optional["PreparedFrame"],
    data: Optional[pd.DataFrame],
    logger=None,
) -> Tuple[MultiTFFeedStore, FeedStore, Optional[FeedStore], Optional[FeedStore]]:
    """
    Build FeedStores from prepared frames for array-backed hot loop.

    Must be called after prepare_multi_tf_frames() or prepare_backtest_frame().
    Creates FeedStore instances with precomputed arrays for O(1) access.

    Args:
        config: System configuration
        tf_mapping: Dict mapping htf/mtf/ltf to timeframe strings
        multi_tf_mode: Whether this is true multi-TF mode
        mtf_frames: Multi-TF prepared frames (if multi-TF mode)
        prepared_frame: Single-TF prepared frame (if single-TF mode)
        data: Fallback DataFrame if prepared_frame not available
        logger: Optional logger instance

    Returns:
        Tuple of (multi_tf_feed_store, exec_feed, htf_feed, mtf_feed)
        htf_feed and mtf_feed may be None if same as exec_feed

    Raises:
        ValueError: If no prepared frames available
    """
    if logger is None:
        logger = get_logger()

    if mtf_frames is None and prepared_frame is None:
        raise ValueError("No prepared frames. Call prepare_multi_tf_frames() first.")

    specs_by_role = config.feature_specs_by_role if hasattr(config, 'feature_specs_by_role') else {}

    exec_feed: Optional[FeedStore] = None
    htf_feed: Optional[FeedStore] = None
    mtf_feed: Optional[FeedStore] = None

    if multi_tf_mode and mtf_frames is not None:
        # Multi-TF mode: build feeds for each TF
        htf_tf = tf_mapping["htf"]
        mtf_tf = tf_mapping["mtf"]
        ltf_tf = tf_mapping["ltf"]

        # Get indicator columns for each TF role
        exec_cols = get_required_indicator_columns_from_specs(specs_by_role.get('exec', []))
        htf_cols = get_required_indicator_columns_from_specs(specs_by_role.get('htf', []))
        mtf_cols = get_required_indicator_columns_from_specs(specs_by_role.get('mtf', []))

        # Build exec/LTF feed
        ltf_df = mtf_frames.frames.get(ltf_tf)
        if ltf_df is not None:
            exec_feed = FeedStore.from_dataframe(
                df=ltf_df,
                tf=ltf_tf,
                symbol=config.symbol,
                indicator_columns=exec_cols,
            )

        # Build HTF feed (may be same as exec in single-TF)
        htf_df = mtf_frames.frames.get(htf_tf)
        if htf_df is not None and htf_tf != ltf_tf:
            htf_feed = FeedStore.from_dataframe(
                df=htf_df,
                tf=htf_tf,
                symbol=config.symbol,
                indicator_columns=htf_cols,
            )
        else:
            htf_feed = exec_feed  # Same as exec

        # Build MTF feed (may be same as exec in single-TF)
        mtf_df = mtf_frames.frames.get(mtf_tf)
        if mtf_df is not None and mtf_tf != ltf_tf:
            mtf_feed = FeedStore.from_dataframe(
                df=mtf_df,
                tf=mtf_tf,
                symbol=config.symbol,
                indicator_columns=mtf_cols,
            )
        else:
            mtf_feed = exec_feed  # Same as exec
    else:
        # Single-TF mode: use exec feed for all
        exec_cols = get_required_indicator_columns_from_specs(specs_by_role.get('exec', []))
        df = prepared_frame.df if prepared_frame else data

        exec_feed = FeedStore.from_dataframe(
            df=df,
            tf=config.tf,
            symbol=config.symbol,
            indicator_columns=exec_cols,
        )
        htf_feed = exec_feed
        mtf_feed = exec_feed

    # Create MultiTFFeedStore
    multi_tf_feed_store = MultiTFFeedStore(
        exec_feed=exec_feed,
        htf_feed=htf_feed if htf_feed is not exec_feed else None,
        mtf_feed=mtf_feed if mtf_feed is not exec_feed else None,
        tf_mapping=tf_mapping,
    )

    logger.info(
        f"Built FeedStores: exec={exec_feed.length} bars, "
        f"htf={htf_feed.length if htf_feed else 0} bars, "
        f"mtf={mtf_feed.length if mtf_feed else 0} bars"
    )

    return multi_tf_feed_store, exec_feed, htf_feed, mtf_feed


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
) -> Optional[QuoteState]:
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
        high_1m=float(quote_feed.high[idx]),
        low_1m=float(quote_feed.low[idx]),
        mark=float(quote_feed.close[idx]),  # Phase 2: approx from OHLCV
        mark_source=mark_source,
        volume_1m=float(quote_feed.volume[idx]),
    )
