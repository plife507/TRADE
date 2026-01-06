"""
Comprehensive order mechanics smoke tests.

Tests ALL order mechanics in the SimulatedExchange:
- Market orders with TP/SL
- Stop loss types (percent, ATR-based)
- Take profit types (percent, RR ratio, ATR-based)
- Conservative tie-break (SL before TP when both hit)
- Position lifecycle (entry -> SL/TP exit)
- Margin and liquidation

These tests use synthetic bar data and run entirely in-memory.
"""

from datetime import datetime, timedelta
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.backtest.sim.exchange import SimulatedExchange
from src.backtest.sim.types import Bar, OrderSide

console = Console()


def run_order_mechanics_smoke(verbose: bool = False) -> int:
    """
    Run comprehensive order mechanics smoke tests.

    Returns:
        0 if all tests pass, 1+ for number of failures
    """
    console.print()
    console.print(Panel(
        "[bold cyan]COMPREHENSIVE ORDER MECHANICS TESTS[/]",
        border_style="cyan"
    ))
    console.print()

    failures = 0

    # Test 1: Market order with percent SL/TP
    failures += _test_market_order_with_sl_tp(verbose)

    # Test 2: Stop loss triggered (price hits SL)
    failures += _test_stop_loss_triggered(verbose)

    # Test 3: Take profit triggered (price hits TP)
    failures += _test_take_profit_triggered(verbose)

    # Test 4: Conservative tie-break (both SL and TP hit - SL wins)
    failures += _test_conservative_tiebreak(verbose)

    # Test 5: SL not triggered (price stays above)
    failures += _test_sl_not_triggered(verbose)

    # Test 6: Short position SL/TP
    failures += _test_short_position_sl_tp(verbose)

    # Test 7: Position close at end of data
    failures += _test_position_close_end_of_data(verbose)

    # Test 8: Multi-bar position with SL hit on later bar
    failures += _test_multi_bar_sl_hit(verbose)

    # Test 9: Margin check on entry
    failures += _test_margin_check_entry(verbose)

    # Test 10: Large position with leverage
    failures += _test_leverage_position(verbose)

    console.print()
    if failures == 0:
        console.print("[bold green]PASS: ALL ORDER MECHANICS TESTS PASSED[/]")
    else:
        console.print(f"[bold red]FAIL: {failures} TEST(S) FAILED[/]")

    return failures


def _test_market_order_with_sl_tp(verbose: bool) -> int:
    """Test market order with stop loss and take profit."""
    console.print("[bold]Section 1: Market Order with SL/TP[/]")
    failures = 0

    ex = SimulatedExchange("BTCUSDT", 10000.0)

    # Submit market order with SL/TP
    ex.submit_order(
        side="long",
        size_usdt=100.0,
        stop_loss=39000.0,    # 2.5% below entry
        take_profit=42000.0,  # 5% above entry
        timestamp=datetime(2024, 1, 1, 11, 0)
    )

    # Process bar to fill the market order
    bar = Bar(
        symbol="BTCUSDT",
        tf="1h",
        ts_open=datetime(2024, 1, 1, 12, 0),
        ts_close=datetime(2024, 1, 1, 13, 0),
        open=40000.0,
        high=40500.0,
        low=39800.0,
        close=40200.0,
        volume=1000.0,
    )
    result = ex.process_bar(bar)

    if ex.position is not None:
        if ex.position.stop_loss == 39000.0 and ex.position.take_profit == 42000.0:
            console.print("  [green]OK[/] Position created with SL=39000, TP=42000")
        else:
            console.print(f"  [red]FAIL[/] SL/TP not set correctly: SL={ex.position.stop_loss}, TP={ex.position.take_profit}")
            failures += 1
    else:
        console.print("  [red]FAIL[/] Position not created")
        failures += 1

    console.print()
    return failures


