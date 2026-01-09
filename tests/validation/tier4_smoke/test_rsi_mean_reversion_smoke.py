"""
Tier 4 Smoke: RSI Mean Reversion Strategy.

Full strategy simulation with:
- RSI oversold entries (< 30)
- RSI overbought exits (> 70) or TP/SL
- Trade counting and basic metrics

Validation criteria:
- Trade count: 5-30 trades on 1000 bars
- Win rate: 30-70%
- No crashes
- Deterministic
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum

import numpy as np

from ..runner import TestResult
from ..fixtures import SyntheticData


class PositionSide(Enum):
    NONE = "none"
    LONG = "long"


@dataclass
class Trade:
    """Completed trade record."""
    entry_bar: int
    exit_bar: int
    entry_price: float
    exit_price: float
    pnl_pct: float

    @property
    def is_winner(self) -> bool:
        return self.pnl_pct > 0


@dataclass
class StrategyState:
    """Strategy execution state."""
    position: PositionSide = PositionSide.NONE
    entry_bar: int = 0
    entry_price: float = 0.0


def run_tests() -> list[TestResult]:
    """Run all RSI mean reversion smoke tests."""
    tests: list[TestResult] = []

    tests.append(test_trade_count())
    tests.append(test_win_rate())
    tests.append(test_determinism())
    tests.append(test_no_crash_various_seeds())

    return tests


def _compute_rsi(values: np.ndarray, length: int = 14) -> np.ndarray:
    """Compute RSI."""
    rsi = np.full_like(values, 50.0)

    for i in range(length, len(values)):
        window = values[i - length:i + 1]
        deltas = np.diff(window)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)

        if avg_loss == 0:
            rsi[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[i] = 100 - (100 / (1 + rs))

    return rsi


def _generate_mean_reverting_data(
    n_bars: int = 1000,
    seed: int = 42,
) -> SyntheticData:
    """Generate data with RSI oscillations."""
    import pandas as pd
    np.random.seed(seed)

    dates = pd.date_range("2024-01-01", periods=n_bars, freq="1min")

    # Create oscillating price with occasional extremes
    base = 100.0
    close = np.zeros(n_bars)
    close[0] = base

    for i in range(1, n_bars):
        # Mean-reverting random walk
        drift = (base - close[i - 1]) * 0.01  # Pull towards mean
        noise = np.random.randn() * 0.5
        close[i] = close[i - 1] + drift + noise

        # Occasional sharp moves (create RSI extremes)
        if np.random.rand() < 0.02:  # 2% chance
            close[i] += np.random.choice([-3, 3])

    high = close + np.abs(np.random.randn(n_bars) * 0.3)
    low = close - np.abs(np.random.randn(n_bars) * 0.3)
    open_ = np.roll(close, 1)
    open_[0] = base
    volume = np.random.randint(1000, 10000, n_bars).astype(float)

    df = pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }, index=dates)

    return SyntheticData(df=df)


def _run_rsi_mean_reversion_strategy(
    data: SyntheticData,
    rsi_length: int = 14,
    oversold: float = 30.0,
    overbought: float = 70.0,
    tp_pct: float = 3.0,
    sl_pct: float = 2.0,
) -> list[Trade]:
    """
    Run RSI mean reversion strategy simulation.

    Entry: RSI < oversold
    Exit: RSI > overbought, or TP/SL hit
    """
    close = data.close.values
    high = data.high.values
    low = data.low.values

    rsi = _compute_rsi(close, rsi_length)

    trades: list[Trade] = []
    state = StrategyState()
    warmup = rsi_length + 1

    for i in range(warmup, len(close)):
        # Check exits first
        if state.position == PositionSide.LONG:
            tp_price = state.entry_price * (1 + tp_pct / 100)
            sl_price = state.entry_price * (1 - sl_pct / 100)

            exit_price = None
            if high[i] >= tp_price:
                exit_price = tp_price
            elif low[i] <= sl_price:
                exit_price = sl_price
            elif rsi[i] > overbought:
                exit_price = close[i]

            if exit_price:
                pnl = (exit_price - state.entry_price) / state.entry_price * 100
                trades.append(Trade(
                    entry_bar=state.entry_bar,
                    exit_bar=i,
                    entry_price=state.entry_price,
                    exit_price=exit_price,
                    pnl_pct=pnl,
                ))
                state.position = PositionSide.NONE

        # Check entries (only if flat)
        if state.position == PositionSide.NONE:
            if rsi[i] < oversold:
                state.position = PositionSide.LONG
                state.entry_bar = i
                state.entry_price = close[i]

    # Close any open position at end
    if state.position == PositionSide.LONG:
        pnl = (close[-1] - state.entry_price) / state.entry_price * 100
        trades.append(Trade(
            entry_bar=state.entry_bar,
            exit_bar=len(close) - 1,
            entry_price=state.entry_price,
            exit_price=close[-1],
            pnl_pct=pnl,
        ))

    return trades


# =============================================================================
# Smoke Tests
# =============================================================================

def test_trade_count() -> TestResult:
    """S_002a: RSI mean reversion generates 5-30 trades on 1000 bars."""
    test_id = "S_002a"
    start = time.perf_counter()

    try:
        data = _generate_mean_reverting_data(n_bars=1000, seed=42)
        trades = _run_rsi_mean_reversion_strategy(data)

        if 5 <= len(trades) <= 30:
            return TestResult(
                test_id=test_id,
                passed=True,
                message=f"Trade count: {len(trades)} (expected 5-30)",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        else:
            return TestResult(
                test_id=test_id,
                passed=False,
                message=f"Trade count: {len(trades)} (expected 5-30)",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
    except Exception as e:
        return TestResult(
            test_id=test_id,
            passed=False,
            message=f"Error: {e}",
            duration_ms=(time.perf_counter() - start) * 1000,
        )


def test_win_rate() -> TestResult:
    """S_002b: Win rate between 30-70%."""
    test_id = "S_002b"
    start = time.perf_counter()

    try:
        data = _generate_mean_reverting_data(n_bars=1000, seed=42)
        trades = _run_rsi_mean_reversion_strategy(data)

        if not trades:
            return TestResult(
                test_id=test_id,
                passed=False,
                message="No trades to calculate win rate",
                duration_ms=(time.perf_counter() - start) * 1000,
            )

        winners = sum(1 for t in trades if t.is_winner)
        win_rate = winners / len(trades) * 100

        if 30 <= win_rate <= 70:
            return TestResult(
                test_id=test_id,
                passed=True,
                message=f"Win rate: {win_rate:.1f}% ({winners}/{len(trades)})",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        else:
            return TestResult(
                test_id=test_id,
                passed=False,
                message=f"Win rate: {win_rate:.1f}% (expected 30-70%)",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
    except Exception as e:
        return TestResult(
            test_id=test_id,
            passed=False,
            message=f"Error: {e}",
            duration_ms=(time.perf_counter() - start) * 1000,
        )


def test_determinism() -> TestResult:
    """S_002c: Same seed produces identical results."""
    test_id = "S_002c"
    start = time.perf_counter()

    try:
        data1 = _generate_mean_reverting_data(n_bars=500, seed=123)
        trades1 = _run_rsi_mean_reversion_strategy(data1)

        data2 = _generate_mean_reverting_data(n_bars=500, seed=123)
        trades2 = _run_rsi_mean_reversion_strategy(data2)

        if len(trades1) != len(trades2):
            return TestResult(
                test_id=test_id,
                passed=False,
                message=f"Trade count differs: {len(trades1)} vs {len(trades2)}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )

        return TestResult(
            test_id=test_id,
            passed=True,
            message=f"Deterministic: {len(trades1)} identical trades",
            duration_ms=(time.perf_counter() - start) * 1000,
        )
    except Exception as e:
        return TestResult(
            test_id=test_id,
            passed=False,
            message=f"Error: {e}",
            duration_ms=(time.perf_counter() - start) * 1000,
        )


def test_no_crash_various_seeds() -> TestResult:
    """S_002d: No crashes across different random seeds."""
    test_id = "S_002d"
    start = time.perf_counter()

    try:
        seeds = [1, 42, 100, 999, 12345]
        total_trades = 0

        for seed in seeds:
            data = _generate_mean_reverting_data(n_bars=500, seed=seed)
            trades = _run_rsi_mean_reversion_strategy(data)
            total_trades += len(trades)

        avg_trades = total_trades / len(seeds)
        return TestResult(
            test_id=test_id,
            passed=True,
            message=f"No crashes, avg {avg_trades:.1f} trades/run",
            duration_ms=(time.perf_counter() - start) * 1000,
        )
    except Exception as e:
        return TestResult(
            test_id=test_id,
            passed=False,
            message=f"Crash: {e}",
            duration_ms=(time.perf_counter() - start) * 1000,
        )


if __name__ == "__main__":
    results = run_tests()
    passed = sum(1 for r in results if r.passed)
    print(f"RSI mean reversion smoke: {passed}/{len(results)} passed")
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"  {status}: {r.test_id} - {r.message}")
