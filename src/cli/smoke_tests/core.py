"""
Core smoke test entry points for TRADE trading bot.

Contains:
- run_smoke_suite: Main entry point for smoke test modes
- run_full_cli_smoke: Full CLI smoke test (data + trading + diagnostics)
"""

from rich.console import Console
from rich.panel import Panel

from ...tools import (
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
    get_risk_limits_tool,
    panic_close_all_tool,
    # Order tools
    set_leverage_tool,
    limit_buy_tool,
    get_open_orders_tool,
    cancel_order_tool,
    cancel_all_orders_tool,
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

# Import from sibling modules
from .data import run_data_builder_smoke
from .backtest import run_backtest_smoke_suite

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

    # PART 8: Backtest Smoke (Phase 6 - opt-in)
    console.print(f"\n[bold magenta]{'='*50}[/]")
    console.print(f"[bold magenta]PART 8: BACKTEST SMOKE (Phase 6)[/]")
    console.print(f"[bold magenta]{'='*50}[/]")
    failures += run_backtest_smoke_suite(smoke_config, app, config)

    console.print(f"\n[bold]Full CLI Smoke Test Complete[/]")
    console.print(f"  Symbols tested: {symbols}")
    console.print(f"  Total failures: {failures}")

    return failures
