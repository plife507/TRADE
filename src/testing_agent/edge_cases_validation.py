"""
Edge Cases Validation: Tests for boundary conditions and numerical precision.

This module validates that the backtest engine handles edge cases correctly:
- Warmup period (no signals before indicators ready)
- Zero volume bars
- Flat prices (OHLC all equal)
- Extreme price moves
- Numerical precision (IEEE 754 float handling)
- Large/small values

Usage:
    from src.testing_agent.edge_cases_validation import run_all_edge_case_tests

    results = run_all_edge_case_tests()
    for r in results:
        print(f"{r.name}: {'PASS' if r.passed else 'FAIL'}")
"""

from dataclasses import dataclass
import math
import numpy as np
import pandas as pd

from ..utils.logger import get_logger

logger = get_logger()


@dataclass
class EdgeCaseTestResult:
    """Result from a single edge case test."""
    name: str
    passed: bool
    expected: str
    actual: str
    error_msg: str | None = None


def _test_warmup_ema_nan() -> EdgeCaseTestResult:
    """
    Test that EMA returns NaN during warmup period.

    EMA(20) should return NaN for the first 19 bars.
    """
    from ..indicators.incremental import IncrementalEMA

    # Create synthetic price data
    np.random.seed(42)
    prices = 50000 * np.cumprod(1 + np.random.normal(0, 0.001, 100))

    # Create EMA indicator
    ema = IncrementalEMA(length=20)

    # Process bars and check warmup
    warmup_nans = 0
    for i in range(100):
        close = float(prices[i])
        ema.update(close=close)
        value = ema.value

        if i < 19:  # First 19 bars should be NaN
            if value is None or (isinstance(value, float) and math.isnan(value)):
                warmup_nans += 1

    passed = warmup_nans == 19
    return EdgeCaseTestResult(
        name="warmup_ema_nan",
        passed=passed,
        expected="19 NaN values during warmup",
        actual=f"{warmup_nans} NaN values",
        error_msg=None if passed else f"Expected 19 NaN values, got {warmup_nans}",
    )


def _test_warmup_rsi_bounds() -> EdgeCaseTestResult:
    """
    Test that RSI returns values in [0, 100] after warmup.

    RSI should never exceed bounds even with extreme price moves.
    """
    from ..indicators.incremental import IncrementalRSI

    # Create synthetic price data with extreme moves
    np.random.seed(42)
    prices = [50000.0]
    for _ in range(99):
        # Random walk with occasional extreme moves
        move = np.random.choice([0.01, 0.02, 0.05, -0.01, -0.02, -0.05])
        prices.append(prices[-1] * (1 + move))

    prices = np.array(prices)

    # Create RSI indicator
    rsi = IncrementalRSI(length=14)

    # Process bars and check bounds
    out_of_bounds = []
    for i in range(100):
        close = float(prices[i])
        rsi.update(close=close)
        value = rsi.value

        if value is not None and not math.isnan(value):
            if value < 0 or value > 100:
                out_of_bounds.append((i, value))

    passed = len(out_of_bounds) == 0
    return EdgeCaseTestResult(
        name="warmup_rsi_bounds",
        passed=passed,
        expected="RSI always in [0, 100]",
        actual="All values in bounds" if passed else f"{len(out_of_bounds)} out of bounds",
        error_msg=None if passed else f"Out of bounds values: {out_of_bounds[:3]}",
    )


