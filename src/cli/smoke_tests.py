"""
CLI Smoke Tests for TRADE trading bot.

Non-interactive test suites for validating CLI functionality:
- run_smoke_suite: Main entry point for smoke tests
- run_data_builder_smoke: Data builder tests (OHLCV, funding, OI)
- run_full_cli_smoke: Full CLI tests (data + trading + diagnostics)
"""

from rich.console import Console
from rich.panel import Panel

from ..tools import (
    ToolResult,
    # Data tools
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
    get_ohlcv_history_tool,
    get_funding_history_tool,
    get_open_interest_history_tool,
    build_symbol_history_tool,
    sync_range_tool,
    sync_funding_tool,
    sync_open_interest_tool,
    get_symbol_summary_tool,
    # Account tools
    get_account_balance_tool,
    get_total_exposure_tool,
    get_account_info_tool,
    get_portfolio_snapshot_tool,
    get_order_history_tool,
    get_closed_pnl_tool,
    get_collateral_info_tool,
    # Position tools
    list_open_positions_tool,
    get_position_detail_tool,
    get_risk_limits_tool,
    set_stop_loss_tool,
    remove_stop_loss_tool,
    set_take_profit_tool,
    remove_take_profit_tool,
    set_trailing_stop_tool,
    set_trailing_stop_by_percent_tool,
    close_position_tool,
    panic_close_all_tool,
    # Order tools - ALL types
    set_leverage_tool,
    market_buy_tool,
    market_sell_tool,
    market_buy_with_tpsl_tool,
    market_sell_with_tpsl_tool,
    limit_buy_tool,
    limit_sell_tool,
    stop_market_buy_tool,
    stop_market_sell_tool,
    stop_limit_buy_tool,
    stop_limit_sell_tool,
    get_open_orders_tool,
    cancel_order_tool,
    cancel_all_orders_tool,
    amend_order_tool,
    partial_close_position_tool,
    # Market data tools
    get_price_tool,
    get_ohlcv_tool,
    get_funding_rate_tool,
    get_open_interest_tool,
    get_orderbook_tool,
    get_instruments_tool,
    # Diagnostics tools
    test_connection_tool,
    get_server_time_offset_tool,
    get_rate_limit_status_tool,
    get_websocket_status_tool,
    exchange_health_check_tool,
    get_api_environment_tool,
)


console = Console()


def run_smoke_suite(mode: str, app, config) -> int:
    """
    Run the smoke test suite in the specified mode.
    
    Args:
        mode: "data" for data builder only, "full" for all CLI features
        app: Application instance
        config: Config instance
    
    Returns:
        Exit code: 0 for success, non-zero for failure
    """
    console.print(f"\n[bold cyan]{'='*60}[/]")
    console.print(f"[bold cyan]SMOKE TEST SUITE - Mode: {mode.upper()}[/]")
    console.print(f"[bold cyan]{'='*60}[/]\n")
    
    smoke_config = config.smoke
    
    console.print(f"[dim]Smoke Config:[/]")
    console.print(f"  Symbols: {smoke_config.symbols}")
    console.print(f"  Period: {smoke_config.period}")
    console.print(f"  USD Size: ${smoke_config.usd_size}")
    console.print(f"  Gap Testing: {smoke_config.enable_gap_testing}")
    console.print()
    
    total_failures = 0
    
    if mode == "data":
        failures = run_data_builder_smoke(smoke_config, app, config)
        total_failures += failures
    elif mode == "full":
        failures = run_full_cli_smoke(smoke_config, app, config)
        total_failures += failures
    
    console.print(f"\n[bold cyan]{'='*60}[/]")
    if total_failures == 0:
        console.print(f"[bold green]SMOKE TEST PASSED[/] - All tests completed successfully")
    else:
        console.print(f"[bold red]SMOKE TEST FAILED[/] - {total_failures} failure(s)")
    console.print(f"[bold cyan]{'='*60}[/]\n")
    
    return 0 if total_failures == 0 else 1


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


