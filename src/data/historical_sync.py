"""
Historical data sync operations.

Contains: sync, sync_range, sync_forward, and internal sync methods.
"""

from datetime import datetime, timedelta
from typing import Callable, Union, TYPE_CHECKING
import pandas as pd

if TYPE_CHECKING:
    from .historical_data_store import HistoricalDataStore


# Import constants from main module when running
def _get_constants():
    from .historical_data_store import TIMEFRAMES, TF_MINUTES, ActivityEmoji, ActivitySpinner
    return TIMEFRAMES, TF_MINUTES, ActivityEmoji, ActivitySpinner


def sync(
    store: "HistoricalDataStore",
    symbols: Union[str, list[str]],
    period: str = "1M",
    timeframes: list[str] = None,
    progress_callback: Callable = None,
    show_spinner: bool = True,
) -> dict[str, int]:
    """Sync historical data for symbols."""
    TIMEFRAMES, TF_MINUTES, ActivityEmoji, ActivitySpinner = _get_constants()
    
    if isinstance(symbols, str):
        symbols = [symbols]
    
    symbols = [s.upper() for s in symbols]
    timeframes = timeframes or list(TIMEFRAMES.keys())
    target_start = datetime.now() - store.parse_period(period)
    
    results = {}
    total_synced = 0
    
    store.reset_cancellation()
    
    total_combinations = len(symbols) * len(timeframes)
    current_combination = 0
    
    for symbol in symbols:
        for tf in timeframes:
            if store._cancelled:
                store.logger.info("Sync cancelled by user")
                break
            
            current_combination += 1
            key = f"{symbol}_{tf}"
            
            if progress_callback:
                progress_callback(symbol, tf, f"{ActivityEmoji.SYNC} starting")
            
            spinner = None
            if show_spinner and not progress_callback:
                spinner = ActivitySpinner(f"Fetching {symbol} {tf}", ActivityEmoji.CANDLE)
                spinner.start()
            
            try:
                count = _sync_symbol_timeframe(store, symbol, tf, target_start, datetime.now())
                results[key] = count
                total_synced += max(0, count)
                
                if spinner:
                    spinner.stop(f"{symbol} {tf}: {count} candles {ActivityEmoji.SPARKLE}")
                elif progress_callback:
                    emoji = ActivityEmoji.SUCCESS if count > 0 else ActivityEmoji.CHART
                    progress_callback(symbol, tf, f"{emoji} done ({count:,} candles)")
                    
            except KeyboardInterrupt:
                store._cancelled = True
                store.logger.info("Sync interrupted by user")
                if spinner:
                    spinner.stop(f"{symbol} {tf}: cancelled", success=False)
                elif progress_callback:
                    progress_callback(symbol, tf, f"{ActivityEmoji.WARNING} cancelled")
                break
            except Exception as e:
                store.logger.error(f"Failed to sync {key}: {e}")
                results[key] = -1
                
                if spinner:
                    spinner.stop(f"{symbol} {tf}: error", success=False)
                elif progress_callback:
                    progress_callback(symbol, tf, f"{ActivityEmoji.ERROR} error: {e}")
        
        if store._cancelled:
            break
    
    return results


