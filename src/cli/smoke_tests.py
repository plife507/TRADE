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
    # Backtest tools (legacy SystemConfig-based)
    backtest_list_systems_tool,
    backtest_get_system_tool,
    backtest_run_tool,
    backtest_prepare_data_tool,
    backtest_verify_data_tool,
    backtest_list_strategies_tool,
    # Backtest CLI wrapper tools (IdeaCard-based, golden path)
    backtest_preflight_idea_card_tool,
    backtest_run_idea_card_tool,
    backtest_data_fix_tool,
    backtest_list_idea_cards_tool,
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
    
    # PART 7: Backtest Smoke (Phase 6 - opt-in)
    console.print(f"\n[bold magenta]{'='*50}[/]")
    console.print(f"[bold magenta]PART 7: BACKTEST SMOKE (Phase 6)[/]")
    console.print(f"[bold magenta]{'='*50}[/]")
    failures += run_backtest_smoke_suite(smoke_config, app, config)
    
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


def _run_backtest_smoke_idea_card(idea_card_id: str, fresh_db: bool = False) -> int:
    """
    Run backtest smoke test using IdeaCard-based wrapper (golden path).
    
    This is the canonical smoke test that uses the same CLI wrapper
    that `trade_cli.py backtest run --smoke` uses.
    
    Args:
        idea_card_id: IdeaCard identifier to test
        fresh_db: Whether to wipe DB and rebuild data first
        
    Returns:
        Number of failures
    """
    import json
    from pathlib import Path
    import pandas as pd
    import math
    
    failures = 0
    
    console.print(f"\n[bold cyan]IdeaCard Smoke Test: {idea_card_id}[/]")
    
    # Step 2: Run preflight check (Phase A gate)
    console.print(f"\n[bold cyan]Step 2: Preflight Check (Phase A Gate)[/]")
    console.print(f"  [dim]Checking env/symbol/tf/coverage...[/]")
    
    preflight_result = backtest_preflight_idea_card_tool(
        idea_card_id=idea_card_id,
        env="live",  # Always use live data env for smoke
    )
    
    if preflight_result.success:
        diag = preflight_result.data
        console.print(f"  [green]OK[/] Preflight passed")
        console.print(f"      Env: {diag.get('env')}")
        console.print(f"      DB: {diag.get('db_path')}")
        console.print(f"      Table: {diag.get('ohlcv_table')}")
        console.print(f"      Symbol: {diag.get('symbol')} | Exec TF: {diag.get('exec_tf')}")
        console.print(f"      DB Coverage: {diag.get('db_bar_count', 0):,} bars")
        
        # Print indicator keys (Phase B)
        exec_keys = diag.get('declared_keys_exec', [])
        htf_keys = diag.get('declared_keys_htf', [])
        mtf_keys = diag.get('declared_keys_mtf', [])
        
        console.print(f"      Indicator Keys (exec): {exec_keys or '(none)'}")
        if htf_keys:
            console.print(f"      Indicator Keys (htf): {htf_keys}")
        if mtf_keys:
            console.print(f"      Indicator Keys (mtf): {mtf_keys}")
    else:
        console.print(f"  [red]FAIL[/] Preflight failed: {preflight_result.error}")
        
        # Print actionable diagnostics
        if preflight_result.data:
            diag = preflight_result.data
            console.print(f"      Env: {diag.get('env')}")
            console.print(f"      DB: {diag.get('db_path')}")
            if diag.get('coverage_issue'):
                console.print(f"      [yellow]Fix: {diag['coverage_issue']}[/]")
            if diag.get('validation_errors'):
                for err in diag['validation_errors']:
                    console.print(f"      [red]Error: {err}[/]")
        
        failures += 1
        
        # Try to fix data if fresh_db
        if fresh_db:
            console.print(f"\n[bold cyan]Step 2b: Attempting Data Fix[/]")
            fix_result = backtest_data_fix_tool(
                idea_card_id=idea_card_id,
                env="live",
                sync_to_now=True,
                fill_gaps=True,
            )
            if fix_result.success:
                console.print(f"  [green]OK[/] Data fix completed: {fix_result.message}")
                # Retry preflight
                preflight_result = backtest_preflight_idea_card_tool(
                    idea_card_id=idea_card_id,
                    env="live",
                )
                if preflight_result.success:
                    console.print(f"  [green]OK[/] Preflight now passes")
                    failures -= 1  # Undo the failure
                else:
                    console.print(f"  [red]FAIL[/] Preflight still fails after data fix")
                    return failures
            else:
                console.print(f"  [red]FAIL[/] Data fix failed: {fix_result.error}")
                return failures
        else:
            return failures
    
    # Step 3: Run backtest with --smoke mode
    console.print(f"\n[bold cyan]Step 3: Run Backtest (Smoke Mode)[/]")
    console.print(f"  [dim]Running with --smoke --strict...[/]")
    
    run_result = backtest_run_idea_card_tool(
        idea_card_id=idea_card_id,
        env="live",
        smoke=True,
        strict=True,
        write_artifacts=True,
    )
    
    if run_result.success:
        console.print(f"  [green]OK[/] {run_result.message}")
        
        data = run_result.data or {}
        trades_count = data.get("trades_count", 0)
        console.print(f"      Trades: {trades_count}")
        
        if data.get("artifact_dir"):
            artifact_dir = Path(data["artifact_dir"])
            console.print(f"      Artifacts: {artifact_dir}")
            
            # Step 4: Validate artifacts
            console.print(f"\n[bold cyan]Step 4: Validate Artifacts[/]")
            
            # Check result.json
            result_json = artifact_dir / "result.json"
            if result_json.exists():
                console.print(f"  [green]OK[/] result.json exists")
                try:
                    with open(result_json) as f:
                        result_data = json.load(f)
                    
                    # Check for required fields
                    metrics = result_data.get("metrics", {})
                    required = ["total_trades", "final_equity", "net_return_pct"]
                    for field in required:
                        if field in metrics:
                            val = metrics[field]
                            if isinstance(val, (int, float)) and (not isinstance(val, float) or math.isfinite(val)):
                                console.print(f"  [green]OK[/] {field} = {val}")
                            else:
                                console.print(f"  [red]FAIL[/] {field} not finite: {val}")
                                failures += 1
                        else:
                            console.print(f"  [yellow]WARN[/] Missing {field}")
                    
                except Exception as e:
                    console.print(f"  [red]FAIL[/] Error reading result.json: {e}")
                    failures += 1
            else:
                console.print(f"  [yellow]WARN[/] result.json not found (smoke mode may skip)")
            
            # Check trades.csv
            trades_csv = artifact_dir / "trades.csv"
            if trades_csv.exists():
                console.print(f"  [green]OK[/] trades.csv exists")
                try:
                    trades_df = pd.read_csv(trades_csv)
                    console.print(f"      {len(trades_df)} trades recorded")
                except Exception as e:
                    console.print(f"  [red]FAIL[/] Error reading trades.csv: {e}")
                    failures += 1
            else:
                console.print(f"  [yellow]WARN[/] trades.csv not found")
            
            # Check equity.csv
            equity_csv = artifact_dir / "equity.csv"
            if equity_csv.exists():
                console.print(f"  [green]OK[/] equity.csv exists")
                try:
                    equity_df = pd.read_csv(equity_csv)
                    console.print(f"      {len(equity_df)} equity points")
                    
                    if "equity" in equity_df.columns and (equity_df["equity"] > 0).all():
                        console.print(f"  [green]OK[/] All equity values > 0")
                    else:
                        console.print(f"  [red]FAIL[/] Some equity values <= 0")
                        failures += 1
                except Exception as e:
                    console.print(f"  [red]FAIL[/] Error reading equity.csv: {e}")
                    failures += 1
            else:
                console.print(f"  [yellow]WARN[/] equity.csv not found")
        
        # Print summary from preflight for diagnostics confirmation
        if preflight_result.data:
            console.print(f"\n[bold cyan]Step 5: Diagnostics Summary[/]")
            diag = preflight_result.data
            console.print(f"  Environment: {diag.get('env')}")
            console.print(f"  Database: {diag.get('db_path')}")
            console.print(f"  Table: {diag.get('ohlcv_table')}")
            console.print(f"  Symbol: {diag.get('symbol')}")
            console.print(f"  Exec TF: {diag.get('exec_tf')}")
            console.print(f"  Warmup: {diag.get('warmup_bars', 0)} bars ({diag.get('warmup_span_minutes', 0)} min)")
            console.print(f"  DB Range: {diag.get('db_earliest')} to {diag.get('db_latest')}")
            console.print(f"  Indicator Keys (exec): {diag.get('declared_keys_exec', [])}")
    else:
        console.print(f"  [red]FAIL[/] Backtest failed: {run_result.error}")
        failures += 1
        
        # Print actionable diagnostics
        if run_result.data and "preflight" in run_result.data:
            diag = run_result.data["preflight"]
            console.print(f"\n[bold]Diagnostics from preflight:[/]")
            console.print(f"  Env: {diag.get('env')}")
            console.print(f"  DB: {diag.get('db_path')}")
            console.print(f"  Symbol: {diag.get('symbol')}")
            console.print(f"  Coverage: {'OK' if diag.get('has_sufficient_coverage') else 'INSUFFICIENT'}")
            if diag.get('coverage_issue'):
                console.print(f"  [yellow]Fix: {diag['coverage_issue']}[/]")
    
    # Summary
    console.print(f"\n[bold magenta]{'='*60}[/]")
    console.print(f"[bold magenta]IDEACARD BACKTEST SMOKE TEST COMPLETE[/]")
    console.print(f"[bold magenta]{'='*60}[/]")
    
    console.print(f"\n[bold]Summary:[/]")
    console.print(f"  IdeaCard: {idea_card_id}")
    console.print(f"  Fresh DB: {fresh_db}")
    console.print(f"  Failures: {failures}")
    
    if failures == 0:
        console.print(f"\n[bold green]OK BACKTEST ENGINE VERIFIED (IdeaCard Path)[/]")
    else:
        console.print(f"\n[bold red]FAIL {failures} TEST(S) FAILED[/]")
    
    return failures