def run_full_cli_smoke(smoke_config, app, config) -> int:
    """
    Run the full CLI smoke test.
    
    Tests all CLI features: data builder, account, positions, orders, market data, diagnostics.
    """
    console.print(Panel(
        "[bold]FULL CLI SMOKE TEST[/]\n"
        "[dim]Testing all CLI features in DEMO mode[/]",
        border_style="magenta"
    ))
    
    failures = 0
    symbols = smoke_config.symbols[:3]
    order_test_symbol = symbols[-1] if len(symbols) > 0 else symbols[0]
    market_test_symbol = symbols[0]
    usd_size = smoke_config.usd_size
    
    # PART 1: Data Builder
    console.print(f"\n[bold magenta]{'='*50}[/]")
    console.print(f"[bold magenta]PART 1: DATA BUILDER[/]")
    console.print(f"[bold magenta]{'='*50}[/]")
    failures += run_data_builder_smoke(smoke_config, app, config)
    
    # PART 2: Account & Balance
    console.print(f"\n[bold magenta]{'='*50}[/]")
    console.print(f"[bold magenta]PART 2: ACCOUNT & BALANCE[/]")
    console.print(f"[bold magenta]{'='*50}[/]")
    
    for test_name, tool_fn in [
        ("2.1: Account Balance", get_account_balance_tool),
        ("2.2: Total Exposure", get_total_exposure_tool),
        ("2.3: Account Info", get_account_info_tool),
        ("2.4: Portfolio Snapshot", get_portfolio_snapshot_tool),
        ("2.7: Collateral Info", get_collateral_info_tool),
    ]:
        console.print(f"\n[bold cyan]{test_name}[/]")
        result = tool_fn()
        if result.success:
            console.print(f"  [green]OK[/] {result.message}")
        else:
            console.print(f"  [red]FAIL[/] {result.error}")
            failures += 1
    
    console.print(f"\n[bold cyan]2.5: Order History (7d)[/]")
    result = get_order_history_tool(window="7d", limit=10)
    if result.success:
        console.print(f"  [green]OK[/] {result.message}")
    else:
        console.print(f"  [red]FAIL[/] {result.error}")
        failures += 1
    
    console.print(f"\n[bold cyan]2.6: Closed PnL (7d)[/]")
    result = get_closed_pnl_tool(window="7d", limit=10)
    if result.success:
        console.print(f"  [green]OK[/] {result.message}")
    else:
        console.print(f"  [red]FAIL[/] {result.error}")
        failures += 1
    
    # PART 3: Positions
    console.print(f"\n[bold magenta]{'='*50}[/]")
    console.print(f"[bold magenta]PART 3: POSITIONS[/]")
    console.print(f"[bold magenta]{'='*50}[/]")
    
    console.print(f"\n[bold cyan]3.1: List Open Positions[/]")
    result = list_open_positions_tool()
    if result.success:
        console.print(f"  [green]OK[/] {result.message}")
    else:
        console.print(f"  [red]FAIL[/] {result.error}")
        failures += 1
    
    console.print(f"\n[bold cyan]3.2: Risk Limits for {market_test_symbol}[/]")
    result = get_risk_limits_tool(market_test_symbol)
    if result.success:
        console.print(f"  [green]OK[/] {result.message}")
    else:
        console.print(f"  [red]FAIL[/] {result.error}")
        failures += 1
    
    # PART 4: Orders (Demo Trading)
    console.print(f"\n[bold magenta]{'='*50}[/]")
    console.print(f"[bold magenta]PART 4: ORDERS (Demo Trading)[/]")
    console.print(f"[bold magenta]{'='*50}[/]")
    
    console.print(f"\n[bold cyan]4.1: Set Leverage for {order_test_symbol}[/]")
    result = set_leverage_tool(order_test_symbol, 2)
    if result.success:
        console.print(f"  [green]OK[/] {result.message}")
    else:
        console.print(f"  [yellow]![/] {result.error} (may already be set)")
    
    console.print(f"\n[bold cyan]4.2: Get Current Price for {order_test_symbol}[/]")
    price_result = get_price_tool(order_test_symbol)
    current_price = 0
    if price_result.success and price_result.data:
        current_price = float(price_result.data.get("price", 0))
        console.print(f"  [green]OK[/] Current price: ${current_price:,.4f}")
    else:
        console.print(f"  [red]FAIL[/] Could not get price: {price_result.error}")
        failures += 1
    
    if current_price > 0:
        limit_price = round(current_price * 0.95, 2)
        
        console.print(f"\n[bold cyan]4.3: Place Limit Buy Order[/]")
        console.print(f"  [dim]Symbol: {order_test_symbol}, Size: ${usd_size}, Price: ${limit_price}[/]")
        result = limit_buy_tool(order_test_symbol, usd_size, limit_price)
        order_id = None
        if result.success:
            console.print(f"  [green]OK[/] {result.message}")
            order_id = result.data.get("order_id") if result.data else None
        else:
            console.print(f"  [red]FAIL[/] {result.error}")
            failures += 1
        
        console.print(f"\n[bold cyan]4.4: Get Open Orders[/]")
        result = get_open_orders_tool(symbol=order_test_symbol)
        if result.success:
            console.print(f"  [green]OK[/] {result.message}")
        else:
            console.print(f"  [red]FAIL[/] {result.error}")
            failures += 1
        
        if order_id:
            console.print(f"\n[bold cyan]4.5: Cancel Order[/]")
            result = cancel_order_tool(order_test_symbol, order_id=order_id)
            if result.success:
                console.print(f"  [green]OK[/] {result.message}")
            else:
                console.print(f"  [yellow]![/] {result.error}")
        
        console.print(f"\n[bold cyan]4.6: Cancel All Orders[/]")
        result = cancel_all_orders_tool(symbol=order_test_symbol)
        if result.success:
            console.print(f"  [green]OK[/] {result.message}")
        else:
            console.print(f"  [yellow]![/] {result.error}")
    
    # PART 5: Market Data
    console.print(f"\n[bold magenta]{'='*50}[/]")
    console.print(f"[bold magenta]PART 5: MARKET DATA[/]")
    console.print(f"[bold magenta]{'='*50}[/]")
    
    console.print(f"\n[bold cyan]5.1: Get Price[/]")
    for sym in symbols:
        result = get_price_tool(sym)
        if result.success:
            price = result.data.get("price", "N/A") if result.data else "N/A"
            console.print(f"  [green]OK[/] {sym}: ${price:,.2f}" if isinstance(price, (int, float)) else f"  [green]OK[/] {sym}: ${price}")
        else:
            console.print(f"  [red]FAIL[/] {sym}: {result.error}")
            failures += 1
    
    for test_name, tool_fn, kwargs in [
        ("5.2: Get OHLCV", get_ohlcv_tool, {"symbol": market_test_symbol, "interval": "60", "limit": 10}),
        ("5.3: Get Funding Rate", get_funding_rate_tool, {"symbol": market_test_symbol}),
        ("5.4: Get Open Interest", get_open_interest_tool, {"symbol": market_test_symbol}),
        ("5.5: Get Orderbook", get_orderbook_tool, {"symbol": market_test_symbol, "limit": 5}),
        ("5.6: Get Instruments", get_instruments_tool, {"symbol": market_test_symbol}),
    ]:
        console.print(f"\n[bold cyan]{test_name}[/]")
        result = tool_fn(**kwargs)
        if result.success:
            console.print(f"  [green]OK[/] {market_test_symbol}: OK")
        else:
            console.print(f"  [red]FAIL[/] {result.error}")
            failures += 1
    
    # PART 6: Diagnostics & Health
    console.print(f"\n[bold magenta]{'='*50}[/]")
    console.print(f"[bold magenta]PART 6: DIAGNOSTICS & HEALTH[/]")
    console.print(f"[bold magenta]{'='*50}[/]")
    
    for test_name, tool_fn, required in [
        ("6.1: Connection Test", test_connection_tool, True),
        ("6.2: Server Time Offset", get_server_time_offset_tool, True),
        ("6.3: Rate Limit Status", get_rate_limit_status_tool, True),
        ("6.4: WebSocket Status", get_websocket_status_tool, False),
        ("6.6: API Environment", get_api_environment_tool, True),
    ]:
        console.print(f"\n[bold cyan]{test_name}[/]")
        result = tool_fn()
        if result.success:
            console.print(f"  [green]OK[/] {result.message}")
        else:
            if required:
                console.print(f"  [red]FAIL[/] {result.error}")
                failures += 1
            else:
                console.print(f"  [yellow]![/] {result.error} (optional)")
    
    console.print(f"\n[bold cyan]6.5: Exchange Health Check[/]")
    result = exchange_health_check_tool(symbol=market_test_symbol)
    if result.success:
        console.print(f"  [green]OK[/] {result.message}")
    else:
        console.print(f"  [red]FAIL[/] {result.error}")
        failures += 1
    
    # PART 7: Panic Flow (Safe Test)
    console.print(f"\n[bold magenta]{'='*50}[/]")
    console.print(f"[bold magenta]PART 7: PANIC FLOW (Safe Test)[/]")
    console.print(f"[bold magenta]{'='*50}[/]")
    
    console.print(f"\n[bold cyan]7.1: Panic Close All (Demo Mode)[/]")
    console.print(f"  [dim]This is safe - we're in DEMO mode with no real positions[/]")
    result = panic_close_all_tool(reason="Smoke test panic verification")
    if result.success:
        console.print(f"  [green]OK[/] Panic flow works: {result.message}")
    else:
        console.print(f"  [yellow]![/] {result.error} (expected if no positions)")
    
    console.print(f"\n[bold]Full CLI Smoke Test Complete[/]")
    console.print(f"  Symbols tested: {symbols}")
    console.print(f"  Total failures: {failures}")
    
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
        f"[dim]Full coverage test: delete all → build sparse → fill gaps → sync → query → maintain[/]\n"
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


