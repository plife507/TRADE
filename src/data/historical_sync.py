"""
Historical data sync operations.

Contains: sync, sync_range, sync_forward, and internal sync methods.
"""

import time

from datetime import datetime, timedelta, timezone
from collections.abc import Callable
from typing import TYPE_CHECKING, cast
import pandas as pd


def _normalize_to_naive_utc(dt: datetime | None) -> datetime | None:
    """
    Normalize datetime to naive UTC for consistent comparison.

    DuckDB returns timezone-aware timestamps, CLI returns naive.
    This ensures both can be compared by stripping timezone info
    (assuming all datetimes are UTC).
    """
    if dt is None:
        return None
    if dt.tzinfo is not None:
        # Convert to UTC then strip timezone
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt

if TYPE_CHECKING:
    from .historical_data_store import HistoricalDataStore, ActivitySpinner as _ActivitySpinner


# Import constants from main module when running
def _get_constants():
    from .historical_data_store import TIMEFRAMES, TF_MINUTES, ActivityEmoji, ActivitySpinner
    return TIMEFRAMES, TF_MINUTES, ActivityEmoji, ActivitySpinner


def sync(
    store: "HistoricalDataStore",
    symbols: str | list[str],
    period: str = "1M",
    timeframes: list[str] | None = None,
    progress_callback: Callable | None = None,
    show_spinner: bool = True,
) -> dict[str, int]:
    """Sync historical data for symbols."""
    TIMEFRAMES, _, ActivityEmoji, ActivitySpinner = _get_constants()

    if isinstance(symbols, str):
        symbols = [symbols]

    symbols = [s.upper() for s in symbols]
    timeframes = timeframes or list(TIMEFRAMES.keys())
    target_start = datetime.now() - store.parse_period(period)

    results = {}

    store.reset_cancellation()

    total_pairs = len(symbols) * len(timeframes)
    pair_idx = 0

    for symbol in symbols:
        for tf in timeframes:
            if store._cancelled:
                store.logger.info("Sync cancelled by user")
                break

            key = f"{symbol}_{tf}"
            pair_idx += 1
            step_label = f"[{pair_idx}/{total_pairs}] {symbol} {tf}"

            if progress_callback:
                progress_callback(symbol, tf, f"{ActivityEmoji.SYNC} starting")

            spinner = None
            if show_spinner and not progress_callback:
                spinner = ActivitySpinner(f"{step_label}", ActivityEmoji.CANDLE)
                spinner.start()

            try:
                count = _sync_symbol_timeframe(store, symbol, tf, target_start, datetime.now(), spinner=spinner)
                results[key] = count

                if spinner:
                    spinner.stop(f"{step_label}: {count:,} candles {ActivityEmoji.SPARKLE}")
                elif progress_callback:
                    emoji = ActivityEmoji.SUCCESS if count > 0 else ActivityEmoji.CHART
                    progress_callback(symbol, tf, f"{emoji} done ({count:,} candles)")

            except KeyboardInterrupt:
                store._cancelled = True
                store.logger.info("Sync interrupted by user")
                if spinner:
                    spinner.stop(f"{step_label}: cancelled", success=False)
                elif progress_callback:
                    progress_callback(symbol, tf, f"{ActivityEmoji.WARNING} cancelled")
                break
            except Exception as e:
                store.logger.error(f"Failed to sync {key}: {e}")
                results[key] = -1

                if spinner:
                    spinner.stop(f"{step_label}: error", success=False)
                elif progress_callback:
                    progress_callback(symbol, tf, f"{ActivityEmoji.ERROR} error: {e}")

        if store._cancelled:
            break

    return results