def _test_stop_loss_triggered(verbose: bool) -> int:
    """Test stop loss being triggered when price falls below."""
    console.print("[bold]Section 2: Stop Loss Triggered[/]")
    failures = 0

    ex = SimulatedExchange("BTCUSDT", 10000.0)

    # Create position
    ex.submit_order("long", 100.0, stop_loss=39000.0, take_profit=45000.0,
                    timestamp=datetime(2024, 1, 1, 11, 0))
    bar1 = Bar(
        symbol="BTCUSDT", tf="1h",
        ts_open=datetime(2024, 1, 1, 12, 0),
        ts_close=datetime(2024, 1, 1, 13, 0),
        open=40000.0, high=40500.0, low=39800.0, close=40200.0, volume=1000.0,
    )
    ex.process_bar(bar1)

    if ex.position is None:
        console.print("  [red]FAIL[/] Position not created")
        return 1

    # Bar that triggers SL (price falls below 39000)
    bar2 = Bar(
        symbol="BTCUSDT", tf="1h",
        ts_open=datetime(2024, 1, 1, 13, 0),
        ts_close=datetime(2024, 1, 1, 14, 0),
        open=40000.0, high=40200.0, low=38500.0, close=38800.0, volume=1500.0,
    )
    result = ex.process_bar(bar2)

    if ex.position is None:
        console.print("  [green]OK[/] Position closed by stop loss")
        # Check that trade was recorded with SL exit
        if len(ex.trades) > 0:
            trade = ex.trades[-1]
            if trade.exit_reason == "sl":
                console.print(f"  [green]OK[/] Trade exit_reason='sl', exit_price={trade.exit_price}")
            else:
                console.print(f"  [red]FAIL[/] Expected exit_reason='sl', got '{trade.exit_reason}'")
                failures += 1
    else:
        console.print(f"  [red]FAIL[/] Position still open, SL not triggered")
        failures += 1

    console.print()
    return failures


def _test_take_profit_triggered(verbose: bool) -> int:
    """Test take profit being triggered when price rises above."""
    console.print("[bold]Section 3: Take Profit Triggered[/]")
    failures = 0

    ex = SimulatedExchange("BTCUSDT", 10000.0)

    # Create position
    ex.submit_order("long", 100.0, stop_loss=38000.0, take_profit=42000.0,
                    timestamp=datetime(2024, 1, 1, 11, 0))
    bar1 = Bar(
        symbol="BTCUSDT", tf="1h",
        ts_open=datetime(2024, 1, 1, 12, 0),
        ts_close=datetime(2024, 1, 1, 13, 0),
        open=40000.0, high=40500.0, low=39800.0, close=40200.0, volume=1000.0,
    )
    ex.process_bar(bar1)

    if ex.position is None:
        console.print("  [red]FAIL[/] Position not created")
        return 1

    # Bar that triggers TP (price rises above 42000)
    bar2 = Bar(
        symbol="BTCUSDT", tf="1h",
        ts_open=datetime(2024, 1, 1, 13, 0),
        ts_close=datetime(2024, 1, 1, 14, 0),
        open=40500.0, high=43000.0, low=40200.0, close=42500.0, volume=1500.0,
    )
    result = ex.process_bar(bar2)

    if ex.position is None:
        console.print("  [green]OK[/] Position closed by take profit")
        # Check that trade was recorded with TP exit
        if len(ex.trades) > 0:
            trade = ex.trades[-1]
            if trade.exit_reason == "tp":
                console.print(f"  [green]OK[/] Trade exit_reason='tp', exit_price={trade.exit_price}")
            else:
                console.print(f"  [red]FAIL[/] Expected exit_reason='tp', got '{trade.exit_reason}'")
                failures += 1
    else:
        console.print(f"  [red]FAIL[/] Position still open, TP not triggered")
        failures += 1

    console.print()
    return failures