def run_comprehensive_order_smoke() -> int:
    """
    Comprehensive test of ALL order types on DEMO account.
    
    Tests:
    - Market orders (buy/sell)
    - Market orders with TP/SL
    - Limit orders (buy/sell)
    - Stop market orders
    - Stop limit orders  
    - Position TP/SL management
    - Trailing stops
    - Order management (amend, cancel)
    
    Returns:
        Number of failures (0 = success)
    """
    console.print(Panel(
        "[bold magenta]COMPREHENSIVE ORDER SMOKE TEST[/]\n"
        "[dim]Testing ALL order types on DEMO account[/]",
        border_style="magenta"
    ))
    
    failures = 0
    TEST_SYMBOL = "SOLUSDT"  # Use SOL for lower USD amounts
    USD_SIZE = 15.0  # Small size for testing
    
    # ============================================================
    # PHASE 1: SETUP
    # ============================================================
    console.print(f"\n[bold magenta]{'='*60}[/]")
    console.print(f"[bold magenta]PHASE 1: SETUP[/]")
    console.print(f"[bold magenta]{'='*60}[/]")
    
    console.print(f"\n[bold cyan]1.1: Get Current Price[/]")
    result = get_price_tool(TEST_SYMBOL)
    current_price = 0
    if result.success and result.data:
        current_price = float(result.data.get("price", 0))
        console.print(f"  [green]OK[/] {TEST_SYMBOL} price: ${current_price:,.4f}")
    else:
        console.print(f"  [red]FAIL[/] Could not get price: {result.error}")
        failures += 1
        return failures  # Can't continue without price
    
    console.print(f"\n[bold cyan]1.2: Set Leverage[/]")
    result = set_leverage_tool(TEST_SYMBOL, 2)
    if result.success:
        console.print(f"  [green]OK[/] {result.message}")
    else:
        console.print(f"  [yellow]![/] {result.error} (may already be set)")
    
    console.print(f"\n[bold cyan]1.3: Cancel Any Existing Orders[/]")
    result = cancel_all_orders_tool(symbol=TEST_SYMBOL)
    if result.success:
        console.print(f"  [green]OK[/] {result.message}")
    else:
        console.print(f"  [yellow]![/] {result.error}")
    
    console.print(f"\n[bold cyan]1.4: Check Existing Positions[/]")
    result = list_open_positions_tool(symbol=TEST_SYMBOL)
    has_position = False
    if result.success:
        positions = result.data if result.data else []
        if positions:
            has_position = True
            console.print(f"  [yellow]![/] Found existing position - will test TP/SL on it")
        else:
            console.print(f"  [green]OK[/] No existing position")
    
    # ============================================================
    # PHASE 2: LIMIT ORDERS
    # ============================================================
    console.print(f"\n[bold magenta]{'='*60}[/]")
    console.print(f"[bold magenta]PHASE 2: LIMIT ORDERS[/]")
    console.print(f"[bold magenta]{'='*60}[/]")
    
    limit_buy_price = round(current_price * 0.92, 2)  # 8% below
    limit_sell_price = round(current_price * 1.08, 2)  # 8% above
    
    console.print(f"\n[bold cyan]2.1: Limit Buy Order[/]")
    console.print(f"  [dim]Price: ${limit_buy_price} (8% below market)[/]")
    result = limit_buy_tool(TEST_SYMBOL, USD_SIZE, limit_buy_price)
    limit_buy_order_id = None
    if result.success:
        limit_buy_order_id = result.data.get("order_id") if result.data else None
        console.print(f"  [green]OK[/] {result.message}")
    else:
        console.print(f"  [red]FAIL[/] {result.error}")
        failures += 1
    
    console.print(f"\n[bold cyan]2.2: Limit Sell Order[/]")
    console.print(f"  [dim]Price: ${limit_sell_price} (8% above market)[/]")
    result = limit_sell_tool(TEST_SYMBOL, USD_SIZE, limit_sell_price)
    limit_sell_order_id = None
    if result.success:
        limit_sell_order_id = result.data.get("order_id") if result.data else None
        console.print(f"  [green]OK[/] {result.message}")
    else:
        console.print(f"  [red]FAIL[/] {result.error}")
        failures += 1
    
    console.print(f"\n[bold cyan]2.3: Verify Open Orders[/]")
    result = get_open_orders_tool(symbol=TEST_SYMBOL)
    if result.success:
        count = len(result.data) if result.data else 0
        console.print(f"  [green]OK[/] Found {count} open orders")
    else:
        console.print(f"  [red]FAIL[/] {result.error}")
        failures += 1
    
    # Cancel limit orders
    console.print(f"\n[bold cyan]2.4: Cancel Limit Orders[/]")
    if limit_buy_order_id:
        result = cancel_order_tool(TEST_SYMBOL, order_id=limit_buy_order_id)
        if result.success:
            console.print(f"  [green]OK[/] Cancelled limit buy order")
        else:
            console.print(f"  [yellow]![/] {result.error}")
    
    if limit_sell_order_id:
        result = cancel_order_tool(TEST_SYMBOL, order_id=limit_sell_order_id)
        if result.success:
            console.print(f"  [green]OK[/] Cancelled limit sell order")
        else:
            console.print(f"  [yellow]![/] {result.error}")
    
    # ============================================================
    # PHASE 3: STOP ORDERS
    # ============================================================
    console.print(f"\n[bold magenta]{'='*60}[/]")
    console.print(f"[bold magenta]PHASE 3: STOP ORDERS[/]")
    console.print(f"[bold magenta]{'='*60}[/]")
    
    stop_buy_trigger = round(current_price * 1.05, 2)  # 5% above
    stop_sell_trigger = round(current_price * 0.95, 2)  # 5% below
    
    console.print(f"\n[bold cyan]3.1: Stop Market Buy[/]")
    console.print(f"  [dim]Trigger: ${stop_buy_trigger} (5% above market)[/]")
    result = stop_market_buy_tool(TEST_SYMBOL, USD_SIZE, stop_buy_trigger)
    stop_buy_order_id = None
    if result.success:
        stop_buy_order_id = result.data.get("order_id") if result.data else None
        console.print(f"  [green]OK[/] {result.message}")
    else:
        console.print(f"  [red]FAIL[/] {result.error}")
        failures += 1
    
    console.print(f"\n[bold cyan]3.2: Stop Market Sell[/]")
    console.print(f"  [dim]Trigger: ${stop_sell_trigger} (5% below market)[/]")
    result = stop_market_sell_tool(TEST_SYMBOL, USD_SIZE, stop_sell_trigger)
    stop_sell_order_id = None
    if result.success:
        stop_sell_order_id = result.data.get("order_id") if result.data else None
        console.print(f"  [green]OK[/] {result.message}")
    else:
        console.print(f"  [red]FAIL[/] {result.error}")
        failures += 1
    
    # Stop limit orders
    stop_limit_buy_price = round(stop_buy_trigger * 1.01, 2)
    stop_limit_sell_price = round(stop_sell_trigger * 0.99, 2)
    
    console.print(f"\n[bold cyan]3.3: Stop Limit Buy[/]")
    console.print(f"  [dim]Trigger: ${stop_buy_trigger}, Limit: ${stop_limit_buy_price}[/]")
    result = stop_limit_buy_tool(TEST_SYMBOL, USD_SIZE, stop_buy_trigger, stop_limit_buy_price)
    stop_limit_buy_id = None
    if result.success:
        stop_limit_buy_id = result.data.get("order_id") if result.data else None
        console.print(f"  [green]OK[/] {result.message}")
    else:
        console.print(f"  [red]FAIL[/] {result.error}")
        failures += 1
    
    console.print(f"\n[bold cyan]3.4: Stop Limit Sell[/]")
    console.print(f"  [dim]Trigger: ${stop_sell_trigger}, Limit: ${stop_limit_sell_price}[/]")
    result = stop_limit_sell_tool(TEST_SYMBOL, USD_SIZE, stop_sell_trigger, stop_limit_sell_price)
    stop_limit_sell_id = None
    if result.success:
        stop_limit_sell_id = result.data.get("order_id") if result.data else None
        console.print(f"  [green]OK[/] {result.message}")
    else:
        console.print(f"  [red]FAIL[/] {result.error}")
        failures += 1
    
    console.print(f"\n[bold cyan]3.5: Cancel All Stop Orders[/]")
    result = cancel_all_orders_tool(symbol=TEST_SYMBOL)
    if result.success:
        console.print(f"  [green]OK[/] {result.message}")
    else:
        console.print(f"  [yellow]![/] {result.error}")
    
    # ============================================================
    # PHASE 4: MARKET ORDERS (Creates Position)
    # ============================================================
    console.print(f"\n[bold magenta]{'='*60}[/]")
    console.print(f"[bold magenta]PHASE 4: MARKET ORDERS (Creates Position)[/]")
    console.print(f"[bold magenta]{'='*60}[/]")
    
    console.print(f"\n[bold cyan]4.1: Market Buy (Open Long)[/]")
    result = market_buy_tool(TEST_SYMBOL, USD_SIZE)
    if result.success:
        console.print(f"  [green]OK[/] {result.message}")
        has_position = True
    else:
        console.print(f"  [red]FAIL[/] {result.error}")
        failures += 1
    
    # ============================================================
    # PHASE 5: POSITION TP/SL MANAGEMENT
    # ============================================================
    console.print(f"\n[bold magenta]{'='*60}[/]")
    console.print(f"[bold magenta]PHASE 5: POSITION TP/SL MANAGEMENT[/]")
    console.print(f"[bold magenta]{'='*60}[/]")
    
    if has_position:
        # Refresh price
        result = get_price_tool(TEST_SYMBOL)
        if result.success and result.data:
            current_price = float(result.data.get("price", current_price))
        
        tp_price = round(current_price * 1.10, 2)  # 10% above
        sl_price = round(current_price * 0.90, 2)  # 10% below
        
        console.print(f"\n[bold cyan]5.1: Set Take Profit[/]")
        console.print(f"  [dim]TP: ${tp_price} (10% above entry)[/]")
        result = set_take_profit_tool(TEST_SYMBOL, tp_price)
        if result.success:
            console.print(f"  [green]OK[/] {result.message}")
        else:
            console.print(f"  [red]FAIL[/] {result.error}")
            failures += 1
        
        console.print(f"\n[bold cyan]5.2: Set Stop Loss[/]")
        console.print(f"  [dim]SL: ${sl_price} (10% below entry)[/]")
        result = set_stop_loss_tool(TEST_SYMBOL, sl_price)
        if result.success:
            console.print(f"  [green]OK[/] {result.message}")
        else:
            console.print(f"  [red]FAIL[/] {result.error}")
            failures += 1
        
        console.print(f"\n[bold cyan]5.3: Set Trailing Stop (5%)[/]")
        result = set_trailing_stop_by_percent_tool(TEST_SYMBOL, 5.0)
        if result.success:
            console.print(f"  [green]OK[/] {result.message}")
        else:
            console.print(f"  [yellow]![/] {result.error} (may not support trailing)")
        
        console.print(f"\n[bold cyan]5.4: Remove Take Profit[/]")
        result = remove_take_profit_tool(TEST_SYMBOL)
        if result.success:
            console.print(f"  [green]OK[/] {result.message}")
        else:
            console.print(f"  [yellow]![/] {result.error}")
        
        console.print(f"\n[bold cyan]5.5: Remove Stop Loss[/]")
        result = remove_stop_loss_tool(TEST_SYMBOL)
        if result.success:
            console.print(f"  [green]OK[/] {result.message}")
        else:
            console.print(f"  [yellow]![/] {result.error}")
        
        console.print(f"\n[bold cyan]5.6: Get Position Detail[/]")
        result = get_position_detail_tool(TEST_SYMBOL)
        if result.success:
            console.print(f"  [green]OK[/] {result.message}")
        else:
            console.print(f"  [yellow]![/] {result.error}")
    else:
        console.print(f"  [yellow]![/] Skipping TP/SL tests - no position created")
    
    # ============================================================
    # PHASE 6: CLOSE POSITION
    # ============================================================
    console.print(f"\n[bold magenta]{'='*60}[/]")
    console.print(f"[bold magenta]PHASE 6: CLOSE POSITION[/]")
    console.print(f"[bold magenta]{'='*60}[/]")
    
    if has_position:
        console.print(f"\n[bold cyan]6.1: Close Position (Market Sell)[/]")
        result = market_sell_tool(TEST_SYMBOL, USD_SIZE)
        if result.success:
            console.print(f"  [green]OK[/] {result.message}")
        else:
            console.print(f"  [yellow]![/] {result.error}")
            # Try close_position_tool as fallback
            result = close_position_tool(TEST_SYMBOL)
            if result.success:
                console.print(f"  [green]OK[/] Position closed via close_position_tool")
            else:
                console.print(f"  [yellow]![/] {result.error}")
    
    console.print(f"\n[bold cyan]6.2: Verify No Open Position[/]")
    result = list_open_positions_tool(symbol=TEST_SYMBOL)
    if result.success:
        positions = result.data if result.data else []
        if not positions:
            console.print(f"  [green]OK[/] No open positions")
        else:
            console.print(f"  [yellow]![/] Still have {len(positions)} position(s)")
    
    # ============================================================
    # PHASE 7: MARKET ORDER WITH TP/SL (Full Cycle)
    # ============================================================
    console.print(f"\n[bold magenta]{'='*60}[/]")
    console.print(f"[bold magenta]PHASE 7: MARKET ORDER WITH TP/SL[/]")
    console.print(f"[bold magenta]{'='*60}[/]")
    
    result = get_price_tool(TEST_SYMBOL)
    if result.success and result.data:
        current_price = float(result.data.get("price", current_price))
    
    tp_price = round(current_price * 1.15, 2)
    sl_price = round(current_price * 0.85, 2)
    
    console.print(f"\n[bold cyan]7.1: Market Buy with TP/SL[/]")
    console.print(f"  [dim]TP: ${tp_price}, SL: ${sl_price}[/]")
    result = market_buy_with_tpsl_tool(TEST_SYMBOL, USD_SIZE, tp_price, sl_price)
    if result.success:
        console.print(f"  [green]OK[/] {result.message}")
    else:
        console.print(f"  [red]FAIL[/] {result.error}")
        failures += 1
    
    console.print(f"\n[bold cyan]7.2: Close Position[/]")
    result = close_position_tool(TEST_SYMBOL)
    if result.success:
        console.print(f"  [green]OK[/] {result.message}")
    else:
        console.print(f"  [yellow]![/] {result.error}")
    
    # ============================================================
    # PHASE 8: FINAL CLEANUP
    # ============================================================
    console.print(f"\n[bold magenta]{'='*60}[/]")
    console.print(f"[bold magenta]PHASE 8: FINAL CLEANUP[/]")
    console.print(f"[bold magenta]{'='*60}[/]")
    
    console.print(f"\n[bold cyan]8.1: Cancel All Remaining Orders[/]")
    result = cancel_all_orders_tool(symbol=TEST_SYMBOL)
    console.print(f"  [green]OK[/] {result.message}" if result.success else f"  [yellow]![/] {result.error}")
    
    console.print(f"\n[bold cyan]8.2: Panic Close All (Safety Check)[/]")
    result = panic_close_all_tool(reason="Order smoke test cleanup")
    console.print(f"  [green]OK[/] {result.message}" if result.success else f"  [yellow]![/] {result.error}")
    
    # ============================================================
    # SUMMARY
    # ============================================================
    console.print(f"\n[bold magenta]{'='*60}[/]")
    console.print(f"[bold magenta]COMPREHENSIVE ORDER SMOKE TEST COMPLETE[/]")
    console.print(f"[bold magenta]{'='*60}[/]")
    
    console.print(f"\n[bold]Test Summary:[/]")
    console.print(f"  Symbol tested: {TEST_SYMBOL}")
    console.print(f"  USD size: ${USD_SIZE}")
    console.print(f"  Order types tested: Limit, Stop Market, Stop Limit, Market, TP/SL, Trailing")
    console.print(f"  Total failures: {failures}")
    
    if failures == 0:
        console.print(f"\n[bold green]OK ALL ORDER TESTS PASSED[/]")
    else:
        console.print(f"\n[bold red]FAIL {failures} ORDER TEST(S) FAILED[/]")
    
    return failures