def sync_range(
    store: "HistoricalDataStore",
    symbols: Union[str, list[str]],
    start: datetime,
    end: datetime,
    timeframes: list[str] = None,
    progress_callback: Callable = None,
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
    
    for symbol in symbols:
        for tf in timeframes:
            key = f"{symbol}_{tf}"
            
            spinner = None
            if show_spinner and not progress_callback:
                spinner = ActivitySpinner(f"Fetching {symbol} {tf} ({start.date()} to {end.date()})", ActivityEmoji.CANDLE)
                spinner.start()
            
            try:
                count = _sync_symbol_timeframe(store, symbol, tf, start, end)
                results[key] = count
                total_synced += max(0, count)
                
                if spinner:
                    spinner.stop(f"{symbol} {tf}: {count:,} candles {ActivityEmoji.SPARKLE}")
                elif progress_callback:
                    emoji = ActivityEmoji.SUCCESS if count > 0 else ActivityEmoji.CHART
                    progress_callback(symbol, tf, f"{emoji} done ({count:,} candles)")
                else:
                    # Log progress even without spinner/callback
                    store.logger.info(f"  {symbol} {tf}: {count:,} candles synced")
                    
            except KeyboardInterrupt:
                store._cancelled = True
                store.logger.info("Sync interrupted by user")
                if spinner:
                    spinner.stop(f"{symbol} {tf}: cancelled", success=False)
                break
            except Exception as e:
                store.logger.error(f"Failed to sync {key}: {e}")
                results[key] = -1
                if spinner:
                    spinner.stop(f"{symbol} {tf}: error", success=False)
        
        if store._cancelled:
            break
    
    store.logger.info(f"Sync complete: {total_synced:,} total candles")
    return results


def sync_forward(
    store: "HistoricalDataStore",
    symbols: Union[str, list[str]],
    timeframes: list[str] = None,
    progress_callback: Callable = None,
    show_spinner: bool = True,
) -> dict[str, int]:
    """Sync data forward from the last stored candle to now."""
    TIMEFRAMES, _, ActivityEmoji, ActivitySpinner = _get_constants()
    
    if isinstance(symbols, str):
        symbols = [symbols]
    
    symbols = [s.upper() for s in symbols]
    timeframes = timeframes or list(TIMEFRAMES.keys())
    results = {}
    total_synced = 0
    
    for symbol in symbols:
        for tf in timeframes:
            key = f"{symbol}_{tf}"
            
            if progress_callback:
                progress_callback(symbol, tf, f"{ActivityEmoji.SYNC} syncing forward")
            
            spinner = None
            if show_spinner and not progress_callback:
                spinner = ActivitySpinner(f"Syncing {symbol} {tf} forward", ActivityEmoji.CANDLE)
                spinner.start()
            
            try:
                count = _sync_forward_symbol_timeframe(store, symbol, tf)
                results[key] = count
                total_synced += max(0, count)
                
                if spinner:
                    if count > 0:
                        spinner.stop(f"{symbol} {tf}: +{count} candles {ActivityEmoji.SPARKLE}")
                    else:
                        spinner.stop(f"{symbol} {tf}: already current {ActivityEmoji.SUCCESS}")
                elif progress_callback:
                    emoji = ActivityEmoji.SUCCESS if count >= 0 else ActivityEmoji.ERROR
                    progress_callback(symbol, tf, f"{emoji} done (+{count} candles)")
                    
            except Exception as e:
                store.logger.error(f"Failed to sync forward {key}: {e}")
                results[key] = -1
                
                if spinner:
                    spinner.stop(f"{symbol} {tf}: error", success=False)
                elif progress_callback:
                    progress_callback(symbol, tf, f"{ActivityEmoji.ERROR} error: {e}")
    
    return results


def _sync_forward_symbol_timeframe(store: "HistoricalDataStore", symbol: str, timeframe: str) -> int:
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
    
    last_ts = existing[0] if existing and existing[0] else None
    
    if last_ts is None:
        return 0
    
    start = last_ts + timedelta(minutes=tf_minutes)
    end = datetime.now()
    
    if start >= end:
        return 0
    
    df = _fetch_from_api(store, symbol, bybit_tf, start, end)
    
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
    
    first_ts, last_ts = existing
    total_synced = 0
    
    ranges_to_fetch = []
    
    if first_ts is None:
        ranges_to_fetch.append((target_start, target_end))
    else:
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
            break
        
        progress_prefix = f"{symbol} {timeframe}"
        df = _fetch_from_api(store, symbol, bybit_tf, range_start, range_end, progress_prefix=progress_prefix)
        
        if not df.empty:
            _store_dataframe(store, symbol, timeframe, df)
            total_synced += len(df)
    
    has_data = store.conn.execute(f"""
        SELECT COUNT(*) FROM {store.table_ohlcv} WHERE symbol = ? AND timeframe = ?
    """, [symbol, timeframe]).fetchone()[0] > 0
    
    if has_data:
        _update_metadata(store, symbol, timeframe)
    
    return total_synced


def _fetch_from_api(
    store: "HistoricalDataStore",
    symbol: str,
    bybit_tf: str,
    start: datetime,
    end: datetime,
    show_progress: bool = True,
    progress_prefix: str = None,
) -> pd.DataFrame:
    """Fetch data from Bybit API with visual progress."""
    _, _, ActivityEmoji, _ = _get_constants()
    
    all_data = []
    current_end = end
    request_count = 0
    
    start_ts = pd.Timestamp(start, tz='UTC') if start.tzinfo is None else pd.Timestamp(start)
    end_ts = pd.Timestamp(end, tz='UTC') if end.tzinfo is None else pd.Timestamp(end)
    current_end_ts = end_ts
    
    while current_end_ts > start_ts:
        if store._cancelled:
            break
        
        request_count += 1
        
        end_ms = int(current_end_ts.timestamp() * 1000)
        
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
        
        oldest = df["timestamp"].min()
        if oldest <= start_ts:
            break
        
        current_end_ts = oldest - pd.Timedelta(milliseconds=1)
        
        import time
        time.sleep(0.05)
    
    if not all_data:
        return pd.DataFrame()
    
    combined = pd.concat(all_data, ignore_index=True)
    combined = combined.drop_duplicates(subset=["timestamp"], keep="first")
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
    
    first_ts, last_ts, count = stats
    
    if first_ts and last_ts:
        store.conn.execute(f"""
            INSERT OR REPLACE INTO {store.table_sync_metadata}
            (symbol, timeframe, first_timestamp, last_timestamp, candle_count, last_sync)
            VALUES (?, ?, ?, ?, ?, ?)
        """, [symbol, timeframe, first_ts, last_ts, count, datetime.now()])