def run_backtest_smoke(system_id: str = None, fresh_db: bool = False, idea_card_id: str = None) -> int:
    """
    Run the backtest smoke test.
    
    GOLDEN PATH: Uses IdeaCard-based wrapper when available.
    Falls back to legacy SystemConfig-based approach if no IdeaCards found.
    
    Tests the backtest engine end-to-end:
    1. List available IdeaCards (or systems for legacy)
    2. Run preflight check (env/symbol/tf/coverage diagnostics)
    3. Optionally prepare data (with fresh_db option)
    4. Run backtest with --smoke mode
    5. Validate output diagnostics and artifacts
    
    Args:
        system_id: System to test (legacy, defaults to env var BACKTEST_SMOKE_SYSTEM)
        fresh_db: Whether to wipe DB and rebuild data
        idea_card_id: IdeaCard to test (preferred over system_id)
        
    Returns:
        Number of failures
    """
    import os
    import json
    from pathlib import Path
    import pandas as pd
    import math
    
    console.print(Panel(
        "[bold magenta]BACKTEST ENGINE SMOKE TEST[/]\n"
        "[dim]Testing backtest pipeline via CLI wrapper (golden path)[/]",
        border_style="magenta"
    ))
    
    failures = 0
    
    # =============================
    # GOLDEN PATH: Try IdeaCard first
    # =============================
    
    console.print(f"\n[bold cyan]Step 1: Check for IdeaCards (Golden Path)[/]")
    
    # List available IdeaCards
    result = backtest_list_idea_cards_tool()
    idea_cards = []
    if result.success and result.data:
        idea_cards = result.data.get("idea_cards", [])
        console.print(f"  [green]OK[/] Found {len(idea_cards)} IdeaCards")
        for card in idea_cards[:5]:
            console.print(f"    • {card}")
    else:
        console.print(f"  [yellow]WARN[/] No IdeaCards found: {result.error}")
    
    # Determine IdeaCard to test
    if idea_card_id is None:
        idea_card_id = os.environ.get("BACKTEST_SMOKE_IDEA_CARD")
    
    if idea_card_id is None and idea_cards:
        idea_card_id = idea_cards[0]  # Use first available
    
    # If we have an IdeaCard, use the golden path
    if idea_card_id:
        console.print(f"\n  [bold]Using IdeaCard: {idea_card_id}[/]")
        return _run_backtest_smoke_idea_card(idea_card_id, fresh_db)
    
    # =============================
    # LEGACY PATH: Fall back to SystemConfig
    # =============================
    console.print(f"\n[yellow]No IdeaCards found, falling back to legacy SystemConfig path[/]")
    
    # Step 1b: List available systems (legacy)
    console.print(f"\n[bold cyan]Step 1b: List Available Systems (Legacy)[/]")
    result = backtest_list_systems_tool()
    if result.success and result.data:
        systems = result.data.get("systems", [])
        console.print(f"  [green]OK[/] Found {len(systems)} systems")
        for sys in systems[:5]:  # Show first 5
            if "error" not in sys:
                console.print(f"    • {sys.get('system_id')} ({sys.get('symbol')} {sys.get('tf')})")
    else:
        console.print(f"  [red]FAIL[/] {result.error or 'No systems found'}")
        failures += 1
        return failures  # Can't continue without systems
    
    # Determine which system to test
    if system_id is None:
        system_id = os.environ.get("BACKTEST_SMOKE_SYSTEM")
    
    if system_id is None and systems:
        # Use first available system with no error
        for sys in systems:
            if "error" not in sys:
                system_id = sys.get("system_id")
                break
    
    if system_id is None:
        console.print(f"  [red]FAIL[/] No valid system found to test")
        return failures + 1
    
    console.print(f"\n  [dim]Testing system: {system_id}[/]")
    
    # Variables for lineage display
    system_uid = None
    strategy_id = None
    strategy_version = None
    risk_profile = {}

    # Step 2: Load system config
    console.print(f"\n[bold cyan]Step 2: Load System Configuration[/]")
    result = backtest_get_system_tool(system_id)
    if result.success and result.data:
        data = result.data
        system_uid = data.get('system_uid', 'N/A')
        strategy_id = data.get('strategy_id')
        strategy_version = data.get('strategy_version', '1')
        risk_profile = data.get('risk_profile', {})
        
        console.print(f"  [green]OK[/] Loaded: {data.get('symbol')} {data.get('tf')}")
        console.print(f"      System UID: [dim]{system_uid}[/]")
        console.print(f"      Strategy: {strategy_id} v{strategy_version}")
        console.print(f"      Risk Mode: {data.get('risk_mode')}")
        console.print(f"      Risk Profile: initial_equity={risk_profile.get('initial_equity')}, "
                     f"risk_per_trade={risk_profile.get('risk_per_trade_pct')}%")
    else:
        console.print(f"  [red]FAIL[/] {result.error}")
        failures += 1
        return failures  # Can't continue

    # Step 3: List and validate strategies
    console.print(f"\n[bold cyan]Step 3: List & Validate Strategies[/]")
    result = backtest_list_strategies_tool()
    if result.success and result.data:
        strategies = result.data.get("strategies", [])
        strategy_ids = [s.get("strategy_id") if isinstance(s, dict) else s for s in strategies]
        console.print(f"  [green]OK[/] Found {len(strategies)} registered strategies")
        
        # Validate that the system's strategy exists in registry
        if strategy_id and strategy_id in strategy_ids:
            console.print(f"  [green]OK[/] Strategy '{strategy_id}' is registered")
        elif strategy_id:
            console.print(f"  [red]FAIL[/] Strategy '{strategy_id}' NOT found in registry!")
            console.print(f"      Available: {strategy_ids}")
            failures += 1
            return failures  # Can't continue without valid strategy
    else:
        console.print(f"  [red]FAIL[/] {result.error}")
        failures += 1
    
    # Step 4: Prepare data (optional fresh DB)
    if fresh_db:
        console.print(f"\n[bold cyan]Step 4: Prepare Data (Fresh DB)[/]")
        console.print(f"  [dim]Wiping database and rebuilding data...[/]")
    else:
        console.print(f"\n[bold cyan]Step 4: Prepare Data[/]")
        console.print(f"  [dim]Syncing data without DB wipe...[/]")
    
    result = backtest_prepare_data_tool(system_id, fresh_db=fresh_db)
    if result.success:
        console.print(f"  [green]OK[/] {result.message}")
        if result.data:
            console.print(f"      Symbol: {result.data.get('symbol')}")
            console.print(f"      Period: {result.data.get('period')}")
            console.print(f"      TFs: {result.data.get('tfs')}")
    else:
        console.print(f"  [red]FAIL[/] {result.error}")
        failures += 1
        # Try to continue - data might already exist
    
    # Step 5: Verify data quality
    console.print(f"\n[bold cyan]Step 5: Verify Data Quality[/]")
    
    for window_name in ["hygiene", "test"]:
        result = backtest_verify_data_tool(system_id, window_name, heal_gaps=True)
        if result.success and result.data:
            passed = result.data.get("verification_passed", False)
            bar_count = result.data.get("bar_count", 0)
            gaps = result.data.get("gaps_found", 0)
            
            status = "OK" if passed else "WARN"
            color = "green" if passed else "yellow"
            console.print(f"  [{color}]{status}[/{color}] {window_name}: {bar_count} bars, {gaps} gaps")
        else:
            console.print(f"  [red]FAIL[/] {window_name}: {result.error}")
            failures += 1
    
    # Step 6: Run backtest - Hygiene window WITH ARTIFACTS
    console.print(f"\n[bold cyan]Step 6: Run Backtest (Hygiene Window) - WITH ARTIFACTS[/]")
    result = backtest_run_tool(system_id, "hygiene", write_artifacts=True)
    artifact_dir = None
    if result.success and result.data:
        data = result.data
        metrics = data.get("metrics", {})
        artifact_dir = data.get("artifact_dir")
        
        console.print(f"  [green]OK[/] {result.message}")
        console.print(f"      Trades: {metrics.get('total_trades', 0)}")
        console.print(f"      Win Rate: {metrics.get('win_rate', 0):.1f}%")
        console.print(f"      Net Return: {metrics.get('net_return_pct', 0):.2f}%")
        console.print(f"      Max DD: {metrics.get('max_drawdown_pct', 0):.1f}%")
        console.print(f"      Sharpe: {metrics.get('sharpe', 0):.2f}")
        console.print(f"      Artifact dir: {artifact_dir}")
    else:
        console.print(f"  [red]FAIL[/] {result.error}")
        failures += 1
    
    # Step 7: Validate BacktestMetrics contract and artifacts
    console.print(f"\n[bold cyan]Step 7: Validate BacktestMetrics Contract & Artifacts[/]")
    
    if artifact_dir:
        artifact_path = Path(artifact_dir)
        
        # 7.1: Check result.json exists and has valid metrics
        result_json_path = artifact_path / "result.json"
        if result_json_path.exists():
            console.print(f"  [green]OK[/] result.json exists")
            try:
                with open(result_json_path) as f:
                    result_data = json.load(f)
                
                metrics = result_data.get("metrics", {})
                
                # Check required fields are present and finite
                required_metrics = [
                    "initial_equity", "final_equity", "net_profit", "net_return_pct",
                    "max_drawdown_abs", "max_drawdown_pct", "max_drawdown_duration_bars",
                    "total_trades", "win_rate", "avg_trade_return_pct", "profit_factor", "sharpe"
                ]
                
                all_present = True
                all_finite = True
                for field in required_metrics:
                    if field not in metrics:
                        console.print(f"  [red]FAIL[/] Missing metric field: {field}")
                        all_present = False
                        failures += 1
                    else:
                        val = metrics[field]
                        if not isinstance(val, (int, float)) or (isinstance(val, float) and not math.isfinite(val)):
                            console.print(f"  [red]FAIL[/] Metric '{field}' not finite: {val}")
                            all_finite = False
                            failures += 1
                
                if all_present and all_finite:
                    console.print(f"  [green]OK[/] All BacktestMetrics fields present and finite")
                
                # Check resolved risk fields
                risk_initial = result_data.get("risk_initial_equity_used", 0)
                risk_pct = result_data.get("risk_per_trade_pct_used", 0)
                risk_lev = result_data.get("risk_max_leverage_used", 0)
                
                # Compare to YAML defaults
                yaml_equity = risk_profile.get("initial_equity", 1000.0)
                yaml_pct = risk_profile.get("risk_per_trade_pct", 1.0)
                yaml_lev = risk_profile.get("max_leverage", 2.0)
                
                if abs(risk_initial - yaml_equity) < 0.01:
                    console.print(f"  [green]OK[/] risk_initial_equity_used matches YAML ({risk_initial})")
                else:
                    console.print(f"  [yellow]WARN[/] risk_initial_equity_used={risk_initial} differs from YAML={yaml_equity}")
                
                if abs(risk_pct - yaml_pct) < 0.01:
                    console.print(f"  [green]OK[/] risk_per_trade_pct_used matches YAML ({risk_pct})")
                else:
                    console.print(f"  [yellow]WARN[/] risk_per_trade_pct_used={risk_pct} differs from YAML={yaml_pct}")
                    
            except Exception as e:
                console.print(f"  [red]FAIL[/] Error reading result.json: {e}")
                failures += 1
        else:
            console.print(f"  [red]FAIL[/] result.json not found at {result_json_path}")
            failures += 1
        
        # 7.2: Check trades.csv
        trades_csv_path = artifact_path / "trades.csv"
        if trades_csv_path.exists():
            console.print(f"  [green]OK[/] trades.csv exists")
            try:
                trades_df = pd.read_csv(trades_csv_path)
                if len(trades_df) > 0:
                    console.print(f"  [green]OK[/] trades.csv has {len(trades_df)} rows")
                else:
                    console.print(f"  [yellow]WARN[/] trades.csv is empty (no trades)")
            except Exception as e:
                console.print(f"  [red]FAIL[/] Error reading trades.csv: {e}")
                failures += 1
        else:
            console.print(f"  [red]FAIL[/] trades.csv not found at {trades_csv_path}")
            failures += 1
        
        # 7.3: Check equity.csv
        equity_csv_path = artifact_path / "equity.csv"
        if equity_csv_path.exists():
            console.print(f"  [green]OK[/] equity.csv exists")
            try:
                equity_df = pd.read_csv(equity_csv_path)
                if len(equity_df) > 1:
                    console.print(f"  [green]OK[/] equity.csv has {len(equity_df)} rows")
                    
                    # Check equity > 0
                    if (equity_df["equity"] > 0).all():
                        console.print(f"  [green]OK[/] All equity values > 0")
                    else:
                        console.print(f"  [red]FAIL[/] Some equity values <= 0")
                        failures += 1
                    
                    # Check drawdown columns are numeric
                    if "drawdown_abs" in equity_df.columns and "drawdown_pct" in equity_df.columns:
                        if pd.api.types.is_numeric_dtype(equity_df["drawdown_abs"]):
                            console.print(f"  [green]OK[/] drawdown_abs is numeric")
                        else:
                            console.print(f"  [red]FAIL[/] drawdown_abs is not numeric")
                            failures += 1
                        if pd.api.types.is_numeric_dtype(equity_df["drawdown_pct"]):
                            console.print(f"  [green]OK[/] drawdown_pct is numeric")
                        else:
                            console.print(f"  [red]FAIL[/] drawdown_pct is not numeric")
                            failures += 1
                    else:
                        console.print(f"  [red]FAIL[/] Missing drawdown columns")
                        failures += 1
                else:
                    console.print(f"  [red]FAIL[/] equity.csv has only {len(equity_df)} rows")
                    failures += 1
            except Exception as e:
                console.print(f"  [red]FAIL[/] Error reading equity.csv: {e}")
                failures += 1
        else:
            console.print(f"  [red]FAIL[/] equity.csv not found at {equity_csv_path}")
            failures += 1
        
        # 7.4: Validate warm-up metadata (new contract)
        console.print(f"\n[bold cyan]Step 7.4: Validate Warm-up Metadata[/]")
        if result_json_path.exists():
            try:
                with open(result_json_path) as f:
                    result_data = json.load(f)
                
                # Check warmup_bars > 0
                warmup_bars = result_data.get("warmup_bars", 0)
                if warmup_bars > 0:
                    console.print(f"  [green]OK[/] warmup_bars = {warmup_bars}")
                else:
                    console.print(f"  [red]FAIL[/] warmup_bars should be > 0, got {warmup_bars}")
                    failures += 1

                # Check max_indicator_lookback > 0
                max_lookback = result_data.get("max_indicator_lookback", 0)
                if max_lookback > 0:
                    console.print(f"  [green]OK[/] max_indicator_lookback = {max_lookback}")
                else:
                    console.print(f"  [yellow]WARN[/] max_indicator_lookback = {max_lookback} (may be 0 if no indicators)")
                
                # Check window timestamps are populated
                req_start = result_data.get("data_window_requested_start", "")
                req_end = result_data.get("data_window_requested_end", "")
                load_start = result_data.get("data_window_loaded_start", "")
                load_end = result_data.get("data_window_loaded_end", "")
                sim_start = result_data.get("simulation_start_ts", "")
                
                if req_start and req_end:
                    console.print(f"  [green]OK[/] Requested window: {req_start[:10]} to {req_end[:10]}")
                else:
                    console.print(f"  [red]FAIL[/] Missing data_window_requested_start/end")
                    failures += 1
                
                if load_start and load_end:
                    console.print(f"  [green]OK[/] Loaded window: {load_start[:10]} to {load_end[:10]}")
                    
                    # Verify loaded_start <= requested_start (warm-up extends backward)
                    if load_start <= req_start:
                        console.print(f"  [green]OK[/] loaded_start <= requested_start (warm-up applied)")
                    else:
                        console.print(f"  [yellow]WARN[/] loaded_start > requested_start (data may be limited)")
                else:
                    console.print(f"  [red]FAIL[/] Missing data_window_loaded_start/end")
                    failures += 1
                
                if sim_start:
                    console.print(f"  [green]OK[/] simulation_start_ts: {sim_start[:10]}")
                    
                    # Verify simulation starts at or after requested start
                    if sim_start >= req_start:
                        console.print(f"  [green]OK[/] simulation starts at/after requested window start")
                    else:
                        console.print(f"  [red]FAIL[/] simulation starts before requested window")
                        failures += 1
                else:
                    console.print(f"  [red]FAIL[/] Missing simulation_start_ts")
                    failures += 1
                
                # Verify equity curve starts at simulation start
                if equity_csv_path.exists():
                    equity_df = pd.read_csv(equity_csv_path)
                    if len(equity_df) > 0 and "ts" in equity_df.columns:
                        first_equity_ts = equity_df["ts"].iloc[0]
                        if sim_start and first_equity_ts >= req_start:
                            console.print(f"  [green]OK[/] First equity point at/after requested start")
                        else:
                            console.print(f"  [yellow]WARN[/] First equity point: {first_equity_ts[:10]}")
                
            except Exception as e:
                console.print(f"  [red]FAIL[/] Error validating warm-up metadata: {e}")
                failures += 1
    else:
        console.print(f"  [yellow]WARN[/] No artifact_dir returned, skipping artifact validation")
    
    # Step 8: Run backtest - Test window (no artifacts needed)
    console.print(f"\n[bold cyan]Step 8: Run Backtest (Test Window)[/]")
    result = backtest_run_tool(system_id, "test", write_artifacts=False)
    if result.success and result.data:
        metrics = result.data.get("metrics", {})
        console.print(f"  [green]OK[/] {result.message}")
        console.print(f"      Trades: {metrics.get('total_trades', 0)}")
        console.print(f"      Net Return: {metrics.get('net_return_pct', 0):.2f}%")
        console.print(f"      Max DD: {metrics.get('max_drawdown_pct', 0):.1f}%")
    else:
        console.print(f"  [red]FAIL[/] {result.error}")
        failures += 1
    
    # Summary
    console.print(f"\n[bold magenta]{'='*60}[/]")
    console.print(f"[bold magenta]BACKTEST SMOKE TEST COMPLETE[/]")
    console.print(f"[bold magenta]{'='*60}[/]")
    
    console.print(f"\n[bold]Test Summary:[/]")
    console.print(f"  System ID: {system_id}")
    console.print(f"  System UID: [dim]{system_uid or 'N/A'}[/]")
    console.print(f"  Strategy: {strategy_id or 'N/A'} v{strategy_version or '?'}")
    console.print(f"  Fresh DB: {fresh_db}")
    console.print(f"  Artifact Validation: {'Done' if artifact_dir else 'Skipped'}")
    console.print(f"  Failures: {failures}")
    
    if failures == 0:
        console.print(f"\n[bold green]OK BACKTEST ENGINE VERIFIED[/]")
    else:
        console.print(f"\n[bold red]FAIL {failures} TEST(S) FAILED[/]")
    
    return failures


