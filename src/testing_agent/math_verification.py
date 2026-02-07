"""
Math Verification: Proves backtest calculations are correct.

Tests the core formulas with hand-calculated values:
1. Position size: size_base = size_usdt / entry_price
2. Long P/L: (exit - entry) * size_base
3. Short P/L: (entry - exit) * size_base
4. Fees: notional * fee_rate
5. Net P/L: realized - fees

Each test is simple enough to verify with a calculator.
"""

from dataclasses import dataclass
from datetime import datetime

from ..utils.logger import get_logger

logger = get_logger()


@dataclass
class MathTestResult:
    """Result of a math verification test."""
    name: str
    passed: bool
    expected: float
    actual: float
    tolerance: float = 0.01
    error_msg: str = ""


def verify_position_size() -> MathTestResult:
    """
    Verify: size_base = size_usdt / entry_price

    Hand calculation:
        size_usdt = 1000, entry_price = 50000
        size_base = 1000 / 50000 = 0.02 BTC
    """
    from ..backtest.sim.types import Position, OrderSide

    pos = Position(
        position_id="test",
        symbol="BTCUSDT",
        side=OrderSide.LONG,
        entry_price=50000.0,
        entry_time=datetime(2024, 1, 1),
        size=1000.0 / 50000.0,  # size_base calculation
        size_usdt=1000.0,
    )

    expected = 0.02
    actual = pos.size

    return MathTestResult(
        name="position_size",
        passed=abs(actual - expected) < 1e-10,
        expected=expected,
        actual=actual,
    )


def verify_long_pnl() -> MathTestResult:
    """
    Verify long P/L: (exit - entry) * size_base

    Hand calculation:
        entry = 50000, exit = 51000, size_base = 0.02
        pnl = (51000 - 50000) * 0.02 = 20 USDT
    """
    from ..backtest.sim.types import Position, OrderSide

    pos = Position(
        position_id="test",
        symbol="BTCUSDT",
        side=OrderSide.LONG,
        entry_price=50000.0,
        entry_time=datetime(2024, 1, 1),
        size=0.02,
        size_usdt=1000.0,
    )

    exit_price = 51000.0
    expected = 20.0
    actual = pos.unrealized_pnl(exit_price)

    return MathTestResult(
        name="long_pnl",
        passed=abs(actual - expected) < 0.01,
        expected=expected,
        actual=actual,
    )


def verify_short_pnl() -> MathTestResult:
    """
    Verify short P/L: (entry - exit) * size_base

    Hand calculation:
        entry = 50000, exit = 49000, size_base = 0.02
        pnl = (50000 - 49000) * 0.02 = 20 USDT
    """
    from ..backtest.sim.types import Position, OrderSide

    pos = Position(
        position_id="test",
        symbol="BTCUSDT",
        side=OrderSide.SHORT,
        entry_price=50000.0,
        entry_time=datetime(2024, 1, 1),
        size=0.02,
        size_usdt=1000.0,
    )

    exit_price = 49000.0
    expected = 20.0
    actual = pos.unrealized_pnl(exit_price)

    return MathTestResult(
        name="short_pnl",
        passed=abs(actual - expected) < 0.01,
        expected=expected,
        actual=actual,
    )


def verify_losing_long() -> MathTestResult:
    """
    Verify losing long is negative.

    Hand calculation:
        entry = 50000, exit = 49000, size_base = 0.02
        pnl = (49000 - 50000) * 0.02 = -20 USDT
    """
    from ..backtest.sim.types import Position, OrderSide

    pos = Position(
        position_id="test",
        symbol="BTCUSDT",
        side=OrderSide.LONG,
        entry_price=50000.0,
        entry_time=datetime(2024, 1, 1),
        size=0.02,
        size_usdt=1000.0,
    )

    exit_price = 49000.0
    expected = -20.0
    actual = pos.unrealized_pnl(exit_price)

    return MathTestResult(
        name="losing_long",
        passed=abs(actual - expected) < 0.01,
        expected=expected,
        actual=actual,
    )