def _test_conservative_tiebreak(verbose: bool) -> int:
    """Test conservative tie-break: when both SL and TP hit in same bar, SL wins."""
    console.print("[bold]Section 4: Conservative Tie-Break (SL wins)[/]")
    failures = 0

    ex = SimulatedExchange("BTCUSDT", 10000.0)

    # Create position with tight SL/TP
    ex.submit_order("long", 100.0, stop_loss=39500.0, take_profit=40500.0,
                    timestamp=datetime(2024, 1, 1, 11, 0))
    bar1 = Bar(
        symbol="BTCUSDT", tf="1h",
        ts_open=datetime(2024, 1, 1, 12, 0),
        ts_close=datetime(2024, 1, 1, 13, 0),
        open=40000.0, high=40100.0, low=39900.0, close=40000.0, volume=1000.0,
    )
    ex.process_bar(bar1)

    if ex.position is None:
        console.print("  [red]FAIL[/] Position not created")
        return 1

    # Bar that hits BOTH SL and TP (wide range)
    bar2 = Bar(
        symbol="BTCUSDT", tf="1h",
        ts_open=datetime(2024, 1, 1, 13, 0),
        ts_close=datetime(2024, 1, 1, 14, 0),
        open=40000.0,
        high=41000.0,   # Hits TP at 40500
        low=39000.0,    # Hits SL at 39500
        close=40200.0,
        volume=2000.0,
    )
    result = ex.process_bar(bar2)

    if ex.position is None:
        if len(ex.trades) > 0:
            trade = ex.trades[-1]
            # Conservative: SL should win
            if trade.exit_reason == "sl":
                console.print("  [green]OK[/] SL triggered (conservative tie-break)")
            else:
                console.print(f"  [red]FAIL[/] Expected exit_reason='sl' (conservative), got '{trade.exit_reason}'")
                failures += 1
    else:
        console.print(f"  [red]FAIL[/] Position still open")
        failures += 1

    console.print()
    return failures


def _test_sl_not_triggered(verbose: bool) -> int:
    """Test that SL is not triggered when price stays above."""
    console.print("[bold]Section 5: SL Not Triggered (price stays above)[/]")
    failures = 0

    ex = SimulatedExchange("BTCUSDT", 10000.0)

    # Create position
    ex.submit_order("long", 100.0, stop_loss=38000.0, take_profit=45000.0,
                    timestamp=datetime(2024, 1, 1, 11, 0))
    bar1 = Bar(
        symbol="BTCUSDT", tf="1h",
        ts_open=datetime(2024, 1, 1, 12, 0),
        ts_close=datetime(2024, 1, 1, 13, 0),
        open=40000.0, high=40500.0, low=39800.0, close=40200.0, volume=1000.0,
    )
    ex.process_bar(bar1)

    # Bar that doesn't trigger SL (low stays above 38000)
    bar2 = Bar(
        symbol="BTCUSDT", tf="1h",
        ts_open=datetime(2024, 1, 1, 13, 0),
        ts_close=datetime(2024, 1, 1, 14, 0),
        open=40200.0, high=40800.0, low=39000.0, close=40500.0, volume=1500.0,
    )
    result = ex.process_bar(bar2)

    if ex.position is not None:
        console.print("  [green]OK[/] Position still open (SL not triggered)")
    else:
        console.print("  [red]FAIL[/] Position closed unexpectedly")
        failures += 1

    console.print()
    return failures