def sync_range(
    store: "HistoricalDataStore",
    symbols: str | list[str],
    start: datetime,
    end: datetime,
    timeframes: list[str] | None = None,
    progress_callback: Callable | None = None,
    show_spinner: bool = True,
) -> dict[str, int]:
    """Sync a specific date range with progress logging."""
    TIMEFRAMES, _, ActivityEmoji, ActivitySpinner = _get_constants()
    
    if isinstance(symbols, str):
        symbols = [symbols]
    
    symbols = [s.upper() for s in symbols]
    timeframes = timeframes or list(TIMEFRAMES.keys())
    results = {}
    total_synced = 0
    
    store.logger.info(f"Syncing {len(symbols)} symbol(s) x {len(timeframes)} TF(s): {start.date()} to {end.date()}")

    total_pairs = len(symbols) * len(timeframes)
    pair_idx = 0

    for symbol in symbols:
        for tf in timeframes:
            key = f"{symbol}_{tf}"
            pair_idx += 1
            step_label = f"[{pair_idx}/{total_pairs}] {symbol} {tf} ({start.date()} to {end.date()})"

            spinner = None
            if show_spinner and not progress_callback:
                spinner = ActivitySpinner(f"{step_label}", ActivityEmoji.CANDLE)
                spinner.start()

            try:
                count = _sync_symbol_timeframe(store, symbol, tf, start, end, spinner=spinner)
                results[key] = count
                total_synced += max(0, count)

                if spinner:
                    spinner.stop(f"{step_label}: {count:,} candles {ActivityEmoji.SPARKLE}")
                elif progress_callback:
                    emoji = ActivityEmoji.SUCCESS if count > 0 else ActivityEmoji.CHART
                    progress_callback(symbol, tf, f"{emoji} done ({count:,} candles)")
                else:
                    store.logger.info(f"  {symbol} {tf}: {count:,} candles synced")

            except KeyboardInterrupt:
                store._cancelled = True
                store.logger.info("Sync interrupted by user")
                if spinner:
                    spinner.stop(f"{step_label}: cancelled", success=False)
                break
            except Exception as e:
                store.logger.error(f"Failed to sync {key}: {e}")
                results[key] = -1
                if spinner:
                    spinner.stop(f"{step_label}: error", success=False)

        if store._cancelled:
            break

    store.logger.info(f"Sync complete: {total_synced:,} total candles")
    return results


def sync_forward(
    store: "HistoricalDataStore",
    symbols: str | list[str],
    timeframes: list[str] | None = None,
    progress_callback: Callable | None = None,
    show_spinner: bool = True,
) -> dict[str, int]:
    """Sync data forward from the last stored candle to now."""
    TIMEFRAMES, _, ActivityEmoji, ActivitySpinner = _get_constants()
    
    if isinstance(symbols, str):
        symbols = [symbols]
    
    symbols = [s.upper() for s in symbols]
    timeframes = timeframes or list(TIMEFRAMES.keys())
    results = {}

    total_pairs = len(symbols) * len(timeframes)
    pair_idx = 0

    for symbol in symbols:
        for tf in timeframes:
            key = f"{symbol}_{tf}"
            pair_idx += 1
            step_label = f"[{pair_idx}/{total_pairs}] {symbol} {tf} forward"

            if progress_callback:
                progress_callback(symbol, tf, f"{ActivityEmoji.SYNC} syncing forward")

            spinner = None
            if show_spinner and not progress_callback:
                spinner = ActivitySpinner(f"{step_label}", ActivityEmoji.CANDLE)
                spinner.start()

            try:
                count = _sync_forward_symbol_timeframe(store, symbol, tf, spinner=spinner)
                results[key] = count

                if spinner:
                    if count > 0:
                        spinner.stop(f"{step_label}: +{count:,} candles {ActivityEmoji.SPARKLE}")
                    else:
                        spinner.stop(f"{step_label}: already current {ActivityEmoji.SUCCESS}")
                elif progress_callback:
                    emoji = ActivityEmoji.SUCCESS if count >= 0 else ActivityEmoji.ERROR
                    progress_callback(symbol, tf, f"{emoji} done (+{count} candles)")

            except Exception as e:
                store.logger.error(f"Failed to sync forward {key}: {e}")
                results[key] = -1

                if spinner:
                    spinner.stop(f"{step_label}: error", success=False)
                elif progress_callback:
                    progress_callback(symbol, tf, f"{ActivityEmoji.ERROR} error: {e}")
    
    return results