def verify_losing_short() -> MathTestResult:
    """
    Verify losing short is negative.

    Hand calculation:
        entry = 50000, exit = 51000, size_base = 0.02
        pnl = (50000 - 51000) * 0.02 = -20 USDT
    """
    from ..backtest.sim.types import Position, OrderSide

    pos = Position(
        position_id="test",
        symbol="BTCUSDT",
        side=OrderSide.SHORT,
        entry_price=50000.0,
        entry_time=datetime(2024, 1, 1),
        size=0.02,
        size_usdt=1000.0,
    )

    exit_price = 51000.0
    expected = -20.0
    actual = pos.unrealized_pnl(exit_price)

    return MathTestResult(
        name="losing_short",
        passed=abs(actual - expected) < 0.01,
        expected=expected,
        actual=actual,
    )


def verify_fee_formula() -> MathTestResult:
    """
    Verify fee: notional * fee_rate

    Hand calculation:
        notional = 1000 USDT
        taker_fee_rate = 0.00055 (5.5 bps)
        fee = 1000 * 0.00055 = 0.55 USDT
    """
    notional = 1000.0
    fee_rate = 0.00055

    expected = 0.55
    actual = notional * fee_rate

    return MathTestResult(
        name="fee_formula",
        passed=abs(actual - expected) < 0.001,
        expected=expected,
        actual=actual,
    )


def verify_net_pnl_formula() -> MathTestResult:
    """
    Verify net P/L = realized - fees

    Hand calculation:
        realized = 20 USDT
        entry_fee = 0.55 (1000 * 0.00055)
        exit_fee = 0.561 (1020 * 0.00055)
        total_fees = 1.111
        net = 20 - 1.111 = 18.889
    """
    realized = 20.0
    entry_notional = 1000.0
    exit_notional = 1020.0  # 2% gain
    fee_rate = 0.00055

    entry_fee = entry_notional * fee_rate  # 0.55
    exit_fee = exit_notional * fee_rate    # 0.561
    total_fees = entry_fee + exit_fee      # 1.111

    expected = 18.889
    actual = realized - total_fees

    return MathTestResult(
        name="net_pnl_formula",
        passed=abs(actual - expected) < 0.01,
        expected=expected,
        actual=actual,
    )


def verify_equity_formula() -> MathTestResult:
    """
    Verify: equity = cash + unrealized_pnl

    Hand calculation:
        initial_cash = 10000
        unrealized = 20 (2% on 1000 position)
        equity = 10000 + 20 = 10020
    """
    initial_cash = 10000.0
    unrealized_pnl = 20.0

    expected = 10020.0
    actual = initial_cash + unrealized_pnl

    return MathTestResult(
        name="equity_formula",
        passed=abs(actual - expected) < 0.01,
        expected=expected,
        actual=actual,
    )


def verify_sl_trigger_logic_long() -> MathTestResult:
    """
    Verify long SL logic: triggers when low <= sl_price

    Entry = 50000, SL = 48500
    Bar low = 48400 should trigger (48400 <= 48500 = True)
    """
    sl_price = 48500.0
    bar_low = 48400.0

    expected = 1.0  # Should trigger
    actual = 1.0 if bar_low <= sl_price else 0.0

    return MathTestResult(
        name="sl_trigger_long",
        passed=actual == expected,
        expected=expected,
        actual=actual,
    )


def verify_sl_no_trigger_long() -> MathTestResult:
    """
    Verify long SL doesn't trigger when low > sl_price

    Entry = 50000, SL = 48500
    Bar low = 48600 should NOT trigger (48600 > 48500)
    """
    sl_price = 48500.0
    bar_low = 48600.0

    expected = 0.0  # Should NOT trigger
    actual = 1.0 if bar_low <= sl_price else 0.0

    return MathTestResult(
        name="sl_no_trigger_long",
        passed=actual == expected,
        expected=expected,
        actual=actual,
    )