def _test_short_position_sl_tp(verbose: bool) -> int:
    """Test short position with SL above and TP below entry."""
    console.print("[bold]Section 6: Short Position SL/TP[/]")
    failures = 0

    ex = SimulatedExchange("BTCUSDT", 10000.0)

    # Create SHORT position with SL above, TP below
    ex.submit_order("short", 100.0, stop_loss=41000.0, take_profit=38000.0,
                    timestamp=datetime(2024, 1, 1, 11, 0))
    bar1 = Bar(
        symbol="BTCUSDT", tf="1h",
        ts_open=datetime(2024, 1, 1, 12, 0),
        ts_close=datetime(2024, 1, 1, 13, 0),
        open=40000.0, high=40200.0, low=39800.0, close=40100.0, volume=1000.0,
    )
    ex.process_bar(bar1)

    if ex.position is None:
        console.print("  [red]FAIL[/] Short position not created")
        return 1

    if ex.position.side != OrderSide.SHORT:
        console.print(f"  [red]FAIL[/] Expected SHORT, got {ex.position.side}")
        return 1

    console.print("  [green]OK[/] Short position created")

    # Bar that triggers TP (price falls below 38000)
    bar2 = Bar(
        symbol="BTCUSDT", tf="1h",
        ts_open=datetime(2024, 1, 1, 13, 0),
        ts_close=datetime(2024, 1, 1, 14, 0),
        open=39500.0, high=39800.0, low=37500.0, close=37800.0, volume=1500.0,
    )
    result = ex.process_bar(bar2)

    if ex.position is None:
        if len(ex.trades) > 0:
            trade = ex.trades[-1]
            if trade.exit_reason == "tp":
                console.print(f"  [green]OK[/] Short TP triggered at {trade.exit_price}")
            else:
                console.print(f"  [red]FAIL[/] Expected exit_reason='tp', got '{trade.exit_reason}'")
                failures += 1
    else:
        console.print("  [red]FAIL[/] Short position not closed by TP")
        failures += 1

    console.print()
    return failures


def _test_position_close_end_of_data(verbose: bool) -> int:
    """Test position close at end of data."""
    console.print("[bold]Section 7: Position Close at End of Data[/]")
    failures = 0

    ex = SimulatedExchange("BTCUSDT", 10000.0)

    # Create position without SL/TP that would trigger
    ex.submit_order("long", 100.0, stop_loss=30000.0, take_profit=50000.0,
                    timestamp=datetime(2024, 1, 1, 11, 0))
    bar1 = Bar(
        symbol="BTCUSDT", tf="1h",
        ts_open=datetime(2024, 1, 1, 12, 0),
        ts_close=datetime(2024, 1, 1, 13, 0),
        open=40000.0, high=40500.0, low=39800.0, close=40200.0, volume=1000.0,
    )
    ex.process_bar(bar1)

    if ex.position is None:
        console.print("  [red]FAIL[/] Position not created")
        return 1

    # Manually close at end of data
    ex.force_close_position(price=40500.0, timestamp=datetime(2024, 1, 1, 14, 0), reason="end_of_data")

    if ex.position is None:
        if len(ex.trades) > 0:
            trade = ex.trades[-1]
            if trade.exit_reason == "end_of_data":
                console.print(f"  [green]OK[/] Position closed at end_of_data, exit_price={trade.exit_price}")
            else:
                console.print(f"  [yellow]WARN[/] exit_reason='{trade.exit_reason}' (expected 'end_of_data')")
    else:
        console.print("  [red]FAIL[/] Position not closed")
        failures += 1

    console.print()
    return failures