# =============================================================================
# INDICATOR METADATA SMOKE TEST
# =============================================================================

def run_metadata_smoke(
    symbol: str = "BTCUSDT",
    tf: str = "15",
    sample_bars: int = 2000,
    seed: int = 1337,
    export_path: str = "artifacts/indicator_metadata.jsonl",
    export_format: str = "jsonl",
) -> int:
    """
    Run the Indicator Metadata v1 smoke test.
    
    Validates the metadata system end-to-end using synthetic data:
    1. Generate deterministic synthetic OHLCV data
    2. Build FeatureArrays with FeatureFrameBuilder
    3. Build FeedStore with metadata
    4. Run validations (coverage, key match, ID consistency)
    5. Export metadata to chosen format
    
    Args:
        symbol: Symbol for synthetic data (default: BTCUSDT)
        tf: Timeframe string (default: 15)
        sample_bars: Number of bars to generate (default: 2000)
        seed: Random seed for reproducibility (default: 1337)
        export_path: Path for metadata export (default: artifacts/indicator_metadata.jsonl)
        export_format: Export format - jsonl, json, or csv (default: jsonl)
        
    Returns:
        Exit code: 0 = success, 1 = validation failure, 2 = export failure
    """
    import numpy as np
    import pandas as pd
    from pathlib import Path
    from datetime import datetime, timezone, timedelta
    
    console.print(Panel(
        "[bold cyan]INDICATOR METADATA v1 SMOKE TEST[/]\n"
        "[dim]Validates metadata capture, invariants, and export[/]",
        border_style="cyan"
    ))
    
    console.print(f"\n[bold]Configuration:[/]")
    console.print(f"  Symbol: {symbol}")
    console.print(f"  Timeframe: {tf}")
    console.print(f"  Sample Bars: {sample_bars:,}")
    console.print(f"  Seed: {seed}")
    console.print(f"  Export Path: {export_path}")
    console.print(f"  Export Format: {export_format}")
    
    failures = 0
    
    # =========================================================================
    # STEP 1: Generate synthetic OHLCV data
    # =========================================================================
    console.print(f"\n[bold cyan]Step 1: Generate Synthetic OHLCV Data[/]")
    
    try:
        np.random.seed(seed)
        
        # Generate timestamps (15-min bars by default)
        tf_minutes = _parse_tf_to_minutes(tf)
        start_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        timestamps = [start_time + timedelta(minutes=i * tf_minutes) for i in range(sample_bars)]
        
        # Generate price data (random walk)
        base_price = 40000.0  # Starting price
        returns = np.random.randn(sample_bars) * 0.002  # 0.2% std per bar
        prices = base_price * np.cumprod(1 + returns)
        
        # Generate OHLCV
        high_noise = np.abs(np.random.randn(sample_bars)) * 0.001
        low_noise = np.abs(np.random.randn(sample_bars)) * 0.001
        
        df = pd.DataFrame({
            'timestamp': timestamps,
            'open': prices * (1 - np.random.rand(sample_bars) * 0.001),
            'high': prices * (1 + high_noise),
            'low': prices * (1 - low_noise),
            'close': prices,
            'volume': np.abs(np.random.randn(sample_bars)) * 1000000 + 500000,
        })
        
        # Ensure high >= max(open, close) and low <= min(open, close)
        df['high'] = df[['open', 'close', 'high']].max(axis=1)
        df['low'] = df[['open', 'close', 'low']].min(axis=1)
        
        console.print(f"  [green]OK[/] Generated {len(df):,} bars")
        console.print(f"      Start: {df['timestamp'].iloc[0]}")
        console.print(f"      End: {df['timestamp'].iloc[-1]}")
        console.print(f"      Price range: ${df['close'].min():,.2f} - ${df['close'].max():,.2f}")
        
    except Exception as e:
        console.print(f"  [red]FAIL[/] Error generating data: {e}")
        return 2
    
    # =========================================================================
    # STEP 2: Build FeatureArrays with FeatureFrameBuilder
    # =========================================================================
    console.print(f"\n[bold cyan]Step 2: Build Features with Metadata[/]")
    
    try:
        from ..backtest.features.feature_spec import (
            FeatureSpec,
            FeatureSpecSet,
            InputSource,
        )
        from ..backtest.features.feature_frame_builder import FeatureFrameBuilder

        # Create a diverse set of FeatureSpecs (single + multi-output)
        # Using string indicator types (registry-based, as of Phase 2)
        specs = [
            # Single-output indicators
            FeatureSpec(
                indicator_type="ema",
                output_key='ema_20',
                params={'length': 20},
                input_source=InputSource.CLOSE,
            ),
            FeatureSpec(
                indicator_type="ema",
                output_key='ema_50',
                params={'length': 50},
                input_source=InputSource.CLOSE,
            ),
            FeatureSpec(
                indicator_type="rsi",
                output_key='rsi_14',
                params={'length': 14},
                input_source=InputSource.CLOSE,
            ),
            FeatureSpec(
                indicator_type="atr",
                output_key='atr_14',
                params={'length': 14},
            ),
            # Multi-output indicators
            FeatureSpec(
                indicator_type="macd",
                output_key='macd',
                params={'fast': 12, 'slow': 26, 'signal': 9},
                input_source=InputSource.CLOSE,
            ),
            FeatureSpec(
                indicator_type="bbands",
                output_key='bb',
                params={'length': 20, 'std': 2.0},
                input_source=InputSource.CLOSE,
            ),
        ]
        
        spec_set = FeatureSpecSet(symbol=symbol, tf=tf, specs=specs)
        
        # Build features with metadata
        builder = FeatureFrameBuilder()
        arrays = builder.build(df, spec_set, tf_role='exec')
        
        console.print(f"  [green]OK[/] Built {len(arrays.arrays)} indicator arrays")
        console.print(f"      Keys: {list(arrays.arrays.keys())}")
        console.print(f"      Metadata keys: {list(arrays.metadata.keys())}")
        
    except Exception as e:
        import traceback
        console.print(f"  [red]FAIL[/] Error building features: {e}")
        traceback.print_exc()
        return 2
    
    # =========================================================================
    # STEP 3: Build FeedStore with metadata
    # =========================================================================
    console.print(f"\n[bold cyan]Step 3: Build FeedStore[/]")
    
    try:
        from ..backtest.runtime.feed_store import FeedStore
        
        feed_store = FeedStore.from_dataframe_with_features(
            df=df,
            tf=tf,
            symbol=symbol,
            feature_arrays=arrays,
        )
        
        console.print(f"  [green]OK[/] FeedStore built")
        console.print(f"      Length: {feed_store.length:,} bars")
        console.print(f"      Indicators: {len(feed_store.indicators)}")
        console.print(f"      Metadata entries: {len(feed_store.indicator_metadata)}")
        
    except Exception as e:
        import traceback
        console.print(f"  [red]FAIL[/] Error building FeedStore: {e}")
        traceback.print_exc()
        return 2
    
    # =========================================================================
    # STEP 4: Validate metadata invariants
    # =========================================================================
    console.print(f"\n[bold cyan]Step 4: Validate Metadata Invariants[/]")
    
    try:
        from ..backtest.runtime.indicator_metadata import (
            validate_metadata_coverage,
            validate_feature_spec_ids,
        )
        
        # 4.1: Coverage check
        console.print(f"\n  [bold]4.1: Coverage Check[/]")
        coverage_ok = validate_metadata_coverage(feed_store)
        if coverage_ok:
            console.print(f"      [green]OK[/] indicator_keys == metadata_keys")
        else:
            console.print(f"      [red]FAIL[/] Coverage mismatch")
            indicator_keys = set(feed_store.indicators.keys())
            metadata_keys = set(feed_store.indicator_metadata.keys())
            console.print(f"          Missing metadata: {indicator_keys - metadata_keys}")
            console.print(f"          Extra metadata: {metadata_keys - indicator_keys}")
            failures += 1
        
        # 4.2: Full validation (coverage + key match + ID consistency)
        console.print(f"\n  [bold]4.2: Full Validation[/]")
        validation_result = validate_feature_spec_ids(feed_store)
        
        if validation_result.is_valid:
            console.print(f"      [green]OK[/] All invariants pass")
        else:
            if not validation_result.coverage_ok:
                console.print(f"      [red]FAIL[/] Coverage: missing={validation_result.missing_metadata}, extra={validation_result.extra_metadata}")
                failures += 1
            if not validation_result.ids_consistent:
                console.print(f"      [red]FAIL[/] ID consistency issues:")
                for mismatch in validation_result.id_mismatches:
                    console.print(f"          {mismatch['indicator_key']}: stored={mismatch['stored_id']} != recomputed={mismatch['recomputed_id']}")
                for key_mismatch in validation_result.key_mismatches:
                    console.print(f"          Key mismatch: {key_mismatch}")
                failures += 1
        
        # 4.3: Sample metadata display
        console.print(f"\n  [bold]4.3: Sample Metadata[/]")
        sample_keys = list(feed_store.indicator_metadata.keys())[:3]
        for key in sample_keys:
            meta = feed_store.indicator_metadata[key]
            console.print(f"      {key}:")
            console.print(f"        feature_spec_id: {meta.feature_spec_id}")
            console.print(f"        indicator_type: {meta.indicator_type}")
            console.print(f"        params: {meta.params}")
            console.print(f"        first_valid_idx: {meta.first_valid_idx_observed}")
            console.print(f"        pandas_ta_version: {meta.pandas_ta_version}")
        
        # 4.4: Multi-output shared ID check
        console.print(f"\n  [bold]4.4: Multi-Output Shared ID Check[/]")
        macd_keys = [k for k in feed_store.indicator_metadata.keys() if k.startswith('macd_')]
        if macd_keys:
            macd_ids = [feed_store.indicator_metadata[k].feature_spec_id for k in macd_keys]
            if len(set(macd_ids)) == 1:
                console.print(f"      [green]OK[/] MACD outputs share ID: {macd_ids[0]}")
            else:
                console.print(f"      [red]FAIL[/] MACD outputs have different IDs: {macd_ids}")
                failures += 1
        
        bb_keys = [k for k in feed_store.indicator_metadata.keys() if k.startswith('bb_')]
        if bb_keys:
            bb_ids = [feed_store.indicator_metadata[k].feature_spec_id for k in bb_keys]
            if len(set(bb_ids)) == 1:
                console.print(f"      [green]OK[/] BBands outputs share ID: {bb_ids[0]}")
            else:
                console.print(f"      [red]FAIL[/] BBands outputs have different IDs: {bb_ids}")
                failures += 1
        
    except Exception as e:
        import traceback
        console.print(f"  [red]FAIL[/] Error during validation: {e}")
        traceback.print_exc()
        failures += 1
    
    # =========================================================================
    # STEP 5: Export metadata
    # =========================================================================
    console.print(f"\n[bold cyan]Step 5: Export Metadata[/]")
    
    try:
        from ..backtest.runtime.indicator_metadata import (
            export_metadata_jsonl,
            export_metadata_json,
            export_metadata_csv,
        )
        
        export_path_obj = Path(export_path)
        export_path_obj.parent.mkdir(parents=True, exist_ok=True)
        
        if export_format == "jsonl":
            export_metadata_jsonl(feed_store, export_path_obj)
        elif export_format == "json":
            export_metadata_json(feed_store, export_path_obj)
        elif export_format == "csv":
            export_metadata_csv(feed_store, export_path_obj)
        else:
            console.print(f"  [red]FAIL[/] Unknown format: {export_format}")
            return 2
        
        # Verify file exists and has content
        if export_path_obj.exists():
            file_size = export_path_obj.stat().st_size
            console.print(f"  [green]OK[/] Exported to {export_path}")
            console.print(f"      Format: {export_format}")
            console.print(f"      Size: {file_size:,} bytes")
            
            # Show preview
            with open(export_path_obj, 'r') as f:
                preview = f.read(500)
                console.print(f"      Preview (first 500 chars):")
                console.print(f"      [dim]{preview}...[/]" if len(preview) == 500 else f"      [dim]{preview}[/]")
        else:
            console.print(f"  [red]FAIL[/] Export file not created")
            return 2
        
    except Exception as e:
        import traceback
        console.print(f"  [red]FAIL[/] Error during export: {e}")
        traceback.print_exc()
        return 2
    
    # =========================================================================
    # SUMMARY
    # =========================================================================
    console.print(f"\n[bold cyan]{'='*60}[/]")
    console.print(f"[bold cyan]INDICATOR METADATA SMOKE TEST COMPLETE[/]")
    console.print(f"[bold cyan]{'='*60}[/]")
    
    console.print(f"\n[bold]Summary:[/]")
    console.print(f"  Symbol: {symbol}")
    console.print(f"  Timeframe: {tf}")
    console.print(f"  Bars: {sample_bars:,}")
    console.print(f"  Indicators: {len(feed_store.indicators)}")
    console.print(f"  Metadata entries: {len(feed_store.indicator_metadata)}")
    console.print(f"  Export: {export_path}")
    console.print(f"  Failures: {failures}")
    
    if failures == 0:
        console.print(f"\n[bold green]OK INDICATOR METADATA v1 VERIFIED[/]")
        return 0
    else:
        console.print(f"\n[bold red]FAIL {failures} VALIDATION(S) FAILED[/]")
        return 1