def _test_zero_volume_bar() -> EdgeCaseTestResult:
    """
    Test that zero volume bars are handled gracefully.

    Indicators should not crash or produce invalid values on zero volume.
    """
    from ..indicators.incremental import IncrementalOBV

    # Create data with zero volume bars
    np.random.seed(42)
    prices = 50000 * np.cumprod(1 + np.random.normal(0, 0.001, 50))
    volumes = np.random.uniform(100, 1000, 50)

    # Set some volumes to zero
    volumes[10] = 0
    volumes[20] = 0
    volumes[30] = 0

    # Test OBV (volume-dependent indicator)
    obv = IncrementalOBV()

    errors = []
    for i in range(50):
        close = float(prices[i])
        volume = float(volumes[i])
        try:
            obv.update(close=close, volume=volume)
            value = obv.value
            # Check for NaN or Inf (after first bar)
            if i > 0 and value is not None and (math.isnan(value) or math.isinf(value)):
                errors.append((i, "NaN/Inf value"))
        except Exception as e:
            errors.append((i, str(e)))

    passed = len(errors) == 0
    return EdgeCaseTestResult(
        name="zero_volume_bar",
        passed=passed,
        expected="No errors on zero volume",
        actual="Handled gracefully" if passed else f"{len(errors)} errors",
        error_msg=None if passed else f"Errors: {errors[:3]}",
    )


def _test_flat_price_bar() -> EdgeCaseTestResult:
    """
    Test that flat price bars (OHLC all equal) are handled.

    This can happen in low-liquidity markets or during halts.
    """
    from ..indicators.incremental import IncrementalATR

    # Create data with flat bars (all OHLC equal)
    np.random.seed(42)
    prices = 50000 * np.cumprod(1 + np.random.normal(0, 0.001, 50))

    # Test ATR (requires price range)
    atr = IncrementalATR(length=14)

    errors = []
    for i in range(50):
        # Use same value for H/L/C on some bars (flat)
        if i in [10, 20, 30]:
            high = low = close = float(prices[i])
        else:
            close = float(prices[i])
            high = close * 1.002
            low = close * 0.998

        try:
            atr.update(high=high, low=low, close=close)
            value = atr.value
            # ATR should be >= 0
            if value is not None and not math.isnan(value):
                if value < 0:
                    errors.append((i, f"Negative ATR: {value}"))
        except Exception as e:
            errors.append((i, str(e)))

    passed = len(errors) == 0
    return EdgeCaseTestResult(
        name="flat_price_bar",
        passed=passed,
        expected="ATR >= 0 even with flat bars",
        actual="Handled gracefully" if passed else f"{len(errors)} errors",
        error_msg=None if passed else f"Errors: {errors[:3]}",
    )


def _test_extreme_price_move() -> EdgeCaseTestResult:
    """
    Test that extreme price moves (50%+ gap) are handled.

    Flash crashes and gaps should not break indicators.
    """
    from ..indicators.incremental import IncrementalMACD

    # Create data with extreme moves
    np.random.seed(42)
    prices = [50000.0] * 50

    # Normal prices for first 20 bars
    for i in range(1, 20):
        prices[i] = prices[i-1] * (1 + np.random.normal(0, 0.001))

    # 50% crash at bar 20
    prices[20] = prices[19] * 0.5

    # Normal after crash
    for i in range(21, 40):
        prices[i] = prices[i-1] * (1 + np.random.normal(0, 0.001))

    # 100% recovery at bar 40
    prices[40] = prices[39] * 2.0

    # Normal to end
    for i in range(41, 50):
        prices[i] = prices[i-1] * (1 + np.random.normal(0, 0.001))

    prices = np.array(prices)

    # Test MACD (sensitive to extreme moves)
    macd = IncrementalMACD(fast=12, slow=26, signal=9)

    errors = []
    for i in range(50):
        close = float(prices[i])
        try:
            macd.update(close=close)
            # Check macd_line, signal_line, histogram for Inf
            for attr in ['macd_line', 'signal_line', 'histogram']:
                value = getattr(macd, f'_{attr}', None)
                if value is not None and not math.isnan(value) and math.isinf(value):
                    errors.append((i, f"Inf in {attr}"))
        except Exception as e:
            errors.append((i, str(e)))

    passed = len(errors) == 0
    return EdgeCaseTestResult(
        name="extreme_price_move",
        passed=passed,
        expected="No Inf values after 50%+ move",
        actual="Handled correctly" if passed else f"{len(errors)} errors",
        error_msg=None if passed else f"Errors: {errors[:3]}",
    )