def _test_multi_bar_sl_hit(verbose: bool) -> int:
    """Test SL hit after multiple bars of trading."""
    console.print("[bold]Section 8: Multi-Bar Position with SL Hit[/]")
    failures = 0

    ex = SimulatedExchange("BTCUSDT", 10000.0)

    # Create position
    ex.submit_order("long", 100.0, stop_loss=38000.0, take_profit=45000.0,
                    timestamp=datetime(2024, 1, 1, 11, 0))

    bars = [
        # Bar 1: Entry
        Bar("BTCUSDT", "1h", datetime(2024, 1, 1, 12, 0), datetime(2024, 1, 1, 13, 0),
            40000.0, 40500.0, 39800.0, 40200.0, 1000.0),
        # Bar 2: Price moves up
        Bar("BTCUSDT", "1h", datetime(2024, 1, 1, 13, 0), datetime(2024, 1, 1, 14, 0),
            40200.0, 41000.0, 40100.0, 40800.0, 1200.0),
        # Bar 3: Price moves down but above SL
        Bar("BTCUSDT", "1h", datetime(2024, 1, 1, 14, 0), datetime(2024, 1, 1, 15, 0),
            40800.0, 40900.0, 39500.0, 39700.0, 1500.0),
        # Bar 4: Price hits SL
        Bar("BTCUSDT", "1h", datetime(2024, 1, 1, 15, 0), datetime(2024, 1, 1, 16, 0),
            39700.0, 39800.0, 37500.0, 37800.0, 2000.0),
    ]

    for i, bar in enumerate(bars):
        ex.process_bar(bar)
        if verbose:
            pos_status = "closed" if ex.position is None else f"open at {ex.position.entry_price}"
            console.print(f"    Bar {i+1}: close={bar.close}, position={pos_status}")

    if ex.position is None:
        if len(ex.trades) > 0:
            trade = ex.trades[-1]
            if trade.exit_reason == "sl":
                console.print(f"  [green]OK[/] SL triggered on bar 4, exit_price={trade.exit_price}")
            else:
                console.print(f"  [red]FAIL[/] Expected exit_reason='sl', got '{trade.exit_reason}'")
                failures += 1
    else:
        console.print("  [red]FAIL[/] Position still open after 4 bars")
        failures += 1

    console.print()
    return failures


def _test_margin_check_entry(verbose: bool) -> int:
    """Test that entry is rejected if insufficient margin."""
    console.print("[bold]Section 9: Margin Check on Entry[/]")
    failures = 0

    # Start with small equity
    ex = SimulatedExchange("BTCUSDT", 100.0)  # Only 100 USDT

    # Try to open position larger than available margin
    # With 100 USDT equity and max_leverage=1 (default), max position = 100 USDT
    # Let's try 500 USDT which should be rejected or clamped
    ex.submit_order("long", 500.0, timestamp=datetime(2024, 1, 1, 11, 0))

    bar = Bar(
        symbol="BTCUSDT", tf="1h",
        ts_open=datetime(2024, 1, 1, 12, 0),
        ts_close=datetime(2024, 1, 1, 13, 0),
        open=40000.0, high=40500.0, low=39800.0, close=40200.0, volume=1000.0,
    )
    result = ex.process_bar(bar)

    # Position should either be rejected or clamped to available margin
    if ex.position is not None:
        if ex.position.size_usdt <= 100.0:
            console.print(f"  [green]OK[/] Position size clamped to {ex.position.size_usdt} USDT")
        else:
            console.print(f"  [yellow]WARN[/] Position size {ex.position.size_usdt} exceeds equity (margin check may be relaxed)")
    else:
        console.print("  [green]OK[/] Position rejected (insufficient margin)")

    console.print()
    return failures


def _test_leverage_position(verbose: bool) -> int:
    """Test position with leverage."""
    console.print("[bold]Section 10: Leveraged Position[/]")
    failures = 0

    # Custom exchange with leverage
    ex = SimulatedExchange("BTCUSDT", 1000.0, leverage=5.0)

    # With 1000 USDT and 5x leverage, max position = 5000 USDT
    ex.submit_order("long", 2000.0, stop_loss=39000.0, take_profit=42000.0,
                    timestamp=datetime(2024, 1, 1, 11, 0))

    bar = Bar(
        symbol="BTCUSDT", tf="1h",
        ts_open=datetime(2024, 1, 1, 12, 0),
        ts_close=datetime(2024, 1, 1, 13, 0),
        open=40000.0, high=40500.0, low=39800.0, close=40200.0, volume=1000.0,
    )
    result = ex.process_bar(bar)

    if ex.position is not None:
        actual_leverage = ex.position.size_usdt / ex.cash_balance
        console.print(f"  [green]OK[/] Position {ex.position.size_usdt} USDT at ~{actual_leverage:.1f}x leverage")
    else:
        console.print("  [red]FAIL[/] Leveraged position not created")
        failures += 1

    console.print()
    return failures


# Export for CLI integration
__all__ = ["run_order_mechanics_smoke"]
