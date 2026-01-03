"""
Historical data maintenance operations.

Contains: detect_gaps, fill_gaps, heal, delete_symbol, cleanup_empty_symbols, vacuum
"""

from datetime import datetime, timedelta
from typing import Callable, Union, TYPE_CHECKING
import pandas as pd

if TYPE_CHECKING:
    from .historical_data_store import HistoricalDataStore


def _get_constants():
    from .historical_data_store import TIMEFRAMES, TF_MINUTES, ActivityEmoji, ActivitySpinner
    return TIMEFRAMES, TF_MINUTES, ActivityEmoji, ActivitySpinner


def detect_gaps(store: "HistoricalDataStore", symbol: str, timeframe: str) -> list[tuple[datetime, datetime]]:
    """
    Detect gaps in stored data.
    
    Returns list of (gap_start, gap_end) tuples.
    """
    TIMEFRAMES, TF_MINUTES, _, _ = _get_constants()
    
    symbol = symbol.upper()
    tf_minutes = TF_MINUTES.get(timeframe, 15)
    
    rows = store.conn.execute(f"""
        SELECT timestamp
        FROM {store.table_ohlcv}
        WHERE symbol = ? AND timeframe = ?
        ORDER BY timestamp ASC
    """, [symbol, timeframe]).fetchall()
    
    if not rows:
        return []
    
    gaps = []
    expected_delta = timedelta(minutes=tf_minutes)
    
    for i in range(1, len(rows)):
        prev_ts = rows[i-1][0]
        curr_ts = rows[i][0]
        actual_delta = curr_ts - prev_ts
        
        if actual_delta > expected_delta * 1.5:
            gaps.append((prev_ts + expected_delta, curr_ts - expected_delta))
    
    return gaps


def fill_gaps(
    store: "HistoricalDataStore",
    symbol: str = None,
    timeframe: str = None,
    progress_callback: Callable = None,
) -> dict[str, int]:
    """
    Fill detected gaps in data.
    
    Args:
        symbol: Specific symbol or None for all
        timeframe: Specific timeframe or None for all
        progress_callback: Optional callback for progress updates
    
    Returns:
        Dict mapping "symbol_timeframe" to candles filled
    """
    TIMEFRAMES, TF_MINUTES, ActivityEmoji, ActivitySpinner = _get_constants()
    from .historical_sync import _fetch_from_api, _store_dataframe, _update_metadata
    
    results = {}
    
    if symbol and timeframe:
        symbols_tfs = [(symbol.upper(), timeframe)]
    else:
        rows = store.conn.execute(f"""
            SELECT DISTINCT symbol, timeframe FROM {store.table_ohlcv}
        """).fetchall()
        symbols_tfs = [(r[0], r[1]) for r in rows]
    
    for sym, tf in symbols_tfs:
        key = f"{sym}_{tf}"
        gaps = detect_gaps(store, sym, tf)
        
        if not gaps:
            results[key] = 0
            continue
        
        if progress_callback:
            progress_callback(sym, tf, f"{ActivityEmoji.REPAIR} filling {len(gaps)} gaps")
        
        total_filled = 0
        bybit_tf = TIMEFRAMES.get(tf, tf)
        
        for gap_start, gap_end in gaps:
            if store._cancelled:
                break
            
            df = _fetch_from_api(store, sym, bybit_tf, gap_start, gap_end, show_progress=False)
            
            if not df.empty:
                _store_dataframe(store, sym, tf, df)
                total_filled += len(df)
        
        if total_filled > 0:
            _update_metadata(store, sym, tf)
        
        results[key] = total_filled
        
        if progress_callback:
            emoji = ActivityEmoji.SUCCESS if total_filled > 0 else ActivityEmoji.CHART
            progress_callback(sym, tf, f"{emoji} filled {total_filled} candles")
    
    return results


