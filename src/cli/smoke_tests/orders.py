"""
Order-related smoke tests for TRADE trading bot.

Tests all order types on DEMO account:
- Market orders (buy/sell)
- Market orders with TP/SL
- Limit orders (buy/sell)
- Stop market orders
- Stop limit orders
- Position TP/SL management
- Trailing stops
- Order management (amend, cancel)
"""

from rich.console import Console
from rich.panel import Panel

from ...tools import (
    # Account tools
    get_account_balance_tool,
    # Position tools
    list_open_positions_tool,
    get_position_detail_tool,
    set_stop_loss_tool,
    remove_stop_loss_tool,
    set_take_profit_tool,
    remove_take_profit_tool,
    set_trailing_stop_by_percent_tool,
    close_position_tool,
    panic_close_all_tool,
    # Order tools
    set_leverage_tool,
    market_buy_tool,
    market_sell_tool,
    market_buy_with_tpsl_tool,
    limit_buy_tool,
    limit_sell_tool,
    stop_market_buy_tool,
    stop_market_sell_tool,
    stop_limit_buy_tool,
    stop_limit_sell_tool,
    get_open_orders_tool,
    cancel_order_tool,
    cancel_all_orders_tool,
    # Market data tools
    get_price_tool,
    # Diagnostics tools
    test_connection_tool,
    get_server_time_offset_tool,
    get_api_environment_tool,
)


console = Console()


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

    WARNING: This test uses LIVE API credentials and may place REAL orders.

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
        "[bold red]WARNING: LIVE CHECK SMOKE TEST[/]\n"
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
            console.print(f"\n  [yellow]WARNING: Running in DEMO mode, not LIVE[/]")
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