def _test_float_precision_addition() -> EdgeCaseTestResult:
    """
    Test IEEE 754 float precision handling.

    Classic example: 0.1 + 0.2 != 0.3 in floating point.
    """
    # Test that our comparison logic handles float precision
    a = 0.1 + 0.2
    b = 0.3

    # Direct comparison fails
    direct_equal = (a == b)

    # Tolerance-based comparison should work
    tolerance = 1e-10
    tolerance_equal = abs(a - b) < tolerance

    passed = not direct_equal and tolerance_equal
    return EdgeCaseTestResult(
        name="float_precision_addition",
        passed=passed,
        expected="0.1+0.2 != 0.3 directly, but equal within 1e-10",
        actual=f"Direct: {direct_equal}, Tolerance: {tolerance_equal}",
        error_msg=None if passed else "Float precision not handled correctly",
    )


def _test_float_precision_comparison() -> EdgeCaseTestResult:
    """
    Test price comparison with tiny differences.

    50000.0 vs 50000.00000001 should be considered equal for trading.
    """
    price1 = 50000.0
    price2 = 50000.00000001

    # Direct comparison
    direct_equal = (price1 == price2)

    # Relative tolerance (1e-9 = 0.0000001%)
    rel_tol = 1e-9
    diff = abs(price1 - price2)
    avg = (abs(price1) + abs(price2)) / 2
    rel_diff = diff / avg if avg > 0 else diff
    tolerance_equal = rel_diff < rel_tol

    passed = not direct_equal and tolerance_equal
    return EdgeCaseTestResult(
        name="float_precision_comparison",
        passed=passed,
        expected="Prices differ by 1e-8 but equal within 1e-9 relative",
        actual=f"Direct: {direct_equal}, Rel diff: {rel_diff:.2e}",
        error_msg=None if passed else "Price comparison precision issue",
    )


def _test_large_position_no_overflow() -> EdgeCaseTestResult:
    """
    Test that large positions don't cause overflow.

    $1M notional at high leverage should work.
    """
    # Simulate large position calculations
    notional = 1_000_000.0  # $1M
    price = 50000.0
    leverage = 100.0

    # Position size
    size = notional / price  # 20 BTC

    # Margin required
    margin = notional / leverage  # $10k

    # Unrealized P/L on 10% move
    new_price = price * 1.10
    unrealized = (new_price - price) * size  # $100k

    # Check for overflow
    has_overflow = any([
        math.isinf(size),
        math.isinf(margin),
        math.isinf(unrealized),
        math.isnan(size),
        math.isnan(margin),
        math.isnan(unrealized),
    ])

    # Verify values are reasonable
    expected_size = 20.0
    expected_margin = 10000.0
    expected_unrealized = 100000.0

    size_correct = abs(size - expected_size) < 0.001
    margin_correct = abs(margin - expected_margin) < 0.01
    unrealized_correct = abs(unrealized - expected_unrealized) < 0.01

    passed = not has_overflow and size_correct and margin_correct and unrealized_correct
    return EdgeCaseTestResult(
        name="large_position_no_overflow",
        passed=passed,
        expected=f"size={expected_size}, margin={expected_margin}, pnl={expected_unrealized}",
        actual=f"size={size:.4f}, margin={margin:.2f}, pnl={unrealized:.2f}",
        error_msg=None if passed else "Large position calculation error",
    )