def heal(
    store: "HistoricalDataStore",
    symbol: str = None,
    timeframe: str = None,
    progress_callback: Callable = None,
) -> dict[str, dict]:
    """
    Heal data by detecting and filling gaps, plus verifying integrity.
    
    Args:
        symbol: Specific symbol or None for all
        timeframe: Specific timeframe or None for all
        progress_callback: Optional callback for progress updates
    
    Returns:
        Dict with healing results per symbol/timeframe
    """
    _, _, ActivityEmoji, _ = _get_constants()
    
    results = {}
    
    if symbol and timeframe:
        symbols_tfs = [(symbol.upper(), timeframe)]
    else:
        rows = store.conn.execute(f"""
            SELECT DISTINCT symbol, timeframe FROM {store.table_ohlcv}
        """).fetchall()
        symbols_tfs = [(r[0], r[1]) for r in rows]
    
    for sym, tf in symbols_tfs:
        key = f"{sym}_{tf}"
        
        if progress_callback:
            progress_callback(sym, tf, f"{ActivityEmoji.REPAIR} checking...")
        
        gaps_before = detect_gaps(store, sym, tf)
        
        fill_result = fill_gaps(store, sym, tf)
        filled = fill_result.get(key, 0)
        
        gaps_after = detect_gaps(store, sym, tf)
        
        results[key] = {
            "gaps_before": len(gaps_before),
            "gaps_after": len(gaps_after),
            "filled": filled,
            "healed": len(gaps_before) - len(gaps_after),
        }
        
        if progress_callback:
            emoji = ActivityEmoji.SUCCESS if len(gaps_after) == 0 else ActivityEmoji.WARNING
            progress_callback(sym, tf, f"{emoji} healed ({filled} candles, {len(gaps_after)} gaps remain)")
    
    return results


def delete_symbol(store: "HistoricalDataStore", symbol: str) -> int:
    """Delete all data for a symbol."""
    symbol = symbol.upper()
    
    count = store.conn.execute(f"""
        SELECT COUNT(*) FROM {store.table_ohlcv} WHERE symbol = ?
    """, [symbol]).fetchone()[0]
    
    store.conn.execute(f"DELETE FROM {store.table_ohlcv} WHERE symbol = ?", [symbol])
    store.conn.execute(f"DELETE FROM {store.table_sync_metadata} WHERE symbol = ?", [symbol])
    store.conn.execute(f"DELETE FROM {store.table_funding} WHERE symbol = ?", [symbol])
    store.conn.execute(f"DELETE FROM {store.table_funding_metadata} WHERE symbol = ?", [symbol])
    store.conn.execute(f"DELETE FROM {store.table_oi} WHERE symbol = ?", [symbol])
    store.conn.execute(f"DELETE FROM {store.table_oi_metadata} WHERE symbol = ?", [symbol])
    
    store.logger.info(f"Deleted {count} candles for {symbol}")
    return count


def delete_symbol_timeframe(store: "HistoricalDataStore", symbol: str, timeframe: str) -> int:
    """Delete data for a specific symbol/timeframe."""
    symbol = symbol.upper()
    
    count = store.conn.execute(f"""
        SELECT COUNT(*) FROM {store.table_ohlcv} WHERE symbol = ? AND timeframe = ?
    """, [symbol, timeframe]).fetchone()[0]
    
    store.conn.execute(f"""
        DELETE FROM {store.table_ohlcv} WHERE symbol = ? AND timeframe = ?
    """, [symbol, timeframe])
    store.conn.execute(f"""
        DELETE FROM {store.table_sync_metadata} WHERE symbol = ? AND timeframe = ?
    """, [symbol, timeframe])
    
    store.logger.info(f"Deleted {count} candles for {symbol} {timeframe}")
    return count


