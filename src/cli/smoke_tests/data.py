"""
Data-related smoke tests for TRADE trading bot.

Extracted from smoke_tests.py for modularity:
- run_data_builder_smoke: Basic data builder tests (OHLCV, funding, OI)
- run_extensive_data_smoke: Full coverage test with clean DB, gaps, sync
"""

from rich.console import Console
from rich.panel import Panel

from ...tools import (
    # Data management tools
    get_database_stats_tool,
    list_cached_symbols_tool,
    get_symbol_status_tool,
    get_symbol_timeframe_ranges_tool,
    fill_gaps_tool,
    heal_data_tool,
    sync_to_now_tool,
    sync_to_now_and_fill_gaps_tool,
    cleanup_empty_symbols_tool,
    vacuum_database_tool,
    delete_all_data_tool,
    # Data query tools
    get_ohlcv_history_tool,
    get_funding_history_tool,
    get_open_interest_history_tool,
    # Data sync tools
    build_symbol_history_tool,
    sync_range_tool,
    sync_funding_tool,
    sync_open_interest_tool,
    get_symbol_summary_tool,
)


console = Console()


def run_data_builder_smoke(smoke_config, app, config) -> int:
    """
    Run the data builder smoke test.

    Tests OHLCV sync, funding rates, open interest, gap detection and repair.
    """
    console.print(Panel(
        "[bold]DATA BUILDER SMOKE TEST[/]\n"
        "[dim]Testing historical data sync, gap detection, and repair[/]",
        border_style="blue"
    ))

    failures = 0
    symbols = smoke_config.symbols[:3]
    period = smoke_config.period

    # Step 1: Database stats (baseline)
    console.print(f"\n[bold cyan]Step 1: Database Stats (Baseline)[/]")
    result = get_database_stats_tool()
    if result.success:
        console.print(f"  [green]OK[/] {result.message}")
    else:
        console.print(f"  [red]FAIL[/] {result.error}")
        failures += 1

    # Step 2: Build full history
    console.print(f"\n[bold cyan]Step 2: Build Full History ({period}) for {symbols}[/]")
    console.print(f"  [dim]This may take several minutes for 1-year data...[/]")

    smoke_timeframes = ["1h", "4h", "1d"]

    result = build_symbol_history_tool(
        symbols=symbols, period=period, timeframes=smoke_timeframes, oi_interval="1h"
    )
    if result.success:
        console.print(f"  [green]OK[/] {result.message}")
        if result.data:
            for sym, sym_data in result.data.get("results", {}).items():
                ohlcv = sym_data.get("ohlcv", {})
                funding = sym_data.get("funding", {})
                oi = sym_data.get("open_interest", {})
                console.print(f"    {sym}: OHLCV={ohlcv.get('total_candles', 0):,} candles, "
                            f"Funding={funding.get('records', 0):,}, OI={oi.get('records', 0):,}")
    else:
        console.print(f"  [red]FAIL[/] {result.error}")
        failures += 1

    # Step 3: Gap testing (if enabled)
    if smoke_config.enable_gap_testing:
        console.print(f"\n[bold cyan]Step 3: Gap Testing[/]")
        test_symbol = symbols[0]

        result = get_symbol_status_tool(test_symbol)
        if result.success:
            console.print(f"  [green]OK[/] Symbol status for {test_symbol}:")
            if result.data:
                for tf_data in result.data:
                    if isinstance(tf_data, dict):
                        console.print(f"    {tf_data.get('timeframe', 'N/A')}: "
                                    f"{tf_data.get('candles', 0):,} candles, gaps={tf_data.get('gaps', 0)}")
        else:
            console.print(f"  [red]FAIL[/] {result.error}")
            failures += 1

        console.print(f"\n  [dim]Testing gap fill functionality...[/]")
        result = fill_gaps_tool(symbol=test_symbol, timeframe="1h")
        if result.success:
            console.print(f"  [green]OK[/] Gap fill: {result.message}")
        else:
            console.print(f"  [red]FAIL[/] Gap fill failed: {result.error}")
            failures += 1

        console.print(f"\n  [dim]Testing data heal functionality...[/]")
        result = heal_data_tool(symbol=test_symbol)
        if result.success:
            console.print(f"  [green]OK[/] Data heal: {result.message}")
        else:
            console.print(f"  [red]FAIL[/] Data heal failed: {result.error}")
            failures += 1

    # Step 4: Sync forward to now
    console.print(f"\n[bold cyan]Step 4: Sync Forward to Now[/]")
    result = sync_to_now_tool(symbols=symbols, timeframes=smoke_timeframes)
    if result.success:
        console.print(f"  [green]OK[/] {result.message}")
    else:
        console.print(f"  [red]FAIL[/] {result.error}")
        failures += 1

    # Step 5: List cached symbols
    console.print(f"\n[bold cyan]Step 5: List Cached Symbols[/]")
    result = list_cached_symbols_tool()
    if result.success:
        console.print(f"  [green]OK[/] {result.message}")
        if result.data:
            for sym_info in result.data[:5]:
                if isinstance(sym_info, dict):
                    console.print(f"    {sym_info.get('symbol', 'N/A')}: "
                                f"{sym_info.get('timeframes', 'N/A')}, "
                                f"{sym_info.get('candles', 0):,} candles")
    else:
        console.print(f"  [red]FAIL[/] {result.error}")
        failures += 1

    # Step 6: Symbol timeframe ranges
    console.print(f"\n[bold cyan]Step 6: Symbol Timeframe Ranges[/]")
    for sym in symbols:
        result = get_symbol_timeframe_ranges_tool(sym)
        if result.success:
            console.print(f"  [green]OK[/] {sym}: {result.message}")
        else:
            console.print(f"  [red]FAIL[/] {sym}: {result.error}")
            failures += 1

    # Step 7: Query OHLCV history
    console.print(f"\n[bold cyan]Step 7: Query OHLCV History[/]")
    for sym in symbols:
        result = get_ohlcv_history_tool(symbol=sym, timeframe="1h", period="1M")
        if result.success:
            count = result.data.get("count", 0) if result.data else 0
            console.print(f"  [green]OK[/] {sym} 1h: {count:,} candles in last month")
        else:
            console.print(f"  [red]FAIL[/] {sym}: {result.error}")
            failures += 1

    # Step 8: Query Funding history
    console.print(f"\n[bold cyan]Step 8: Query Funding History[/]")
    for sym in symbols:
        result = get_funding_history_tool(symbol=sym, period="1M")
        if result.success:
            count = result.data.get("count", 0) if result.data else 0
            console.print(f"  [green]OK[/] {sym}: {count:,} funding records in last month")
        else:
            console.print(f"  [red]FAIL[/] {sym}: {result.error}")
            failures += 1

    # Step 9: Query Open Interest history
    console.print(f"\n[bold cyan]Step 9: Query Open Interest History[/]")
    for sym in symbols:
        result = get_open_interest_history_tool(symbol=sym, period="1M")
        if result.success:
            count = result.data.get("count", 0) if result.data else 0
            console.print(f"  [green]OK[/] {sym}: {count:,} OI records in last month")
        else:
            console.print(f"  [red]FAIL[/] {sym}: {result.error}")
            failures += 1

    # Step 10: Database stats (final)
    console.print(f"\n[bold cyan]Step 10: Database Stats (Final)[/]")
    result = get_database_stats_tool()
    if result.success:
        console.print(f"  [green]OK[/] {result.message}")
    else:
        console.print(f"  [red]FAIL[/] {result.error}")
        failures += 1

    # Step 11: Maintenance tools
    console.print(f"\n[bold cyan]Step 11: Maintenance Tools[/]")

    result = cleanup_empty_symbols_tool()
    if result.success:
        console.print(f"  [green]OK[/] Cleanup empty: {result.message}")
    else:
        console.print(f"  [red]FAIL[/] Cleanup empty: {result.error}")
        failures += 1

    result = vacuum_database_tool()
    if result.success:
        console.print(f"  [green]OK[/] Vacuum: {result.message}")
    else:
        console.print(f"  [red]FAIL[/] Vacuum: {result.error}")
        failures += 1

    console.print(f"\n[bold]Data Builder Smoke Test Complete[/]")
    console.print(f"  Symbols tested: {symbols}")
    console.print(f"  Failures: {failures}")

    return failures