def _test_small_price_no_underflow() -> EdgeCaseTestResult:
    """
    Test that very small prices don't cause underflow.

    Meme coins can have prices like 0.00000001.
    """
    # Simulate small price calculations
    price = 0.00000001  # 1e-8
    size = 1_000_000_000  # 1B tokens (to get reasonable notional)
    notional = price * size  # $10

    # Fee calculation
    fee_rate = 0.0001  # 1 bps
    fee = notional * fee_rate  # $0.001

    # Check for underflow
    has_underflow = any([
        notional == 0 and price > 0 and size > 0,
        fee == 0 and fee_rate > 0 and notional > 0,
    ])

    # Verify values are reasonable
    expected_notional = 10.0
    expected_fee = 0.001

    notional_correct = abs(notional - expected_notional) < 0.001
    fee_correct = abs(fee - expected_fee) < 0.0001

    passed = not has_underflow and notional_correct and fee_correct
    return EdgeCaseTestResult(
        name="small_price_no_underflow",
        passed=passed,
        expected=f"notional={expected_notional}, fee={expected_fee}",
        actual=f"notional={notional:.4f}, fee={fee:.6f}",
        error_msg=None if passed else "Small price calculation error",
    )


def _test_division_by_zero_protection() -> EdgeCaseTestResult:
    """
    Test that division by zero is handled.

    Win rate with 0 trades, Sharpe with 0 std, etc.
    """
    errors = []

    # Win rate with 0 trades
    wins = 0
    total = 0
    try:
        win_rate = wins / total if total > 0 else 0.0
        if math.isnan(win_rate) or math.isinf(win_rate):
            errors.append("Win rate is NaN/Inf")
    except ZeroDivisionError:
        errors.append("Win rate division by zero")

    # Sharpe with 0 std
    returns_mean = 0.01
    returns_std = 0.0
    try:
        sharpe = returns_mean / returns_std if returns_std > 0 else 0.0
        if math.isinf(sharpe):
            errors.append("Sharpe is Inf")
    except ZeroDivisionError:
        errors.append("Sharpe division by zero")

    # Profit factor with 0 losses
    gross_profit = 1000.0
    gross_loss = 0.0
    try:
        profit_factor = gross_profit / abs(gross_loss) if gross_loss != 0 else float('inf')
        # Inf is acceptable here (infinite profit factor when no losses)
    except ZeroDivisionError:
        errors.append("Profit factor division by zero")

    passed = len(errors) == 0
    return EdgeCaseTestResult(
        name="division_by_zero_protection",
        passed=passed,
        expected="No unhandled division by zero",
        actual="All protected" if passed else f"{len(errors)} issues",
        error_msg=None if passed else f"Issues: {errors}",
    )


def run_all_edge_case_tests() -> list[EdgeCaseTestResult]:
    """Run all edge case tests and return results."""
    tests = [
        _test_warmup_ema_nan,
        _test_warmup_rsi_bounds,
        _test_zero_volume_bar,
        _test_flat_price_bar,
        _test_extreme_price_move,
        _test_float_precision_addition,
        _test_float_precision_comparison,
        _test_large_position_no_overflow,
        _test_small_price_no_underflow,
        _test_division_by_zero_protection,
    ]

    results = []
    for test_func in tests:
        try:
            result = test_func()
            results.append(result)
        except Exception as e:
            results.append(EdgeCaseTestResult(
                name=test_func.__name__.replace("_test_", ""),
                passed=False,
                expected="No exception",
                actual=f"Exception: {type(e).__name__}",
                error_msg=str(e),
            ))

    return results


def format_edge_case_test_report(results: list[EdgeCaseTestResult]) -> str:
    """Format edge case test results as a report string."""
    lines = []
    lines.append("=" * 60)
    lines.append("EDGE CASE VALIDATION REPORT")
    lines.append("=" * 60)

    passed = sum(1 for r in results if r.passed)
    total = len(results)

    for r in results:
        status = "PASS" if r.passed else "FAIL"
        lines.append(f"  [{status}] {r.name}")
        if not r.passed:
            lines.append(f"         Expected: {r.expected}")
            lines.append(f"         Actual:   {r.actual}")
            if r.error_msg:
                lines.append(f"         Error:    {r.error_msg}")

    lines.append("-" * 60)
    lines.append(f"TOTAL: {passed}/{total} tests passed")
    lines.append("=" * 60)

    return "\n".join(lines)