def run_live_check_smoke() -> int:
    """
    Limited LIVE connectivity and order test.
    
    ⚠️  WARNING: This test uses LIVE API credentials and may place REAL orders.
    
    Tests:
    1. LIVE API connectivity (public)
    2. LIVE API authentication (private)
    3. Account balance check
    4. Limited order test (place and cancel far-from-market limit order)
    
    The order test will likely fail with "insufficient funds" if the account
    has low balance - this is expected and proves the API works.
    
    Returns:
        Number of failures (0 = success, expected failures from low balance are OK)
    """
    from src.config.config import get_config
    
    console.print(Panel(
        "[bold red]⚠️  LIVE CHECK SMOKE TEST ⚠️[/]\n"
        "[red]Testing LIVE API connectivity and authentication[/]\n"
        "[dim]This uses your LIVE account credentials[/]",
        border_style="red"
    ))
    
    failures = 0
    config = get_config()
    
    # Get current API environment
    env_summary = config.bybit.get_api_environment_summary()
    trading = env_summary["trading"]
    
    # ============================================================
    # PHASE 1: VERIFY LIVE MODE
    # ============================================================
    console.print(f"\n[bold red]{'='*60}[/]")
    console.print(f"[bold red]PHASE 1: VERIFY LIVE MODE[/]")
    console.print(f"[bold red]{'='*60}[/]")
    
    console.print(f"\n[bold cyan]1.1: Check API Environment[/]")
    result = get_api_environment_tool()
    if result.success:
        console.print(f"  [green]OK[/] {result.message}")
        data = result.data or {}
        active = data.get("active_trading", {})
        console.print(f"      Active Mode: {active.get('mode', 'N/A')}")
        console.print(f"      Base URL: {active.get('base_url', 'N/A')}")
        
        # Check if we're actually in LIVE mode
        if active.get("is_demo", True):
            console.print(f"\n  [yellow]⚠️  WARNING: Running in DEMO mode, not LIVE[/]")
            console.print(f"  [yellow]Set BYBIT_USE_DEMO=false to test LIVE[/]")
    else:
        console.print(f"  [red]FAIL[/] {result.error}")
        failures += 1
    
    # ============================================================
    # PHASE 2: LIVE CONNECTIVITY
    # ============================================================
    console.print(f"\n[bold red]{'='*60}[/]")
    console.print(f"[bold red]PHASE 2: LIVE CONNECTIVITY[/]")
    console.print(f"[bold red]{'='*60}[/]")
    
    console.print(f"\n[bold cyan]2.1: Test Connection[/]")
    result = test_connection_tool()
    if result.success:
        console.print(f"  [green]OK[/] {result.message}")
        data = result.data or {}
        console.print(f"      Environment: {data.get('environment', 'N/A')}")
        console.print(f"      Public API: {'OK' if data.get('public_ok') else 'FAIL'}")
        console.print(f"      Private API: {'OK' if data.get('private_ok') else 'FAIL'}")
        if data.get("btc_price"):
            console.print(f"      BTC Price: ${float(data['btc_price']):,.2f}")
    else:
        console.print(f"  [red]FAIL[/] {result.error}")
        failures += 1
    
    console.print(f"\n[bold cyan]2.2: Server Time Sync[/]")
    result = get_server_time_offset_tool()
    if result.success:
        console.print(f"  [green]OK[/] {result.message}")
    else:
        console.print(f"  [red]FAIL[/] {result.error}")
        failures += 1
    
    # ============================================================
    # PHASE 3: ACCOUNT CHECK
    # ============================================================
    console.print(f"\n[bold red]{'='*60}[/]")
    console.print(f"[bold red]PHASE 3: ACCOUNT CHECK[/]")
    console.print(f"[bold red]{'='*60}[/]")
    
    console.print(f"\n[bold cyan]3.1: Account Balance[/]")
    result = get_account_balance_tool()
    if result.success:
        console.print(f"  [green]OK[/] {result.message}")
        data = result.data or {}
        if "total" in data:
            console.print(f"      Total Equity: ${float(data.get('total', 0)):,.2f}")
            console.print(f"      Available: ${float(data.get('available', 0)):,.2f}")
    else:
        console.print(f"  [red]FAIL[/] {result.error}")
        failures += 1
    
    console.print(f"\n[bold cyan]3.2: Open Positions[/]")
    result = list_open_positions_tool()
    if result.success:
        positions = result.data if result.data else []
        console.print(f"  [green]OK[/] Found {len(positions)} open position(s)")
    else:
        console.print(f"  [yellow]![/] {result.error}")
    
    # ============================================================
    # PHASE 4: LIMITED ORDER TEST
    # ============================================================
    console.print(f"\n[bold red]{'='*60}[/]")
    console.print(f"[bold red]PHASE 4: LIMITED ORDER TEST[/]")
    console.print(f"[bold red]{'='*60}[/]")
    
    # Use SOLUSDT (cheaper) so $20 order size works, or use larger amount for BTC
    TEST_SYMBOL = "SOLUSDT"
    ORDER_SIZE_USD = 20.0
    
    console.print(f"\n[bold cyan]4.1: Get Current Price[/]")
    result = get_price_tool(TEST_SYMBOL)
    current_price = 0
    if result.success and result.data:
        current_price = float(result.data.get("price", 0))
        console.print(f"  [green]OK[/] {TEST_SYMBOL} price: ${current_price:,.2f}")
    else:
        console.print(f"  [red]FAIL[/] {result.error}")
        failures += 1
    
    if current_price > 0:
        # Place a limit order far from market (should not fill)
        limit_price = round(current_price * 0.80, 2)  # 20% below market
        
        console.print(f"\n[bold cyan]4.2: Place Limit Order (Far From Market)[/]")
        console.print(f"  [dim]Price: ${limit_price:,.2f} (20% below market - won't fill)[/]")
        console.print(f"  [dim]Size: ${ORDER_SIZE_USD} USD[/]")
        
        result = limit_buy_tool(TEST_SYMBOL, ORDER_SIZE_USD, limit_price)
        order_id = None
        if result.success:
            order_id = result.data.get("order_id") if result.data else None
            console.print(f"  [green]OK[/] {result.message}")
            console.print(f"      Order ID: {order_id}")
        else:
            # Expected: "insufficient funds" error
            if "110007" in str(result.error) or "not enough" in str(result.error).lower():
                console.print(f"  [yellow]![/] {result.error}")
                console.print(f"  [dim]This is expected with low balance - API works correctly[/]")
            else:
                console.print(f"  [red]FAIL[/] {result.error}")
                failures += 1
        
        if order_id:
            console.print(f"\n[bold cyan]4.3: Cancel Order[/]")
            result = cancel_order_tool(TEST_SYMBOL, order_id=order_id)
            if result.success:
                console.print(f"  [green]OK[/] Order cancelled")
            else:
                console.print(f"  [yellow]![/] {result.error}")
    
    # ============================================================
    # SUMMARY
    # ============================================================
    console.print(f"\n[bold red]{'='*60}[/]")
    console.print(f"[bold red]LIVE CHECK SMOKE TEST COMPLETE[/]")
    console.print(f"[bold red]{'='*60}[/]")
    
    console.print(f"\n[bold]Test Summary:[/]")
    console.print(f"  API Mode: {trading['mode']}")
    console.print(f"  Base URL: {trading['base_url']}")
    console.print(f"  Hard failures: {failures}")
    
    if failures == 0:
        console.print(f"\n[bold green]OK LIVE API CONNECTIVITY VERIFIED[/]")
    else:
        console.print(f"\n[bold red]FAIL {failures} CONNECTIVITY TEST(S) FAILED[/]")
    
    return failures