def _sync_forward_symbol_timeframe(
    store: "HistoricalDataStore",
    symbol: str,
    timeframe: str,
    spinner: "_ActivitySpinner | None" = None,
) -> int:
    """Sync a single symbol/timeframe forward from last timestamp to now."""
    TIMEFRAMES, TF_MINUTES, _, _ = _get_constants()

    symbol = symbol.upper()
    bybit_tf = TIMEFRAMES.get(timeframe, timeframe)
    tf_minutes = TF_MINUTES.get(timeframe, 15)

    existing = store.conn.execute(f"""
        SELECT MAX(timestamp) as last_ts
        FROM {store.table_ohlcv}
        WHERE symbol = ? AND timeframe = ?
    """, [symbol, timeframe]).fetchone()

    # Normalize to naive UTC for consistent comparison
    last_ts = _normalize_to_naive_utc(existing[0]) if existing and existing[0] else None

    if last_ts is None:
        return 0

    start = last_ts + timedelta(minutes=tf_minutes)
    end = datetime.now()  # Already naive

    if start >= end:
        return 0

    df = _fetch_from_api(store, symbol, bybit_tf, start, end, spinner=spinner)
    
    if not df.empty:
        _store_dataframe(store, symbol, timeframe, df)
        _update_metadata(store, symbol, timeframe)
        return len(df)
    
    return 0


def _sync_symbol_timeframe(
    store: "HistoricalDataStore",
    symbol: str,
    timeframe: str,
    target_start: datetime,
    target_end: datetime,
    spinner: "_ActivitySpinner | None" = None,
) -> int:
    """Sync a single symbol/timeframe combination."""
    TIMEFRAMES, TF_MINUTES, _, _ = _get_constants()
    
    symbol = symbol.upper()
    bybit_tf = TIMEFRAMES.get(timeframe, timeframe)
    tf_minutes = TF_MINUTES.get(timeframe, 15)
    
    existing = store.conn.execute(f"""
        SELECT MIN(timestamp) as first_ts, MAX(timestamp) as last_ts
        FROM {store.table_ohlcv}
        WHERE symbol = ? AND timeframe = ?
    """, [symbol, timeframe]).fetchone()

    # Normalize all datetimes to naive UTC for consistent comparison
    # (DuckDB returns tz-aware, CLI input is naive)
    first_ts = _normalize_to_naive_utc(existing[0]) if existing else None
    last_ts = _normalize_to_naive_utc(existing[1]) if existing else None
    target_start_norm = _normalize_to_naive_utc(target_start)
    target_end_norm = _normalize_to_naive_utc(target_end)
    assert target_start_norm is not None
    assert target_end_norm is not None
    target_start = target_start_norm
    target_end = target_end_norm

    total_synced = 0
    was_partial = False

    ranges_to_fetch = []

    if first_ts is None:
        ranges_to_fetch.append((target_start, target_end))
    else:
        assert last_ts is not None, "last_ts must not be None when first_ts is not None"
        if target_start < first_ts:
            older_end = first_ts - timedelta(minutes=tf_minutes)
            if target_start <= older_end:
                ranges_to_fetch.append((target_start, older_end))

        if target_end > last_ts:
            newer_start = last_ts + timedelta(minutes=tf_minutes)
            if newer_start <= target_end:
                ranges_to_fetch.append((newer_start, target_end))

    for range_start, range_end in ranges_to_fetch:
        if store._cancelled:
            was_partial = True
            break

        df = _fetch_from_api(store, symbol, bybit_tf, range_start, range_end, spinner=spinner)

        if not df.empty:
            _store_dataframe(store, symbol, timeframe, df)
            total_synced += len(df)

    # Only update metadata if fetch completed fully (not interrupted)
    if not was_partial:
        count_row = store.conn.execute(f"""
            SELECT COUNT(*) FROM {store.table_ohlcv} WHERE symbol = ? AND timeframe = ?
        """, [symbol, timeframe]).fetchone()
        has_data = (count_row[0] > 0) if count_row else False

        if has_data:
            _update_metadata(store, symbol, timeframe)

    return total_synced


def _estimate_candle_count(start: datetime, end: datetime, bybit_tf: str) -> int:
    """Estimate total candles for a date range and timeframe."""
    bybit_to_minutes = {"1": 1, "3": 3, "5": 5, "15": 15, "30": 30, "60": 60, "120": 120, "240": 240, "360": 360, "720": 720, "D": 1440}
    minutes = bybit_to_minutes.get(bybit_tf, 60)
    total_minutes = (end - start).total_seconds() / 60
    return max(1, int(total_minutes / minutes))