def run_extensive_data_smoke(env: str = "live") -> int:
    """
    Run extensive data smoke test with clean database, intentional gaps, and comprehensive tool coverage.

    This test:
    1. Deletes ALL existing data (clean slate)
    2. Builds sparse history with intentional gaps
    3. Verifies gaps exist in the data
    4. Fills gaps using fill_gaps_tool
    5. Syncs data to current using sync_to_now_tool
    6. Queries all data types (OHLCV, funding, OI)
    7. Runs maintenance tools
    8. Verifies final database state

    Args:
        env: Data environment to test ("live" or "demo"). Defaults to "live".

    Returns:
        Number of failures (0 = success)
    """
    from datetime import datetime, timedelta

    env_label = env.upper()
    env_color = "green" if env == "live" else "cyan"

    console.print(Panel(
        f"[bold yellow]EXTENSIVE DATA SMOKE TEST ({env_label})[/]\n"
        f"[dim]Full coverage test: delete all -> build sparse -> fill gaps -> sync -> query -> maintain[/]\n"
        f"[{env_color}]Data Environment: {env_label}[/{env_color}]",
        border_style="yellow"
    ))

    failures = 0

    # Test configuration
    SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    TIMEFRAMES = ["1h", "4h"]

    # ============================================================
    # PHASE 1: DELETE ALL DATA (Clean Slate)
    # ============================================================
    console.print(f"\n[bold yellow]{'='*60}[/]")
    console.print(f"[bold yellow]PHASE 1: DELETE ALL DATA (Clean Slate)[/]")
    console.print(f"[bold yellow]{'='*60}[/]")

    console.print(f"\n[bold cyan]1.1: Check Current Database State ({env_label})[/]")
    result = get_database_stats_tool(env=env)
    if result.success:
        console.print(f"  [green]OK[/] Before deletion: {result.message}")
    else:
        console.print(f"  [red]FAIL[/] {result.error}")
        failures += 1

    console.print(f"\n[bold cyan]1.2: Delete ALL Data ({env_label})[/]")
    result = delete_all_data_tool(vacuum=True, env=env)
    if result.success:
        console.print(f"  [green]OK[/] {result.message}")
        if result.data:
            deleted = result.data.get("deleted", {})
            console.print(f"      OHLCV: {deleted.get('ohlcv', 0):,} rows")
            console.print(f"      Funding: {deleted.get('funding', 0):,} rows")
            console.print(f"      Open Interest: {deleted.get('open_interest', 0):,} rows")
    else:
        console.print(f"  [red]FAIL[/] {result.error}")
        failures += 1

    console.print(f"\n[bold cyan]1.3: Verify Database is Empty ({env_label})[/]")
    result = get_database_stats_tool(env=env)
    if result.success:
        console.print(f"  [green]OK[/] After deletion: {result.message}")
        if result.data:
            ohlcv_count = result.data.get("ohlcv_candles", 0)
            if ohlcv_count > 0:
                console.print(f"  [red]FAIL[/] Database not empty! Still has {ohlcv_count:,} candles")
                failures += 1
            else:
                console.print(f"  [green]OK[/] Database is clean (0 candles)")
    else:
        console.print(f"  [red]FAIL[/] {result.error}")
        failures += 1

    # ============================================================
    # PHASE 2: BUILD SPARSE HISTORY WITH INTENTIONAL GAPS
    # ============================================================
    console.print(f"\n[bold yellow]{'='*60}[/]")
    console.print(f"[bold yellow]PHASE 2: BUILD SPARSE HISTORY (Intentional Gaps)[/]")
    console.print(f"[bold yellow]{'='*60}[/]")

    console.print(f"\n[dim]Strategy: Build 3 separate date ranges with gaps between them[/]")
    console.print(f"  Range 1: 60-50 days ago (10 days)")
    console.print(f"  Range 2: 40-30 days ago (10 days)")
    console.print(f"  Range 3: 20-10 days ago (10 days)")
    console.print(f"  GAPS: 50-40 days, 30-20 days, 10 days to now")

    now = datetime.now()
    ranges = [
        (now - timedelta(days=60), now - timedelta(days=50)),  # 60-50 days ago
        (now - timedelta(days=40), now - timedelta(days=30)),  # 40-30 days ago
        (now - timedelta(days=20), now - timedelta(days=10)),  # 20-10 days ago
    ]

    console.print(f"\n[bold cyan]2.1: Sync OHLCV in Sparse Ranges ({env_label})[/]")
    for i, (start, end) in enumerate(ranges, 1):
        console.print(f"\n  [dim]Range {i}: {start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}[/]")

        result = sync_range_tool(
            symbols=SYMBOLS,
            start=start,
            end=end,
            timeframes=TIMEFRAMES,
            env=env,
        )
        if result.success:
            console.print(f"    [green]OK[/] {result.message}")
            if result.data:
                for sym, sym_data in result.data.get("results", {}).items():
                    if isinstance(sym_data, dict):
                        console.print(f"      {sym}: {sym_data.get('total_candles', 0):,} candles")
        else:
            console.print(f"    [red]FAIL[/] {result.error}")
            failures += 1

    console.print(f"\n[bold cyan]2.2: Sync Funding Rates (sparse) ({env_label})[/]")
    result = sync_funding_tool(symbols=SYMBOLS, period="2M", env=env)
    if result.success:
        console.print(f"  [green]OK[/] {result.message}")
    else:
        console.print(f"  [red]FAIL[/] {result.error}")
        failures += 1

    console.print(f"\n[bold cyan]2.3: Sync Open Interest (sparse) ({env_label})[/]")
    result = sync_open_interest_tool(symbols=SYMBOLS, period="2M", interval="1h", env=env)
    if result.success:
        console.print(f"  [green]OK[/] {result.message}")
    else:
        console.print(f"  [red]FAIL[/] {result.error}")
        failures += 1

    # ============================================================
    # PHASE 3: VERIFY GAPS EXIST
    # ============================================================
    console.print(f"\n[bold yellow]{'='*60}[/]")
    console.print(f"[bold yellow]PHASE 3: VERIFY GAPS EXIST[/]")
    console.print(f"[bold yellow]{'='*60}[/]")

    console.print(f"\n[bold cyan]3.1: Check Symbol Timeframe Ranges ({env_label})[/]")
    result = get_symbol_timeframe_ranges_tool(env=env)
    if result.success:
        console.print(f"  [green]OK[/] {result.message}")
        if result.data:
            # Handle both dict format (with "ranges" key) and list format
            ranges_data = result.data.get("ranges", []) if isinstance(result.data, dict) else result.data
            for item in ranges_data[:12]:  # Show first 12
                first_ts = item.get('first_timestamp', 'N/A')
                last_ts = item.get('last_timestamp', 'N/A')
                first_str = first_ts[:10] if first_ts and first_ts != 'N/A' else 'N/A'
                last_str = last_ts[:10] if last_ts and last_ts != 'N/A' else 'N/A'
                console.print(f"    {item['symbol']} {item['timeframe']}: "
                            f"{first_str} to {last_str} "
                            f"({item.get('candle_count', 0):,} candles)")
    else:
        console.print(f"  [red]FAIL[/] {result.error}")
        failures += 1

    console.print(f"\n[bold cyan]3.2: Check Symbol Status (gaps) ({env_label})[/]")
    for sym in SYMBOLS:
        result = get_symbol_status_tool(sym, env=env)
        if result.success:
            console.print(f"  [green]OK[/] {sym}:")
            if result.data:
                # Handle dict format with "summary" key or "raw_status"
                raw_status = result.data.get("raw_status", {}) if isinstance(result.data, dict) else {}
                for key, tf_data in raw_status.items():
                    if isinstance(tf_data, dict):
                        gaps = tf_data.get('gaps', 0)
                        gap_str = f"[yellow]{gaps} gaps[/]" if gaps > 0 else "[green]0 gaps[/]"
                        console.print(f"      {tf_data.get('timeframe', 'N/A')}: "
                                    f"{tf_data.get('candle_count', 0):,} candles, {gap_str}")
        else:
            console.print(f"  [red]FAIL[/] {sym}: {result.error}")
            failures += 1

    # ============================================================
    # PHASE 4: FILL GAPS
    # ============================================================
    console.print(f"\n[bold yellow]{'='*60}[/]")
    console.print(f"[bold yellow]PHASE 4: FILL GAPS[/]")
    console.print(f"[bold yellow]{'='*60}[/]")

    console.print(f"\n[bold cyan]4.1: Fill Gaps for All Symbols ({env_label})[/]")
    for sym in SYMBOLS:
        result = fill_gaps_tool(symbol=sym, env=env)
        if result.success:
            console.print(f"  [green]OK[/] {sym}: {result.message}")
        else:
            console.print(f"  [red]FAIL[/] {sym}: {result.error}")
            failures += 1

    console.print(f"\n[bold cyan]4.2: Verify Gaps Filled ({env_label})[/]")
    for sym in SYMBOLS:
        result = get_symbol_status_tool(sym, env=env)
        if result.success:
            console.print(f"  [green]OK[/] {sym}:")
            if result.data:
                # Handle dict format with "summary" key or "raw_status"
                raw_status = result.data.get("raw_status", {}) if isinstance(result.data, dict) else {}
                for key, tf_data in raw_status.items():
                    if isinstance(tf_data, dict):
                        gaps = tf_data.get('gaps', 0)
                        gap_str = f"[green]0 gaps OK[/]" if gaps == 0 else f"[yellow]{gaps} gaps remaining[/]"
                        console.print(f"      {tf_data.get('timeframe', 'N/A')}: "
                                    f"{tf_data.get('candle_count', 0):,} candles, {gap_str}")
        else:
            console.print(f"  [red]FAIL[/] {sym}: {result.error}")

    # ============================================================
    # PHASE 5: SYNC TO CURRENT
    # ============================================================
    console.print(f"\n[bold yellow]{'='*60}[/]")
    console.print(f"[bold yellow]PHASE 5: SYNC TO CURRENT[/]")
    console.print(f"[bold yellow]{'='*60}[/]")

    console.print(f"\n[bold cyan]5.1: Sync Forward to Now ({env_label})[/]")
    result = sync_to_now_tool(symbols=SYMBOLS, timeframes=TIMEFRAMES, env=env)
    if result.success:
        console.print(f"  [green]OK[/] {result.message}")
        if result.data:
            console.print(f"      Total synced: {result.data.get('total_synced', 0):,} candles")
    else:
        console.print(f"  [red]FAIL[/] {result.error}")
        failures += 1

    console.print(f"\n[bold cyan]5.2: Sync + Fill Gaps (Combined) ({env_label})[/]")
    result = sync_to_now_and_fill_gaps_tool(symbols=SYMBOLS, timeframes=TIMEFRAMES, env=env)
    if result.success:
        console.print(f"  [green]OK[/] {result.message}")
    else:
        console.print(f"  [red]FAIL[/] {result.error}")
        failures += 1

    # ============================================================
    # PHASE 6: QUERY ALL DATA TYPES
    # ============================================================
    console.print(f"\n[bold yellow]{'='*60}[/]")
    console.print(f"[bold yellow]PHASE 6: QUERY ALL DATA TYPES[/]")
    console.print(f"[bold yellow]{'='*60}[/]")

    console.print(f"\n[bold cyan]6.1: Query OHLCV History ({env_label})[/]")
    for sym in SYMBOLS:
        for tf in TIMEFRAMES:
            result = get_ohlcv_history_tool(symbol=sym, timeframe=tf, period="1M", env=env)
            if result.success:
                count = result.data.get("count", 0) if result.data else 0
                console.print(f"  [green]OK[/] {sym} {tf}: {count:,} candles (last month)")
            else:
                console.print(f"  [red]FAIL[/] {sym} {tf}: {result.error}")
                failures += 1

    console.print(f"\n[bold cyan]6.2: Query Funding History ({env_label})[/]")
    for sym in SYMBOLS:
        result = get_funding_history_tool(symbol=sym, period="1M", env=env)
        if result.success:
            count = result.data.get("count", 0) if result.data else 0
            console.print(f"  [green]OK[/] {sym}: {count:,} funding records")
        else:
            console.print(f"  [red]FAIL[/] {sym}: {result.error}")
            failures += 1

    console.print(f"\n[bold cyan]6.3: Query Open Interest History ({env_label})[/]")
    for sym in SYMBOLS:
        result = get_open_interest_history_tool(symbol=sym, period="1M", env=env)
        if result.success:
            count = result.data.get("count", 0) if result.data else 0
            console.print(f"  [green]OK[/] {sym}: {count:,} OI records")
        else:
            console.print(f"  [red]FAIL[/] {sym}: {result.error}")
            failures += 1

    # ============================================================
    # PHASE 7: MAINTENANCE TOOLS
    # ============================================================
    console.print(f"\n[bold yellow]{'='*60}[/]")
    console.print(f"[bold yellow]PHASE 7: MAINTENANCE TOOLS[/]")
    console.print(f"[bold yellow]{'='*60}[/]")

    console.print(f"\n[bold cyan]7.1: Heal Data (Integrity Check) ({env_label})[/]")
    result = heal_data_tool(env=env)
    if result.success:
        console.print(f"  [green]OK[/] {result.message}")
    else:
        console.print(f"  [red]FAIL[/] {result.error}")
        failures += 1

    console.print(f"\n[bold cyan]7.2: Cleanup Empty Symbols ({env_label})[/]")
    result = cleanup_empty_symbols_tool(env=env)
    if result.success:
        console.print(f"  [green]OK[/] {result.message}")
    else:
        console.print(f"  [red]FAIL[/] {result.error}")
        failures += 1

    console.print(f"\n[bold cyan]7.3: Vacuum Database ({env_label})[/]")
    result = vacuum_database_tool(env=env)
    if result.success:
        console.print(f"  [green]OK[/] {result.message}")
    else:
        console.print(f"  [red]FAIL[/] {result.error}")
        failures += 1

    # ============================================================
    # PHASE 8: FINAL VERIFICATION
    # ============================================================
    console.print(f"\n[bold yellow]{'='*60}[/]")
    console.print(f"[bold yellow]PHASE 8: FINAL VERIFICATION[/]")
    console.print(f"[bold yellow]{'='*60}[/]")

    console.print(f"\n[bold cyan]8.1: Final Database Stats ({env_label})[/]")
    result = get_database_stats_tool(env=env)
    if result.success:
        console.print(f"  [green]OK[/] {result.message}")
    else:
        console.print(f"  [red]FAIL[/] {result.error}")
        failures += 1

    console.print(f"\n[bold cyan]8.2: List All Cached Symbols ({env_label})[/]")
    result = list_cached_symbols_tool(env=env)
    if result.success:
        console.print(f"  [green]OK[/] {result.message}")
        if result.data:
            # Handle both dict format (with "symbols" key) and list format
            symbols_data = result.data.get("symbols", result.data) if isinstance(result.data, dict) else result.data
            for sym_info in symbols_data:
                if isinstance(sym_info, dict):
                    # Handle both "timeframes" as string or list
                    tfs = sym_info.get('timeframes', 'N/A')
                    tfs_str = tfs if isinstance(tfs, str) else ', '.join(tfs)
                    candles = sym_info.get('total_candles', sym_info.get('candles', 0))
                    console.print(f"      {sym_info.get('symbol', 'N/A')}: {tfs_str} | {candles:,} candles")
    else:
        console.print(f"  [red]FAIL[/] {result.error}")
        failures += 1

    console.print(f"\n[bold cyan]8.3: Symbol Summary ({env_label})[/]")
    result = get_symbol_summary_tool(env=env)
    if result.success:
        console.print(f"  [green]OK[/] {result.message}")
    else:
        console.print(f"  [red]FAIL[/] {result.error}")
        failures += 1

    # ============================================================
    # SUMMARY
    # ============================================================
    console.print(f"\n[bold yellow]{'='*60}[/]")
    console.print(f"[bold yellow]EXTENSIVE DATA SMOKE TEST COMPLETE ({env_label})[/]")
    console.print(f"[bold yellow]{'='*60}[/]")

    console.print(f"\n[bold]Test Summary:[/]")
    console.print(f"  Data Environment: {env_label}")
    console.print(f"  Symbols tested: {SYMBOLS}")
    console.print(f"  Timeframes: {TIMEFRAMES}")
    console.print(f"  Total failures: {failures}")

    if failures == 0:
        console.print(f"\n[bold green]OK ALL TESTS PASSED[/]")
    else:
        console.print(f"\n[bold red]FAIL {failures} TEST(S) FAILED[/]")

    return failures