def cleanup_empty_symbols(store: "HistoricalDataStore") -> list[str]:
    """Remove symbols with no data from metadata tables."""
    symbols_with_data = store.conn.execute(f"""
        SELECT DISTINCT symbol FROM {store.table_ohlcv}
    """).fetchall()
    symbols_with_data = {r[0] for r in symbols_with_data}
    
    all_metadata_symbols = store.conn.execute(f"""
        SELECT DISTINCT symbol FROM {store.table_sync_metadata}
    """).fetchall()
    all_metadata_symbols = {r[0] for r in all_metadata_symbols}
    
    empty_symbols = all_metadata_symbols - symbols_with_data
    
    for sym in empty_symbols:
        store.conn.execute(f"DELETE FROM {store.table_sync_metadata} WHERE symbol = ?", [sym])
        store.conn.execute(f"DELETE FROM {store.table_funding_metadata} WHERE symbol = ?", [sym])
        store.conn.execute(f"DELETE FROM {store.table_oi_metadata} WHERE symbol = ?", [sym])
    
    if empty_symbols:
        store.logger.info(f"Cleaned up {len(empty_symbols)} empty symbols: {empty_symbols}")
    
    return list(empty_symbols)


def vacuum(store: "HistoricalDataStore"):
    """Vacuum the database to reclaim space."""
    store.conn.execute("VACUUM")
    store.logger.info("Database vacuumed")