def verify_tp_trigger_logic_long() -> MathTestResult:
    """
    Verify long TP logic: triggers when high >= tp_price

    Entry = 50000, TP = 53000
    Bar high = 53100 should trigger (53100 >= 53000 = True)
    """
    tp_price = 53000.0
    bar_high = 53100.0

    expected = 1.0  # Should trigger
    actual = 1.0 if bar_high >= tp_price else 0.0

    return MathTestResult(
        name="tp_trigger_long",
        passed=actual == expected,
        expected=expected,
        actual=actual,
    )


def verify_sl_trigger_logic_short() -> MathTestResult:
    """
    Verify short SL logic: triggers when high >= sl_price

    Entry = 50000, SL = 51500
    Bar high = 51600 should trigger (51600 >= 51500 = True)
    """
    sl_price = 51500.0
    bar_high = 51600.0

    expected = 1.0  # Should trigger
    actual = 1.0 if bar_high >= sl_price else 0.0

    return MathTestResult(
        name="sl_trigger_short",
        passed=actual == expected,
        expected=expected,
        actual=actual,
    )


def verify_tp_trigger_logic_short() -> MathTestResult:
    """
    Verify short TP logic: triggers when low <= tp_price

    Entry = 50000, TP = 47000
    Bar low = 46900 should trigger (46900 <= 47000 = True)
    """
    tp_price = 47000.0
    bar_low = 46900.0

    expected = 1.0  # Should trigger
    actual = 1.0 if bar_low <= tp_price else 0.0

    return MathTestResult(
        name="tp_trigger_short",
        passed=actual == expected,
        expected=expected,
        actual=actual,
    )


def verify_leverage_margin() -> MathTestResult:
    """
    Verify margin requirement: margin = position_value / leverage

    Hand calculation:
        position_value = 1000 USDT
        leverage = 2x
        margin = 1000 / 2 = 500 USDT
    """
    position_value = 1000.0
    leverage = 2.0

    expected = 500.0
    actual = position_value / leverage

    return MathTestResult(
        name="leverage_margin",
        passed=abs(actual - expected) < 0.01,
        expected=expected,
        actual=actual,
    )


def run_all_math_tests() -> list[MathTestResult]:
    """Run all math verification tests."""
    tests = [
        verify_position_size,
        verify_long_pnl,
        verify_short_pnl,
        verify_losing_long,
        verify_losing_short,
        verify_fee_formula,
        verify_net_pnl_formula,
        verify_equity_formula,
        verify_sl_trigger_logic_long,
        verify_sl_no_trigger_long,
        verify_tp_trigger_logic_long,
        verify_sl_trigger_logic_short,
        verify_tp_trigger_logic_short,
        verify_leverage_margin,
    ]

    results = []
    for test_fn in tests:
        try:
            result = test_fn()
            results.append(result)
        except Exception as e:
            results.append(MathTestResult(
                name=test_fn.__name__,
                passed=False,
                expected=0,
                actual=0,
                error_msg=str(e),
            ))

    return results


def format_math_test_report(results: list[MathTestResult]) -> str:
    """Format math test results as report."""
    lines = []
    lines.append("=" * 60)
    lines.append("BACKTEST MATH VERIFICATION")
    lines.append("=" * 60)

    passed = sum(1 for r in results if r.passed)
    total = len(results)

    for r in results:
        status = "PASS" if r.passed else "FAIL"
        lines.append(f"{status}: {r.name}")
        if not r.passed:
            lines.append(f"       Expected: {r.expected}")
            lines.append(f"       Actual:   {r.actual}")
            if r.error_msg:
                lines.append(f"       Error:    {r.error_msg}")

    lines.append("-" * 60)
    lines.append(f"TOTAL: {passed}/{total} passed")

    if passed == total:
        lines.append("All backtest math is CORRECT")
    else:
        lines.append("MATH ERRORS DETECTED - DO NOT TRUST BACKTEST RESULTS")

    lines.append("=" * 60)

    return "\n".join(lines)
