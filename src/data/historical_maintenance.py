"""
Historical data maintenance operations.

Contains: detect_gaps, fill_gaps, heal, delete_symbol, cleanup_empty_symbols, vacuum
"""

from datetime import datetime, timedelta
from collections.abc import Callable
from typing import TYPE_CHECKING

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
    _, TF_MINUTES, _, _ = _get_constants()

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
        
        if actual_delta > expected_delta * 1.05:
            gaps.append((prev_ts + expected_delta, curr_ts - expected_delta))
    
    return gaps


def fill_gaps(
    store: "HistoricalDataStore",
    symbol: str | None = None,
    timeframe: str | None = None,
    progress_callback: Callable | None = None,
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
    symbol: str | None = None,
    timeframe: str | None = None,
    progress_callback: Callable | None = None,
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
    
    row = store.conn.execute(f"""
        SELECT COUNT(*) FROM {store.table_ohlcv} WHERE symbol = ?
    """, [symbol]).fetchone()
    assert row is not None
    count = row[0]
    
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
    
    row = store.conn.execute(f"""
        SELECT COUNT(*) FROM {store.table_ohlcv} WHERE symbol = ? AND timeframe = ?
    """, [symbol, timeframe]).fetchone()
    assert row is not None
    count = row[0]
    
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
    data_rows = store.conn.execute(f"""
        SELECT DISTINCT symbol FROM {store.table_ohlcv}
    """).fetchall()
    symbols_with_data = {r[0] for r in data_rows}

    metadata_rows = store.conn.execute(f"""
        SELECT DISTINCT symbol FROM {store.table_sync_metadata}
    """).fetchall()
    all_metadata_symbols = {r[0] for r in metadata_rows}
    
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
    symbol: str | None = None,
    fix_issues: bool = True,
    fill_gaps_after: bool = True,
) -> dict:
    """
    Comprehensive data integrity check and repair.
    
    Checks for: duplicates, invalid OHLCV, negative volumes, NULL values,
    symbol casing, price anomalies, and time gaps.
    """
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
    
    # Use parameterized queries for safety
    symbol_filter = "AND symbol = ?" if symbol else ""
    params = [symbol] if symbol else []

    # 1. Duplicates
    print_activity("Checking for duplicate timestamps...", ActivityEmoji.SEARCH)
    dupe_query = f"""
        SELECT symbol, timeframe, timestamp, COUNT(*) as cnt
        FROM {store.table_ohlcv}
        WHERE 1=1 {symbol_filter}
        GROUP BY symbol, timeframe, timestamp HAVING COUNT(*) > 1
    """
    dupes = store.conn.execute(dupe_query, params).fetchall()

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
    invalid_query = f"""
        SELECT symbol, timeframe, timestamp FROM {store.table_ohlcv}
        WHERE high < low {symbol_filter}
    """
    invalid_hl = store.conn.execute(invalid_query, params).fetchall()
    
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
    neg_vol_query = f"""
        SELECT COUNT(*) FROM {store.table_ohlcv}
        WHERE volume < 0 {symbol_filter}
    """
    neg_vol_row = store.conn.execute(neg_vol_query, params).fetchone()
    assert neg_vol_row is not None
    neg_vol = neg_vol_row[0]
    
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
    null_query = f"""
        SELECT
            SUM(CASE WHEN open IS NULL THEN 1 ELSE 0 END),
            SUM(CASE WHEN high IS NULL THEN 1 ELSE 0 END),
            SUM(CASE WHEN low IS NULL THEN 1 ELSE 0 END),
            SUM(CASE WHEN close IS NULL THEN 1 ELSE 0 END),
            SUM(CASE WHEN volume IS NULL THEN 1 ELSE 0 END)
        FROM {store.table_ohlcv}
        WHERE 1=1 {symbol_filter}
    """
    null_counts = store.conn.execute(null_query, params).fetchone()
    assert null_counts is not None
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
    casing_query = f"""
        SELECT DISTINCT symbol FROM {store.table_ohlcv}
        WHERE symbol != UPPER(symbol) {symbol_filter}
    """
    bad_casing = store.conn.execute(casing_query, params).fetchall()
    
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
    anomaly_query = f"""
        SELECT COUNT(*) FROM {store.table_ohlcv}
        WHERE (open > high OR open < low OR close > high OR close < low) {symbol_filter}
    """
    anomaly_row = store.conn.execute(anomaly_query, params).fetchone()
    assert anomaly_row is not None
    anomalies = anomaly_row[0]
    
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