def heal_comprehensive(
    store: "HistoricalDataStore",
    symbol: str = None,
    fix_issues: bool = True,
    fill_gaps_after: bool = True,
) -> dict:
    """
    Comprehensive data integrity check and repair.
    
    Checks for: duplicates, invalid OHLCV, negative volumes, NULL values,
    symbol casing, price anomalies, and time gaps.
    """
    from datetime import datetime
    from .historical_data_store import TIMEFRAMES, ActivityEmoji, print_activity
    
    if symbol:
        symbol = symbol.upper()
    
    print_activity("Starting data integrity check...", ActivityEmoji.SEARCH)
    
    report = {
        "checked_at": datetime.now().isoformat(),
        "symbol_filter": symbol,
        "issues_found": 0,
        "issues_fixed": 0,
        "details": {},
    }
    
    where_clause = f"WHERE symbol = '{symbol}'" if symbol else ""
    and_clause = f"AND symbol = '{symbol}'" if symbol else ""
    
    # 1. Duplicates
    print_activity("Checking for duplicate timestamps...", ActivityEmoji.SEARCH)
    dupes = store.conn.execute(f"""
        SELECT symbol, timeframe, timestamp, COUNT(*) as cnt
        FROM {store.table_ohlcv} {where_clause}
        GROUP BY symbol, timeframe, timestamp HAVING COUNT(*) > 1
    """).fetchall()
    
    report["details"]["duplicates"] = {"found": len(dupes), "fixed": 0}
    report["issues_found"] += len(dupes)
    
    if dupes and fix_issues:
        print_activity(f"Removing {len(dupes)} duplicate entries...", ActivityEmoji.REPAIR)
        for sym, tf, ts, cnt in dupes:
            store.conn.execute(f"""
                DELETE FROM {store.table_ohlcv} 
                WHERE symbol = ? AND timeframe = ? AND timestamp = ?
            """, [sym, tf, ts])
        report["details"]["duplicates"]["fixed"] = len(dupes)
        report["issues_fixed"] += len(dupes)
    
    # 2. Invalid high < low
    print_activity("Checking for invalid high < low...", ActivityEmoji.SEARCH)
    invalid_hl = store.conn.execute(f"""
        SELECT symbol, timeframe, timestamp FROM {store.table_ohlcv}
        WHERE high < low {and_clause.replace('AND', 'AND' if where_clause else '')}
    """.replace('AND  AND', 'AND')).fetchall()
    
    report["details"]["invalid_high_low"] = {"found": len(invalid_hl), "fixed": 0}
    report["issues_found"] += len(invalid_hl)
    
    if invalid_hl and fix_issues:
        print_activity(f"Removing {len(invalid_hl)} invalid rows...", ActivityEmoji.REPAIR)
        if symbol:
            store.conn.execute(f"DELETE FROM {store.table_ohlcv} WHERE high < low AND symbol = ?", [symbol])
        else:
            store.conn.execute(f"DELETE FROM {store.table_ohlcv} WHERE high < low")
        report["details"]["invalid_high_low"]["fixed"] = len(invalid_hl)
        report["issues_fixed"] += len(invalid_hl)
    
    # 3. Negative volumes
    print_activity("Checking for negative volumes...", ActivityEmoji.SEARCH)
    neg_vol = store.conn.execute(f"""
        SELECT COUNT(*) FROM {store.table_ohlcv} WHERE volume < 0 
        {and_clause.replace('AND', 'AND' if where_clause else '')}
    """.replace('AND  AND', 'AND')).fetchone()[0]
    
    report["details"]["negative_volumes"] = {"found": neg_vol, "fixed": 0}
    report["issues_found"] += neg_vol
    
    if neg_vol > 0 and fix_issues:
        print_activity(f"Setting {neg_vol} negative volumes to 0...", ActivityEmoji.REPAIR)
        if symbol:
            store.conn.execute(f"UPDATE {store.table_ohlcv} SET volume = 0 WHERE volume < 0 AND symbol = ?", [symbol])
        else:
            store.conn.execute(f"UPDATE {store.table_ohlcv} SET volume = 0 WHERE volume < 0")
        report["details"]["negative_volumes"]["fixed"] = neg_vol
        report["issues_fixed"] += neg_vol
    
    # 4. NULL values
    print_activity("Checking for NULL values...", ActivityEmoji.SEARCH)
    null_counts = store.conn.execute(f"""
        SELECT 
            SUM(CASE WHEN open IS NULL THEN 1 ELSE 0 END),
            SUM(CASE WHEN high IS NULL THEN 1 ELSE 0 END),
            SUM(CASE WHEN low IS NULL THEN 1 ELSE 0 END),
            SUM(CASE WHEN close IS NULL THEN 1 ELSE 0 END),
            SUM(CASE WHEN volume IS NULL THEN 1 ELSE 0 END)
        FROM {store.table_ohlcv} {where_clause}
    """).fetchone()
    total_nulls = sum(n or 0 for n in null_counts)
    
    report["details"]["null_values"] = {"found": total_nulls, "fixed": 0}
    report["issues_found"] += total_nulls
    
    if total_nulls > 0 and fix_issues:
        print_activity(f"Removing {total_nulls} rows with NULL values...", ActivityEmoji.REPAIR)
        if symbol:
            store.conn.execute(f"""
                DELETE FROM {store.table_ohlcv} 
                WHERE (open IS NULL OR high IS NULL OR low IS NULL OR close IS NULL) AND symbol = ?
            """, [symbol])
        else:
            store.conn.execute(f"""
                DELETE FROM {store.table_ohlcv} 
                WHERE open IS NULL OR high IS NULL OR low IS NULL OR close IS NULL
            """)
        report["details"]["null_values"]["fixed"] = total_nulls
        report["issues_fixed"] += total_nulls
    
    # 5. Symbol casing
    print_activity("Checking symbol casing...", ActivityEmoji.SEARCH)
    bad_casing = store.conn.execute(f"""
        SELECT DISTINCT symbol FROM {store.table_ohlcv} WHERE symbol != UPPER(symbol)
        {and_clause.replace('AND', 'AND' if where_clause else '')}
    """.replace('AND  AND', 'AND')).fetchall()
    
    report["details"]["symbol_casing"] = {"found": len(bad_casing), "fixed": 0}
    report["issues_found"] += len(bad_casing)
    
    if bad_casing and fix_issues:
        print_activity(f"Normalizing {len(bad_casing)} symbol(s)...", ActivityEmoji.REPAIR)
        for (bad_sym,) in bad_casing:
            store.conn.execute(f"UPDATE {store.table_ohlcv} SET symbol = UPPER(symbol) WHERE symbol = ?", [bad_sym])
            store.conn.execute(f"UPDATE {store.table_sync_metadata} SET symbol = UPPER(symbol) WHERE symbol = ?", [bad_sym])
        report["details"]["symbol_casing"]["fixed"] = len(bad_casing)
        report["issues_fixed"] += len(bad_casing)
    
    # 6. Price anomalies
    print_activity("Checking for price anomalies...", ActivityEmoji.SEARCH)
    anomalies = store.conn.execute(f"""
        SELECT COUNT(*) FROM {store.table_ohlcv} 
        WHERE (open > high OR open < low OR close > high OR close < low)
        {and_clause.replace('AND', 'AND' if where_clause else '')}
    """.replace('AND  AND', 'AND')).fetchone()[0]
    
    report["details"]["price_anomalies"] = {"found": anomalies, "fixed": 0}
    report["issues_found"] += anomalies
    
    if anomalies > 0 and fix_issues:
        print_activity(f"Removing {anomalies} rows with price anomalies...", ActivityEmoji.REPAIR)
        if symbol:
            store.conn.execute(f"""
                DELETE FROM {store.table_ohlcv} 
                WHERE (open > high OR open < low OR close > high OR close < low) AND symbol = ?
            """, [symbol])
        else:
            store.conn.execute(f"""
                DELETE FROM {store.table_ohlcv} 
                WHERE open > high OR open < low OR close > high OR close < low
            """)
        report["details"]["price_anomalies"]["fixed"] = anomalies
        report["issues_fixed"] += anomalies
    
    # 7. Update metadata after fixes
    if fix_issues and report["issues_fixed"] > 0:
        print_activity("Updating metadata...", ActivityEmoji.DATABASE)
        if symbol:
            combos = store.conn.execute(f"""
                SELECT DISTINCT symbol, timeframe FROM {store.table_ohlcv} WHERE symbol = ?
            """, [symbol]).fetchall()
        else:
            combos = store.conn.execute(f"""
                SELECT DISTINCT symbol, timeframe FROM {store.table_ohlcv}
            """).fetchall()
        
        for sym, tf in combos:
            store._update_metadata(sym, tf)
    
    # 8. Check gaps
    print_activity("Checking for time gaps...", ActivityEmoji.SEARCH)
    if symbol:
        combos = [(symbol, tf) for tf in TIMEFRAMES.keys()]
    else:
        combos = store.conn.execute(f"""
            SELECT DISTINCT symbol, timeframe FROM {store.table_sync_metadata}
        """).fetchall()
    
    total_gaps = 0
    for sym, tf in combos:
        gaps = detect_gaps(store, sym, tf)
        if gaps:
            total_gaps += len(gaps)
    
    report["details"]["gaps"] = {"found": total_gaps, "filled": 0}
    report["issues_found"] += total_gaps
    
    if total_gaps > 0 and fix_issues and fill_gaps_after:
        print_activity(f"Filling {total_gaps} gaps...", ActivityEmoji.REPAIR)
        fill_results = fill_gaps(store, symbol)
        filled = sum(v for v in fill_results.values() if v > 0)
        report["details"]["gaps"]["filled"] = filled
        report["issues_fixed"] += filled
    
    # Summary
    print("\n" + "=" * 60)
    if report["issues_found"] == 0:
        print_activity("Data is healthy! No issues found.", ActivityEmoji.SUCCESS)
    else:
        emoji = ActivityEmoji.SUCCESS if report["issues_fixed"] == report["issues_found"] else ActivityEmoji.WARNING
        print_activity(f"Found {report['issues_found']} issues, fixed {report['issues_fixed']}", emoji)
    print("=" * 60 + "\n")
    
    return report