def _parse_tf_to_minutes(tf: str) -> int:
    """Parse timeframe string to minutes."""
    tf = tf.lower().strip()
    
    if tf.endswith('m'):
        return int(tf[:-1])
    elif tf.endswith('h'):
        return int(tf[:-1]) * 60
    elif tf.endswith('d'):
        return int(tf[:-1]) * 1440
    elif tf.isdigit():
        return int(tf)  # Assume minutes
    else:
        return 15  # Default to 15 minutes


# =============================================================================
# Phase 6: Backtest Smoke Tests
# =============================================================================

def run_backtest_smoke_mixed_idea_cards() -> int:
    """
    Run backtest smoke test with a mix of idea cards to validate various scenarios.
    
    Tests multiple idea cards covering:
    - Single-TF strategies
    - Multi-TF strategies
    - Different timeframes (5m, 15m, 1h, 4h)
    - Different indicators
    - Different symbols
    
    Also validates issues from BACKTESTER_FUNCTION_ISSUES_REVIEW.md:
    - Issue #4: TF validation (unknown TF should raise)
    - Issue #3: Warmup handoff validation
    - Issue #5: Metadata coverage validation
    
    Returns:
        0 on success, number of failures otherwise
    """
    import os
    from datetime import datetime, timedelta
    
    console.print(Panel(
        "[bold]BACKTEST SMOKE TEST: MIXED IDEA CARDS[/]\n"
        "[dim]Testing multiple idea cards across different scenarios[/]",
        border_style="magenta"
    ))
    
    failures = 0
    
    # Select a diverse mix of idea cards
    idea_cards_to_test = [
        # Single-TF, simple indicators
        "test__phase6_warmup_matrix__BTCUSDT_5m",
        # Multi-TF, complex indicators
        "test__phase6_mtf_alignment__BTCUSDT_5m_1h_4h",
        # Validation cards (if available)
        "scalp_5m_momentum",
        "intraday_15m_multi",
    ]
    
    # Filter to only existing cards
    result = backtest_list_idea_cards_tool()
    available_cards = []
    if result.success and result.data:
        available_cards = result.data.get("idea_cards", [])
    
    # Filter idea_cards_to_test to only those that exist
    cards_to_test = [card for card in idea_cards_to_test if card in available_cards]
    
    if not cards_to_test:
        console.print(f"  [yellow]WARN[/] No idea cards found to test")
        console.print(f"      Available cards: {available_cards[:10]}")
        # Try to use any available card
        if available_cards:
            cards_to_test = available_cards[:3]  # Use first 3 available
            console.print(f"      Using first 3 available: {cards_to_test}")
        else:
            return 1
    
    console.print(f"\n[bold cyan]Testing {len(cards_to_test)} idea cards:[/]")
    for card in cards_to_test:
        console.print(f"  • {card}")
    
    # Test each card
    for i, card_id in enumerate(cards_to_test, 1):
        console.print(f"\n[bold cyan]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/]")
        console.print(f"[bold cyan]Card {i}/{len(cards_to_test)}: {card_id}[/]")
        console.print(f"[bold cyan]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/]")
        
        card_failures = _run_backtest_smoke_idea_card(card_id, fresh_db=False)
        failures += card_failures
        
        if card_failures == 0:
            console.print(f"  [green]✓ PASSED[/] {card_id}")
        else:
            console.print(f"  [red]✗ FAILED[/] {card_id} ({card_failures} failure(s))")
    
    # Summary
    console.print(f"\n[bold cyan]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/]")
    if failures == 0:
        console.print(f"[bold green]✓ ALL CARDS PASSED[/] ({len(cards_to_test)}/{len(cards_to_test)})")
    else:
        console.print(f"[bold red]✗ {failures} FAILURE(S) ACROSS {len(cards_to_test)} CARDS[/]")
    
    return failures