def validate_data_quality(
    store: "HistoricalDataStore",
    symbol: str | None = None,
    timeframe: str | None = None,
) -> dict:
    """
    G2-4: Validate data quality for potential anomalies.

    Checks for:
    - Stuck prices (close unchanged for > 10 consecutive bars)
    - Volume spikes (> 10x average volume)
    - Uniform data (all OHLC equal for extended periods)

    Args:
        store: HistoricalDataStore instance
        symbol: Specific symbol or None for all
        timeframe: Specific timeframe or None for all

    Returns:
        Dict with quality report per symbol/timeframe
    """
    from .historical_data_store import ActivityEmoji, print_activity

    report = {
        "checked_at": datetime.now().isoformat(),
        "symbol_filter": symbol,
        "timeframe_filter": timeframe,
        "issues": [],
        "summary": {
            "stuck_prices": 0,
            "volume_spikes": 0,
            "uniform_data": 0,
        }
    }

    # Build list of symbol/timeframe combinations to check
    if symbol and timeframe:
        combinations = [(symbol.upper(), timeframe)]
    else:
        rows = store.conn.execute(f"""
            SELECT DISTINCT symbol, timeframe FROM {store.table_ohlcv}
        """).fetchall()
        combinations = [(r[0], r[1]) for r in rows]

    print_activity(f"Validating data quality for {len(combinations)} combinations...", ActivityEmoji.SEARCH)

    for sym, tf in combinations:
        # Fetch recent data for analysis
        df = store.conn.execute(f"""
            SELECT timestamp, open, high, low, close, volume
            FROM {store.table_ohlcv}
            WHERE symbol = ? AND timeframe = ?
            ORDER BY timestamp DESC
            LIMIT 1000
        """, [sym, tf]).fetchdf()

        if df.empty or len(df) < 20:
            continue

        # 1. Check for stuck prices (close unchanged for > 10 bars)
        close_diff = df["close"].diff()
        stuck_mask = (close_diff == 0)
        if stuck_mask.sum() > 10:
            # Check for consecutive stuck periods
            stuck_runs = 0
            current_run = 0
            for is_stuck in stuck_mask:
                if is_stuck:
                    current_run += 1
                    if current_run > 10:
                        stuck_runs += 1
                else:
                    current_run = 0

            if stuck_runs > 0:
                report["issues"].append({
                    "symbol": sym,
                    "timeframe": tf,
                    "type": "stuck_prices",
                    "detail": f"Found {stuck_runs} period(s) with > 10 consecutive unchanged closes",
                })
                report["summary"]["stuck_prices"] += 1

        # 2. Check for volume spikes (> 10x average)
        avg_volume = df["volume"].mean()
        if avg_volume > 0:
            spike_mask = df["volume"] > avg_volume * 10
            spike_count = spike_mask.sum()
            if spike_count > 0:
                report["issues"].append({
                    "symbol": sym,
                    "timeframe": tf,
                    "type": "volume_spike",
                    "detail": f"Found {spike_count} bar(s) with volume > 10x average",
                })
                report["summary"]["volume_spikes"] += spike_count

        # 3. Check for uniform data (OHLC all equal for extended periods)
        uniform_mask = (df["open"] == df["high"]) & (df["high"] == df["low"]) & (df["low"] == df["close"])
        if uniform_mask.sum() > 5:
            # Could indicate synthetic or broken data
            report["issues"].append({
                "symbol": sym,
                "timeframe": tf,
                "type": "uniform_ohlc",
                "detail": f"Found {uniform_mask.sum()} bar(s) with O=H=L=C (possibly synthetic)",
            })
            report["summary"]["uniform_data"] += uniform_mask.sum()

    # Print summary
    total_issues = len(report["issues"])
    if total_issues == 0:
        print_activity("Data quality OK: No anomalies detected", ActivityEmoji.SUCCESS)
    else:
        print_activity(f"Data quality: {total_issues} potential issue(s) found", ActivityEmoji.WARNING)
        for issue in report["issues"][:5]:  # Show first 5
            print(f"  - {issue['symbol']} {issue['timeframe']}: {issue['type']} - {issue['detail']}")
        if total_issues > 5:
            print(f"  ... and {total_issues - 5} more")

    return report