def _fetch_from_api(
    store: "HistoricalDataStore",
    symbol: str,
    bybit_tf: str,
    start: datetime,
    end: datetime,
    show_progress: bool = True,
    progress_prefix: str | None = None,
    spinner: "_ActivitySpinner | None" = None,
) -> pd.DataFrame:
    """Fetch data from Bybit API with progress tracking.

    Args:
        spinner: An ActivitySpinner instance. If provided, progress is
                 reported via spinner.set_progress().
    """
    all_data = []
    total_fetched = 0
    total_estimate = _estimate_candle_count(start, end, bybit_tf)

    start_ts = cast(pd.Timestamp, pd.Timestamp(start, tz='UTC') if start.tzinfo is None else pd.Timestamp(start))
    end_ts = cast(pd.Timestamp, pd.Timestamp(end, tz='UTC') if end.tzinfo is None else pd.Timestamp(end))
    current_end_ts = end_ts

    while current_end_ts > start_ts:
        if store._cancelled:
            break

        # current_end_ts is always valid (constructed from datetime arg)
        end_ms = int(current_end_ts.value // 10**6)

        try:
            df = store.client.get_klines(
                symbol=symbol,
                interval=bybit_tf,
                limit=1000,
                end=end_ms,
            )
        except Exception as e:
            store.logger.error(f"API error fetching {symbol}: {e}")
            break

        if df.empty:
            break

        df = df[df["timestamp"] >= start_ts]

        if df.empty:
            break

        all_data.append(df)
        total_fetched += len(df)

        # Report progress to spinner
        if spinner is not None:
            spinner.set_progress(total_fetched, total_estimate)

        oldest = df["timestamp"].min()
        if oldest <= start_ts:
            break

        current_end_ts = oldest - pd.Timedelta(milliseconds=1)

        time.sleep(0.05)

    if not all_data:
        return pd.DataFrame()

    combined = pd.concat(all_data, ignore_index=True)
    combined = combined.drop_duplicates(subset=["timestamp"], keep="last")
    combined = combined.sort_values("timestamp").reset_index(drop=True)

    return combined


def _store_dataframe(store: "HistoricalDataStore", symbol: str, timeframe: str, df: pd.DataFrame):
    """Store DataFrame to DuckDB."""
    if df.empty:
        return

    temp_df = df.copy()
    temp_df["symbol"] = symbol.upper()
    temp_df["timeframe"] = timeframe

    if temp_df["timestamp"].dt.tz is not None:
        temp_df["timestamp"] = temp_df["timestamp"].dt.tz_localize(None)

    if "turnover" not in temp_df.columns:
        temp_df["turnover"] = 0.0

    with store._write_operation():
        store.conn.execute(f"""
            INSERT OR REPLACE INTO {store.table_ohlcv}
            (symbol, timeframe, timestamp, open, high, low, close, volume, turnover)
            SELECT symbol, timeframe, timestamp, open, high, low, close, volume, turnover
            FROM temp_df
        """)


def _update_metadata(store: "HistoricalDataStore", symbol: str, timeframe: str):
    """Update sync metadata for a symbol/timeframe."""
    symbol = symbol.upper()

    stats = store.conn.execute(f"""
        SELECT
            MIN(timestamp) as first_ts,
            MAX(timestamp) as last_ts,
            COUNT(*) as count
        FROM {store.table_ohlcv}
        WHERE symbol = ? AND timeframe = ?
    """, [symbol, timeframe]).fetchone()

    assert stats is not None
    first_ts, last_ts, count = stats

    if first_ts and last_ts:
        with store._write_operation():
            store.conn.execute(f"""
                INSERT OR REPLACE INTO {store.table_sync_metadata}
                (symbol, timeframe, first_timestamp, last_timestamp, candle_count, last_sync)
                VALUES (?, ?, ?, ?, ?, ?)
            """, [symbol, timeframe, first_ts, last_ts, count, datetime.now()])