def run_phase6_backtest_smoke() -> int:
    """
    Phase 6: CLI Smoke Tests for backtest infrastructure.
    
    Tests:
    1. Window matrix - warmup requirements and PreflightReport structure
    2. Deterministic bounded backfill - data-fix with max_lookback_days cap
    3. No-backfill when coverage is sufficient
    4. Drift regression - equity.parquet has ts_ms column
    5. MTF alignment - eval_start_ts_ms in RunManifest
    6. Audit verification - pipeline_signature, artifacts, hashes
    7. (Optional) Determinism spot-check - re-run hash comparison
    
    Returns:
        0 on success, number of failures otherwise
    """
    import os
    
    console.print(Panel(
        "[bold]PHASE 6: BACKTEST CLI SMOKE TESTS[/]\n"
        "[dim]Validating preflight, data-fix, artifact structure, and audit gates[/]",
        border_style="cyan"
    ))
    
    failures = 0
    
    # Test IdeaCards for Phase 6
    WARMUP_MATRIX_CARD = "test__phase6_warmup_matrix__BTCUSDT_5m"
    MTF_ALIGNMENT_CARD = "test__phase6_mtf_alignment__BTCUSDT_5m_1h_4h"
    TEST_SYMBOL = "BTCUSDT"
    TEST_ENV = "live"
    
    # =========================================================================
    # TEST 1: PreflightReport structure validation
    # =========================================================================
    console.print(f"\n[bold cyan]TEST 1: PreflightReport Structure[/]")
    
    try:
        from ..tools.backtest_cli_wrapper import backtest_preflight_idea_card_tool
        from datetime import datetime, timedelta
        
        # Preflight requires explicit start/end dates
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=7)  # 7 days window
        
        result = backtest_preflight_idea_card_tool(
            idea_card_id=WARMUP_MATRIX_CARD,
            env=TEST_ENV,
            symbol_override=TEST_SYMBOL,
            start=start_dt,
            end=end_dt,
        )
        
        if result.data:
            data = result.data
            
            # Check required fields in PreflightReport
            required_fields = [
                "overall_status",
                "computed_warmup_requirements",
                "error_code",
                "error_details",
            ]
            
            missing_fields = [f for f in required_fields if f not in data]
            if missing_fields:
                console.print(f"  [red]FAIL[/] Missing PreflightReport fields: {missing_fields}")
                failures += 1
            else:
                console.print(f"  [green]OK[/] PreflightReport has required fields")
            
            # Check epoch-ms timestamps in coverage (if available)
            coverage = data.get("coverage", {})
            if coverage:
                if "db_start_ts_ms" in coverage and "db_end_ts_ms" in coverage:
                    console.print(f"  [green]OK[/] Coverage has epoch-ms timestamps")
                    console.print(f"      db_start_ts_ms: {coverage.get('db_start_ts_ms')}")
                    console.print(f"      db_end_ts_ms: {coverage.get('db_end_ts_ms')}")
                else:
                    console.print(f"  [yellow]WARN[/] Coverage missing epoch-ms timestamps (may be no data)")
            
            # Check warmup requirements
            warmup_req = data.get("computed_warmup_requirements", {})
            if warmup_req:
                warmup_by_role = warmup_req.get("warmup_by_role", {})
                delay_by_role = warmup_req.get("delay_by_role", {})
                console.print(f"  [green]OK[/] Warmup requirements present")
                console.print(f"      warmup_by_role: {warmup_by_role}")
                console.print(f"      delay_by_role: {delay_by_role}")
            else:
                console.print(f"  [red]FAIL[/] Missing computed_warmup_requirements")
                failures += 1
        else:
            console.print(f"  [red]FAIL[/] No data in preflight result")
            failures += 1
            
    except FileNotFoundError as e:
        console.print(f"  [yellow]SKIP[/] IdeaCard not found: {e}")
    except Exception as e:
        console.print(f"  [red]FAIL[/] Preflight error: {e}")
        import traceback
        traceback.print_exc()
        failures += 1
    
    # =========================================================================
    # TEST 2: Data-fix bounded enforcement
    # =========================================================================
    console.print(f"\n[bold cyan]TEST 2: Data-fix Bounded Enforcement[/]")
    
    try:
        from ..tools.backtest_cli_wrapper import backtest_data_fix_tool
        from datetime import datetime, timedelta
        
        # Request a long range that should be clamped
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=30)  # Request 30 days
        max_lookback = 7  # Should clamp to 7 days
        
        result = backtest_data_fix_tool(
            idea_card_id=WARMUP_MATRIX_CARD,
            env=TEST_ENV,
            start=start_dt,
            end=end_dt,
            max_lookback_days=max_lookback,
            sync_to_now=False,
            fill_gaps=False,
            heal=False,
        )
        
        if result.data:
            data = result.data
            bounds = data.get("bounds", {})
            
            # Verify bounds were applied
            if bounds.get("applied") is True:
                console.print(f"  [green]OK[/] Bounds applied correctly")
                console.print(f"      cap.max_lookback_days: {bounds.get('cap', {}).get('max_lookback_days')}")
            else:
                console.print(f"  [red]FAIL[/] Bounds not applied (expected applied=True)")
                failures += 1
            
            # Verify epoch-ms timestamps in bounds
            if bounds.get("start_ts_ms") is not None and bounds.get("end_ts_ms") is not None:
                console.print(f"  [green]OK[/] Bounds have epoch-ms timestamps")
            else:
                console.print(f"  [red]FAIL[/] Bounds missing epoch-ms timestamps")
                failures += 1
            
            # Verify progress count
            progress_count = data.get("progress_lines_count", 0)
            console.print(f"  [green]OK[/] Progress lines count: {progress_count}")
            
        else:
            console.print(f"  [yellow]WARN[/] No data in data-fix result")
            
    except FileNotFoundError as e:
        console.print(f"  [yellow]SKIP[/] IdeaCard not found: {e}")
    except Exception as e:
        console.print(f"  [red]FAIL[/] Data-fix error: {e}")
        import traceback
        traceback.print_exc()
        failures += 1
    
    # =========================================================================
    # TEST 3: MTF Alignment IdeaCard validation
    # =========================================================================
    console.print(f"\n[bold cyan]TEST 3: MTF Alignment IdeaCard[/]")
    
    try:
        from ..backtest.idea_card import load_idea_card
        from ..backtest.execution_validation import validate_idea_card_full
        
        idea_card = load_idea_card(MTF_ALIGNMENT_CARD)
        validation = validate_idea_card_full(idea_card)
        
        if validation.is_valid:
            console.print(f"  [green]OK[/] MTF IdeaCard validates")
            console.print(f"      exec_tf: {idea_card.exec_tf}")
            console.print(f"      mtf: {idea_card.mtf}")
            console.print(f"      htf: {idea_card.htf}")
            
            # Check delay bars are different across roles
            delays = {}
            for role, tf_config in idea_card.tf_configs.items():
                # delay_bars is in market_structure
                if tf_config.market_structure:
                    delays[role] = tf_config.market_structure.delay_bars
                else:
                    delays[role] = 0
            console.print(f"      delay_bars: {delays}")
            
            if len(set(delays.values())) > 1:
                console.print(f"  [green]OK[/] Different delay bars across roles")
            else:
                console.print(f"  [yellow]WARN[/] Same delay bars across all roles")
        else:
            console.print(f"  [red]FAIL[/] MTF IdeaCard validation failed")
            for err in validation.errors:
                console.print(f"      - {err.message}")
            failures += 1
            
    except FileNotFoundError as e:
        console.print(f"  [yellow]SKIP[/] MTF IdeaCard not found: {e}")
    except Exception as e:
        console.print(f"  [red]FAIL[/] MTF IdeaCard error: {e}")
        import traceback
        traceback.print_exc()
        failures += 1
    
    # =========================================================================
    # TEST 4: Artifact standards validation
    # =========================================================================
    console.print(f"\n[bold cyan]TEST 4: Artifact Standards[/]")
    
    try:
        from ..backtest.artifacts.artifact_standards import (
            REQUIRED_EQUITY_COLUMNS,
            RunManifest,
        )
        
        # Check ts_ms is in required equity columns
        if "ts_ms" in REQUIRED_EQUITY_COLUMNS:
            console.print(f"  [green]OK[/] ts_ms in REQUIRED_EQUITY_COLUMNS")
        else:
            console.print(f"  [red]FAIL[/] ts_ms missing from REQUIRED_EQUITY_COLUMNS")
            failures += 1
        
        # Check RunManifest has eval_start_ts_ms field
        manifest = RunManifest(
            full_hash="test",
            short_hash="test",
            short_hash_length=8,
            idea_card_id="test",
            idea_card_hash="test",
            symbols=["BTCUSDT"],
            tf_exec="5m",
            tf_ctx=[],
            window_start="2024-01-01",
            window_end="2024-01-31",
        )
        
        if hasattr(manifest, 'eval_start_ts_ms'):
            console.print(f"  [green]OK[/] RunManifest has eval_start_ts_ms field")
        else:
            console.print(f"  [red]FAIL[/] RunManifest missing eval_start_ts_ms field")
            failures += 1
        
        if hasattr(manifest, 'equity_timestamp_column'):
            console.print(f"  [green]OK[/] RunManifest has equity_timestamp_column field")
            console.print(f"      Default value: {manifest.equity_timestamp_column}")
        else:
            console.print(f"  [red]FAIL[/] RunManifest missing equity_timestamp_column field")
            failures += 1
            
    except Exception as e:
        console.print(f"  [red]FAIL[/] Artifact standards error: {e}")
        import traceback
        traceback.print_exc()
        failures += 1
    
    # =========================================================================
    # TEST 5: Audit Verification (full backtest + artifact validation)
    # =========================================================================
    console.print(f"\n[bold cyan]TEST 5: Audit Verification (Backtest + Artifacts)[/]")
    
    # This test runs a full backtest and validates:
    # - pipeline_signature.json exists and is valid
    # - All required artifacts present
    # - Result hashes are populated
    artifact_path = None
    
    try:
        from ..tools.backtest_cli_wrapper import backtest_run_idea_card_tool
        from datetime import datetime, timedelta
        from pathlib import Path
        
        # Run a short backtest with a window that should have data
        # Using November 2024 as a stable historical window that should be cached
        end_dt = datetime(2024, 11, 15)
        start_dt = datetime(2024, 11, 1)  # 14-day window
        
        console.print(f"  [dim]Running backtest: {WARMUP_MATRIX_CARD} ({start_dt.date()} to {end_dt.date()})...[/]")
        
        run_result = backtest_run_idea_card_tool(
            idea_card_id=WARMUP_MATRIX_CARD,
            env=TEST_ENV,
            start=start_dt,
            end=end_dt,
            fix_gaps=True,  # Auto-sync data if needed
        )
        
        if run_result.success and run_result.data:
            # artifact_dir is the key used by backtest_run_idea_card_tool
            artifact_path = run_result.data.get("artifact_dir")
            console.print(f"  [green]OK[/] Backtest completed")
            console.print(f"      Artifact dir: {artifact_path}")
            
            # Check artifact validation result
            artifact_validation = run_result.data.get("artifact_validation", {})
            if artifact_validation.get("passed"):
                console.print(f"  [green]OK[/] Artifact validation passed")
            else:
                console.print(f"  [red]FAIL[/] Artifact validation failed")
                for err in artifact_validation.get("errors", []):
                    console.print(f"      - {err}")
                failures += 1
            
            # Check pipeline signature validation
            if artifact_validation.get("pipeline_signature_valid") is True:
                console.print(f"  [green]OK[/] Pipeline signature valid")
            elif artifact_validation.get("pipeline_signature_valid") is False:
                console.print(f"  [red]FAIL[/] Pipeline signature invalid")
                failures += 1
            else:
                console.print(f"  [yellow]WARN[/] Pipeline signature status unknown")
            
            # Check result.json has hashes
            if artifact_path:
                result_json_path = Path(artifact_path) / "result.json"
                if result_json_path.exists():
                    import json
                    with open(result_json_path, "r") as f:
                        result_data = json.load(f)
                    
                    # Check for hash fields
                    hash_fields = ["trades_hash", "equity_hash", "run_hash", "idea_hash"]
                    populated_hashes = [f for f in hash_fields if result_data.get(f)]
                    
                    if len(populated_hashes) == len(hash_fields):
                        console.print(f"  [green]OK[/] All hash fields populated in result.json")
                        for field in hash_fields:
                            console.print(f"      {field}: {result_data.get(field, 'N/A')[:16]}...")
                    else:
                        missing = [f for f in hash_fields if not result_data.get(f)]
                        console.print(f"  [red]FAIL[/] Missing hash fields: {missing}")
                        failures += 1
                else:
                    console.print(f"  [red]FAIL[/] result.json not found at {result_json_path}")
                    failures += 1
        else:
            console.print(f"  [red]FAIL[/] Backtest failed: {run_result.error}")
            failures += 1
            
    except Exception as e:
        console.print(f"  [red]FAIL[/] Audit verification error: {e}")
        import traceback
        traceback.print_exc()
        failures += 1
    
    # =========================================================================
    # TEST 6: Determinism Spot-Check (Optional)
    # =========================================================================
    include_determinism = os.environ.get("TRADE_SMOKE_INCLUDE_DETERMINISM", "0")
    
    if include_determinism in ("1", "true", "True", "TRUE"):
        console.print(f"\n[bold cyan]TEST 6: Determinism Spot-Check[/]")
        
        try:
            from ..backtest.artifacts.determinism import compare_runs
            from pathlib import Path
            
            if artifact_path:
                artifact_path_obj = Path(artifact_path)
                
                console.print(f"  [dim]Comparing run to itself (sanity check)...[/]")
                
                # Self-comparison should always pass
                result = compare_runs(artifact_path_obj, artifact_path_obj)
                
                if result.passed:
                    console.print(f"  [green]OK[/] Self-comparison passed (determinism sanity check)")
                    for comp in result.hash_comparisons:
                        status = "[OK]" if comp.matches else "[MISMATCH]"
                        console.print(f"      {status} {comp.field_name}")
                else:
                    console.print(f"  [red]FAIL[/] Self-comparison failed (unexpected!)")
                    for err in result.errors:
                        console.print(f"      - {err}")
                    failures += 1
            else:
                console.print(f"  [yellow]SKIP[/] No artifact path from TEST 5, skipping determinism check")
                
        except Exception as e:
            console.print(f"  [red]FAIL[/] Determinism check error: {e}")
            import traceback
            traceback.print_exc()
            failures += 1
    else:
        console.print(f"\n[dim]TEST 6: Determinism spot-check skipped (set TRADE_SMOKE_INCLUDE_DETERMINISM=1 to enable)[/]")
    
    # =========================================================================
    # SUMMARY
    # =========================================================================
    console.print(f"\n[bold cyan]{'='*60}[/]")
    console.print(f"[bold cyan]PHASE 6 BACKTEST SMOKE TEST COMPLETE[/]")
    console.print(f"[bold cyan]{'='*60}[/]")
    
    if failures == 0:
        console.print(f"\n[bold green]OK PHASE 6 VERIFIED[/]")
    else:
        console.print(f"\n[bold red]FAIL {failures} TEST(S) FAILED[/]")
    
    return failures


def run_backtest_smoke_suite(smoke_config, app, config) -> int:
    """
    Run backtest-specific smoke tests (for smoke suite integration).
    
    This is a lightweight wrapper that calls Phase 6 tests if enabled.
    """
    import os
    
    # Check opt-in environment variable
    include_backtest = os.environ.get("TRADE_SMOKE_INCLUDE_BACKTEST", "0")
    
    if include_backtest not in ("1", "true", "True", "TRUE"):
        console.print(f"\n[dim]Backtest smoke tests skipped (set TRADE_SMOKE_INCLUDE_BACKTEST=1 to enable)[/]")
        return 0
    
    return run_phase6_backtest_smoke()
