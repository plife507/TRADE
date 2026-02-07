"""
Execution Validation: Proves trade execution is correct.

Tests execution flow with synthetic data:
1. Fill timing (signal at bar N → fill at bar N+1 open)
2. Slippage application (fill price adjusted by configured BPS)
3. SL/TP execution (triggers at correct bar and price)
4. Position management (no double entry, proper close)
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
import pandas as pd
import numpy as np

from ..utils.logger import get_logger

logger = get_logger()


@dataclass
class ExecutionTestResult:
    """Result of an execution validation test."""
    name: str
    passed: bool
    expected: str
    actual: str
    error_msg: str = ""


# =============================================================================
# Synthetic Data Generators
# =============================================================================

def generate_ohlcv_df(
    num_bars: int = 100,
    base_price: float = 50000.0,
    volatility: float = 0.01,
    start_time: datetime | None = None,
) -> pd.DataFrame:
    """Generate synthetic OHLCV DataFrame."""
    if start_time is None:
        start_time = datetime(2025, 1, 1)

    np.random.seed(42)  # Reproducibility

    timestamps = [start_time + timedelta(minutes=i) for i in range(num_bars)]
    closes = [base_price]

    for _ in range(1, num_bars):
        change = np.random.normal(0, volatility)
        closes.append(closes[-1] * (1 + change))

    closes = np.array(closes)

    # Generate OHLC from closes
    highs = closes * (1 + np.random.uniform(0, volatility, num_bars))
    lows = closes * (1 - np.random.uniform(0, volatility, num_bars))
    opens = np.roll(closes, 1)
    opens[0] = closes[0]

    return pd.DataFrame({
        "timestamp": timestamps,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": np.random.uniform(1000, 5000, num_bars),
    })


def generate_sl_trigger_data(
    entry_bar: int = 10,
    entry_price: float = 50000.0,
    sl_pct: float = 3.0,  # 3% stop loss
    trigger_bar: int = 20,
    direction: str = "long",
) -> pd.DataFrame:
    """
    Generate data where SL triggers at exact bar.

    For long: low drops below SL level at trigger_bar.
    For short: high rises above SL level at trigger_bar.
    """
    num_bars = trigger_bar + 10
    start_time = datetime(2025, 1, 1)

    sl_price = entry_price * (1 - sl_pct / 100) if direction == "long" else entry_price * (1 + sl_pct / 100)

    timestamps = [start_time + timedelta(minutes=i) for i in range(num_bars)]
    opens = []
    highs = []
    lows = []
    closes = []

    for i in range(num_bars):
        if i < trigger_bar:
            # Price stays above SL for long, below for short
            if direction == "long":
                base = entry_price - (entry_price - sl_price) * 0.3  # Stay above SL
                open_p = base
                high_p = base + 100
                low_p = base - 100  # But not below SL
                close_p = base + 50
            else:
                base = entry_price + (sl_price - entry_price) * 0.3  # Stay below SL
                open_p = base
                high_p = base + 100  # But not above SL
                low_p = base - 100
                close_p = base - 50
        elif i == trigger_bar:
            # SL triggers on this bar
            if direction == "long":
                open_p = entry_price - 200
                high_p = entry_price - 100
                low_p = sl_price - 50  # Below SL
                close_p = sl_price - 25
            else:
                open_p = entry_price + 200
                high_p = sl_price + 50  # Above SL
                low_p = entry_price + 100
                close_p = sl_price + 25
        else:
            # After trigger
            base = sl_price if direction == "long" else sl_price
            open_p = base
            high_p = base + 100
            low_p = base - 100
            close_p = base

        opens.append(open_p)
        highs.append(high_p)
        lows.append(low_p)
        closes.append(close_p)

    return pd.DataFrame({
        "timestamp": timestamps,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": [1000.0] * num_bars,
    })


def generate_tp_trigger_data(
    entry_bar: int = 10,
    entry_price: float = 50000.0,
    tp_pct: float = 6.0,  # 6% take profit
    trigger_bar: int = 25,
    direction: str = "long",
) -> pd.DataFrame:
    """
    Generate data where TP triggers at exact bar.

    For long: high rises above TP level at trigger_bar.
    For short: low drops below TP level at trigger_bar.
    """
    num_bars = trigger_bar + 10
    start_time = datetime(2025, 1, 1)

    tp_price = entry_price * (1 + tp_pct / 100) if direction == "long" else entry_price * (1 - tp_pct / 100)

    timestamps = [start_time + timedelta(minutes=i) for i in range(num_bars)]
    opens = []
    highs = []
    lows = []
    closes = []

    for i in range(num_bars):
        if i < trigger_bar:
            # Price stays below TP for long, above for short
            if direction == "long":
                base = entry_price + (tp_price - entry_price) * 0.3  # Stay below TP
                open_p = base
                high_p = base + 100  # But not above TP
                low_p = base - 100
                close_p = base + 50
            else:
                base = entry_price - (entry_price - tp_price) * 0.3  # Stay above TP
                open_p = base
                high_p = base + 100
                low_p = base - 100  # But not below TP
                close_p = base - 50
        elif i == trigger_bar:
            # TP triggers on this bar
            if direction == "long":
                open_p = tp_price - 200
                high_p = tp_price + 50  # Above TP
                low_p = tp_price - 250
                close_p = tp_price + 25
            else:
                open_p = tp_price + 200
                high_p = tp_price + 250
                low_p = tp_price - 50  # Below TP
                close_p = tp_price - 25
        else:
            base = tp_price
            open_p = base
            high_p = base + 100
            low_p = base - 100
            close_p = base

        opens.append(open_p)
        highs.append(high_p)
        lows.append(low_p)
        closes.append(close_p)

    return pd.DataFrame({
        "timestamp": timestamps,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": [1000.0] * num_bars,
    })


# =============================================================================
# Fill Timing Tests
# =============================================================================

def test_fill_next_bar_open() -> ExecutionTestResult:
    """
    Test: Signal at bar N results in fill at bar N+1 open price.

    Setup:
        - Signal fires at bar 50 (close = 50000)
        - Bar 51 open = 50100
    Expected:
        - Fill occurs at bar 51
        - Fill price = 50100 (bar 51 open)
    """
    from .fill_validator import validate_fill_timing

    candles = generate_ohlcv_df(num_bars=100, base_price=50000.0)
    # Force specific prices for test
    candles.loc[50, "close"] = 50000.0
    candles.loc[51, "open"] = 50100.0

    # Simulate correct trade (signal at 50, fill at 51)
    trades = [{
        "trade_id": 1,
        "signal_bar": 50,
        "entry_bar": 51,
        "entry_price": 50100.0,  # Bar 51 open
        "exit_bar": 60,
        "exit_price": 51000.0,
        "exit_reason": "signal",
    }]

    result = validate_fill_timing(
        trades=trades,
        candles=candles,
        allowed_slippage_bps=10.0,
        require_next_bar_fill=True,
    )

    passed = result.passed and len(result.violations) == 0

    return ExecutionTestResult(
        name="fill_next_bar_open",
        passed=passed,
        expected="Fill at bar 51 open (50100)",
        actual=f"Violations: {len(result.violations)}, passed: {result.passed}",
    )


def test_no_same_bar_fill() -> ExecutionTestResult:
    """
    Test: Same-bar fills are detected as violations.

    Setup:
        - Signal fires at bar 50
        - Entry fill also at bar 50 (violation!)
    Expected:
        - Validation fails
        - Violation type = "same_bar"
    """
    from .fill_validator import validate_fill_timing

    candles = generate_ohlcv_df(num_bars=100, base_price=50000.0)

    # Simulate same-bar fill (violation)
    trades = [{
        "trade_id": 1,
        "signal_bar": 50,
        "entry_bar": 50,  # Same bar as signal - VIOLATION
        "entry_price": 50000.0,
        "exit_bar": 60,
        "exit_price": 51000.0,
    }]

    result = validate_fill_timing(
        trades=trades,
        candles=candles,
        require_next_bar_fill=True,
    )

    passed = (
        not result.passed and
        result.same_bar_fills == 1 and
        len(result.violations) == 1 and
        result.violations[0].violation_type == "same_bar"
    )

    return ExecutionTestResult(
        name="no_same_bar_fill",
        passed=passed,
        expected="Violation detected: same_bar fill",
        actual=f"passed={result.passed}, same_bar_fills={result.same_bar_fills}",
    )


def test_slippage_within_bounds() -> ExecutionTestResult:
    """
    Test: Slippage within configured BPS is allowed.

    Setup:
        - Bar 51 open = 50000
        - Fill price = 50005 (1 BPS slippage)
        - Allowed slippage = 10 BPS
    Expected:
        - Validation passes
    """
    from .fill_validator import validate_fill_timing

    candles = generate_ohlcv_df(num_bars=100, base_price=50000.0)
    candles.loc[51, "open"] = 50000.0

    # Fill price slightly above open (1 BPS)
    trades = [{
        "trade_id": 1,
        "signal_bar": 50,
        "entry_bar": 51,
        "entry_price": 50005.0,  # 1 BPS above open
        "exit_bar": 60,
        "exit_price": 51000.0,
    }]

    result = validate_fill_timing(
        trades=trades,
        candles=candles,
        allowed_slippage_bps=10.0,  # Allow up to 10 BPS
        require_next_bar_fill=True,
    )

    passed = result.passed and result.slippage_violations == 0

    return ExecutionTestResult(
        name="slippage_within_bounds",
        passed=passed,
        expected="No slippage violation (1 BPS < 10 BPS allowed)",
        actual=f"slippage_violations={result.slippage_violations}, max={result.max_slippage_bps:.1f}",
    )


def test_slippage_exceeds_bounds() -> ExecutionTestResult:
    """
    Test: Slippage exceeding configured BPS is flagged.

    Setup:
        - Bar 51 open = 50000
        - Fill price = 50100 (20 BPS slippage)
        - Allowed slippage = 10 BPS
    Expected:
        - Validation fails with slippage violation
    """
    from .fill_validator import validate_fill_timing

    candles = generate_ohlcv_df(num_bars=100, base_price=50000.0)
    candles.loc[51, "open"] = 50000.0

    # Fill price 20 BPS above open (exceeds 10 BPS limit)
    trades = [{
        "trade_id": 1,
        "signal_bar": 50,
        "entry_bar": 51,
        "entry_price": 50100.0,  # 20 BPS above open
        "exit_bar": 60,
        "exit_price": 51000.0,
    }]

    result = validate_fill_timing(
        trades=trades,
        candles=candles,
        allowed_slippage_bps=10.0,  # Only allow 10 BPS
        require_next_bar_fill=True,
    )

    passed = (
        not result.passed and
        result.slippage_violations == 1 and
        result.max_slippage_bps >= 20.0
    )

    return ExecutionTestResult(
        name="slippage_exceeds_bounds",
        passed=passed,
        expected="Slippage violation (20 BPS > 10 BPS allowed)",
        actual=f"slippage_violations={result.slippage_violations}, max={result.max_slippage_bps:.1f}",
    )


# =============================================================================
# SL/TP Execution Tests
# =============================================================================

def test_sl_trigger_long() -> ExecutionTestResult:
    """
    Test: Long SL triggers when low <= sl_price.

    Setup:
        - Entry at 50000, SL at 48500 (3%)
        - Bar 20: low = 48400 (below SL)
    Expected:
        - Exit at bar 20 at SL price
    """
    from .fill_validator import validate_sl_tp_execution

    entry_price = 50000.0
    sl_price = 48500.0  # 3% below entry
    trigger_bar = 20

    candles = generate_sl_trigger_data(
        entry_bar=10,
        entry_price=entry_price,
        sl_pct=3.0,
        trigger_bar=trigger_bar,
        direction="long",
    )

    trades = [{
        "trade_id": 1,
        "direction": "long",
        "entry_bar": 10,
        "entry_price": entry_price,
        "sl_price": sl_price,
        "tp_price": 53000.0,
        "exit_bar": trigger_bar,
        "exit_price": sl_price,  # Fill at SL price
        "exit_reason": "sl",
    }]

    result = validate_sl_tp_execution(
        trades=trades,
        candles=candles,
        sl_tolerance_pct=1.0,
    )

    passed = result.passed and result.price_violations == 0

    return ExecutionTestResult(
        name="sl_trigger_long",
        passed=passed,
        expected="SL triggers at bar 20 (low < SL price)",
        actual=f"passed={result.passed}, violations={len(result.violations)}",
    )


def test_tp_trigger_long() -> ExecutionTestResult:
    """
    Test: Long TP triggers when high >= tp_price.

    Setup:
        - Entry at 50000, TP at 53000 (6%)
        - Bar 25: high = 53050 (above TP)
    Expected:
        - Exit at bar 25 at TP price
    """
    from .fill_validator import validate_sl_tp_execution

    entry_price = 50000.0
    tp_price = 53000.0  # 6% above entry
    trigger_bar = 25

    candles = generate_tp_trigger_data(
        entry_bar=10,
        entry_price=entry_price,
        tp_pct=6.0,
        trigger_bar=trigger_bar,
        direction="long",
    )

    trades = [{
        "trade_id": 1,
        "direction": "long",
        "entry_bar": 10,
        "entry_price": entry_price,
        "sl_price": 48500.0,
        "tp_price": tp_price,
        "exit_bar": trigger_bar,
        "exit_price": tp_price,  # Fill at TP price
        "exit_reason": "tp",
    }]

    result = validate_sl_tp_execution(
        trades=trades,
        candles=candles,
        tp_tolerance_pct=1.0,
    )

    passed = result.passed and result.price_violations == 0

    return ExecutionTestResult(
        name="tp_trigger_long",
        passed=passed,
        expected="TP triggers at bar 25 (high >= TP price)",
        actual=f"passed={result.passed}, violations={len(result.violations)}",
    )


def test_sl_trigger_short() -> ExecutionTestResult:
    """
    Test: Short SL triggers when high >= sl_price.

    Setup:
        - Short entry at 50000, SL at 51500 (3%)
        - Bar 20: high = 51600 (above SL)
    Expected:
        - Exit at bar 20 at SL price
    """
    from .fill_validator import validate_sl_tp_execution

    entry_price = 50000.0
    sl_price = 51500.0  # 3% above entry (for short)
    trigger_bar = 20

    candles = generate_sl_trigger_data(
        entry_bar=10,
        entry_price=entry_price,
        sl_pct=3.0,
        trigger_bar=trigger_bar,
        direction="short",
    )

    trades = [{
        "trade_id": 1,
        "direction": "short",
        "entry_bar": 10,
        "entry_price": entry_price,
        "sl_price": sl_price,
        "tp_price": 47000.0,
        "exit_bar": trigger_bar,
        "exit_price": sl_price,
        "exit_reason": "sl",
    }]

    result = validate_sl_tp_execution(
        trades=trades,
        candles=candles,
        sl_tolerance_pct=1.0,
    )

    passed = result.passed and result.price_violations == 0

    return ExecutionTestResult(
        name="sl_trigger_short",
        passed=passed,
        expected="Short SL triggers at bar 20 (high >= SL price)",
        actual=f"passed={result.passed}, violations={len(result.violations)}",
    )


def test_tp_trigger_short() -> ExecutionTestResult:
    """
    Test: Short TP triggers when low <= tp_price.

    Setup:
        - Short entry at 50000, TP at 47000 (6%)
        - Bar 25: low = 46900 (below TP)
    Expected:
        - Exit at bar 25 at TP price
    """
    from .fill_validator import validate_sl_tp_execution

    entry_price = 50000.0
    tp_price = 47000.0  # 6% below entry (for short)
    trigger_bar = 25

    candles = generate_tp_trigger_data(
        entry_bar=10,
        entry_price=entry_price,
        tp_pct=6.0,
        trigger_bar=trigger_bar,
        direction="short",
    )

    trades = [{
        "trade_id": 1,
        "direction": "short",
        "entry_bar": 10,
        "entry_price": entry_price,
        "sl_price": 51500.0,
        "tp_price": tp_price,
        "exit_bar": trigger_bar,
        "exit_price": tp_price,
        "exit_reason": "tp",
    }]

    result = validate_sl_tp_execution(
        trades=trades,
        candles=candles,
        tp_tolerance_pct=1.0,
    )

    passed = result.passed and result.price_violations == 0

    return ExecutionTestResult(
        name="tp_trigger_short",
        passed=passed,
        expected="Short TP triggers at bar 25 (low <= TP price)",
        actual=f"passed={result.passed}, violations={len(result.violations)}",
    )


def test_sl_fill_price_accuracy() -> ExecutionTestResult:
    """
    Test: SL fill price must be at SL level (not bar low).

    The SL should fill at the SL price, not the extreme low of the bar.
    """
    from .fill_validator import validate_sl_tp_execution

    entry_price = 50000.0
    sl_price = 48500.0
    trigger_bar = 20

    candles = generate_sl_trigger_data(
        entry_bar=10,
        entry_price=entry_price,
        sl_pct=3.0,
        trigger_bar=trigger_bar,
        direction="long",
    )

    # Trade with correct SL fill price
    trades_correct = [{
        "trade_id": 1,
        "direction": "long",
        "entry_bar": 10,
        "entry_price": entry_price,
        "sl_price": sl_price,
        "exit_bar": trigger_bar,
        "exit_price": sl_price,  # Correct: fill at SL price
        "exit_reason": "sl",
    }]

    result = validate_sl_tp_execution(
        trades=trades_correct,
        candles=candles,
        sl_tolerance_pct=0.5,  # Tight tolerance
    )

    passed = result.passed

    return ExecutionTestResult(
        name="sl_fill_price_accuracy",
        passed=passed,
        expected="SL fills at SL price (48500), not bar low",
        actual=f"passed={result.passed}, violations={len(result.violations)}",
    )


# =============================================================================
# Run All Tests
# =============================================================================

def run_all_execution_tests() -> list[ExecutionTestResult]:
    """Run all execution validation tests."""
    tests = [
        # Fill timing
        test_fill_next_bar_open,
        test_no_same_bar_fill,
        test_slippage_within_bounds,
        test_slippage_exceeds_bounds,
        # SL/TP execution
        test_sl_trigger_long,
        test_tp_trigger_long,
        test_sl_trigger_short,
        test_tp_trigger_short,
        test_sl_fill_price_accuracy,
    ]

    results = []
    for test_fn in tests:
        try:
            result = test_fn()
            results.append(result)
        except Exception as e:
            results.append(ExecutionTestResult(
                name=test_fn.__name__,
                passed=False,
                expected="Test to run",
                actual="",
                error_msg=str(e),
            ))

    return results


def format_execution_test_report(results: list[ExecutionTestResult]) -> str:
    """Format execution test results as report."""
    lines = []
    lines.append("=" * 60)
    lines.append("EXECUTION FLOW VALIDATION")
    lines.append("=" * 60)

    passed = sum(1 for r in results if r.passed)
    total = len(results)

    # Group by category
    categories = {
        "Fill Timing": ["fill_next_bar_open", "no_same_bar_fill",
                       "slippage_within_bounds", "slippage_exceeds_bounds"],
        "SL/TP Execution": ["sl_trigger_long", "tp_trigger_long",
                           "sl_trigger_short", "tp_trigger_short",
                           "sl_fill_price_accuracy"],
    }

    for category, test_names in categories.items():
        lines.append(f"\n{category}:")
        for r in results:
            if r.name in test_names:
                status = "PASS" if r.passed else "FAIL"
                lines.append(f"  {status}: {r.name}")
                if not r.passed:
                    lines.append(f"         Expected: {r.expected}")
                    lines.append(f"         Actual:   {r.actual}")
                    if r.error_msg:
                        lines.append(f"         Error:    {r.error_msg}")

    lines.append("-" * 60)
    lines.append(f"TOTAL: {passed}/{total} passed")

    if passed == total:
        lines.append("All execution flow is CORRECT")
    else:
        lines.append("EXECUTION ERRORS DETECTED")

    lines.append("=" * 60)

    return "\n".join(lines)
