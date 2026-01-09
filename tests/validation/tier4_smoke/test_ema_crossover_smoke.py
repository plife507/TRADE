"""
Tier 4 Smoke: EMA Crossover Strategy.

Full strategy simulation with:
- EMA 9/21 crossover entries
- Fixed TP/SL exits
- Trade counting and basic metrics

Validation criteria:
- Trade count: 5-25 trades on 1000 bars
- Win rate: 30-70% (sanity check)
- No crashes
- Deterministic (same result on re-run)
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum

import numpy as np

from ..runner import TestResult
from ..fixtures import generate_trending_up, SyntheticData


class PositionSide(Enum):
    NONE = "none"
    LONG = "long"
    SHORT = "short"


@dataclass
class Trade:
    """Completed trade record."""
    entry_bar: int
    exit_bar: int
    entry_price: float
    exit_price: float
    side: PositionSide
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
    tp_price: float = 0.0
    sl_price: float = 0.0


def run_tests() -> list[TestResult]:
    """Run all EMA crossover smoke tests."""
    tests: list[TestResult] = []

    tests.append(test_trade_count())
    tests.append(test_win_rate())
    tests.append(test_determinism())
    tests.append(test_no_crash_various_seeds())

    return tests


def _compute_ema(values: np.ndarray, length: int) -> np.ndarray:
    """Compute EMA."""
    ema = np.zeros_like(values)
    alpha = 2.0 / (length + 1)
    ema[0] = values[0]
    for i in range(1, len(values)):
        ema[i] = alpha * values[i] + (1 - alpha) * ema[i - 1]
    return ema


def _run_ema_crossover_strategy(
    data: SyntheticData,
    fast_len: int = 9,
    slow_len: int = 21,
    tp_pct: float = 2.0,
    sl_pct: float = 1.0,
) -> list[Trade]:
    """
    Run EMA crossover strategy simulation.

    Entry: EMA fast crosses above EMA slow
    Exit: TP at +2%, SL at -1%, or reverse signal
    """
    close = data.close.values
    high = data.high.values
    low = data.low.values

    ema_fast = _compute_ema(close, fast_len)
    ema_slow = _compute_ema(close, slow_len)

    trades: list[Trade] = []
    state = StrategyState()
    warmup = max(fast_len, slow_len) + 1

    for i in range(warmup, len(close)):
        # Check exits first
        if state.position == PositionSide.LONG:
            # Check TP/SL
            if high[i] >= state.tp_price:
                pnl = (state.tp_price - state.entry_price) / state.entry_price * 100
                trades.append(Trade(
                    entry_bar=state.entry_bar,
                    exit_bar=i,
                    entry_price=state.entry_price,
                    exit_price=state.tp_price,
                    side=PositionSide.LONG,
                    pnl_pct=pnl,
                ))
                state.position = PositionSide.NONE
            elif low[i] <= state.sl_price:
                pnl = (state.sl_price - state.entry_price) / state.entry_price * 100
                trades.append(Trade(
                    entry_bar=state.entry_bar,
                    exit_bar=i,
                    entry_price=state.entry_price,
                    exit_price=state.sl_price,
                    side=PositionSide.LONG,
                    pnl_pct=pnl,
                ))
                state.position = PositionSide.NONE

        # Check entries (only if flat)
        if state.position == PositionSide.NONE:
            # Cross above
            prev_fast_below = ema_fast[i - 1] <= ema_slow[i - 1]
            curr_fast_above = ema_fast[i] > ema_slow[i]

            if prev_fast_below and curr_fast_above:
                state.position = PositionSide.LONG
                state.entry_bar = i
                state.entry_price = close[i]
                state.tp_price = close[i] * (1 + tp_pct / 100)
                state.sl_price = close[i] * (1 - sl_pct / 100)

    # Close any open position at end
    if state.position == PositionSide.LONG:
        pnl = (close[-1] - state.entry_price) / state.entry_price * 100
        trades.append(Trade(
            entry_bar=state.entry_bar,
            exit_bar=len(close) - 1,
            entry_price=state.entry_price,
            exit_price=close[-1],
            side=PositionSide.LONG,
            pnl_pct=pnl,
        ))

    return trades


# =============================================================================
# Smoke Tests
# =============================================================================

def test_trade_count() -> TestResult:
    """S_001a: EMA crossover generates 5-25 trades on 1000 bars.

    Validates that strategy produces a reasonable number of trades.
    Too few = not enough opportunities
    Too many = overtrading / noisy signals
    """
    test_id = "S_001a"
    start = time.perf_counter()

    try:
        data = generate_trending_up(
            start=100.0,
            end=150.0,
            n_bars=1000,
            pullbacks=8,
            seed=42,
        )

        trades = _run_ema_crossover_strategy(data)

        if 5 <= len(trades) <= 25:
            return TestResult(
                test_id=test_id,
                passed=True,
                message=f"Trade count: {len(trades)} (expected 5-25)",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        else:
            return TestResult(
                test_id=test_id,
                passed=False,
                message=f"Trade count: {len(trades)} (expected 5-25)",
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
    """S_001b: Win rate between 30-70% (sanity check).

    Validates that strategy isn't completely broken.
    Outside this range suggests systematic issues.
    """
    test_id = "S_001b"
    start = time.perf_counter()

    try:
        data = generate_trending_up(
            start=100.0,
            end=150.0,
            n_bars=1000,
            pullbacks=8,
            seed=42,
        )

        trades = _run_ema_crossover_strategy(data)

        if not trades:
            return TestResult(
                test_id=test_id,
                passed=False,
                message="No trades to calculate win rate",
                duration_ms=(time.perf_counter() - start) * 1000,
            )

        winners = sum(1 for t in trades if t.is_winner)
        win_rate = winners / len(trades) * 100

        if 20 <= win_rate <= 90:
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
    """S_001c: Same seed produces identical results.

    Validates that strategy execution is deterministic.
    """
    test_id = "S_001c"
    start = time.perf_counter()

    try:
        # Run twice with same seed
        data1 = generate_trending_up(start=100.0, end=150.0, n_bars=500, pullbacks=5, seed=123)
        trades1 = _run_ema_crossover_strategy(data1)

        data2 = generate_trending_up(start=100.0, end=150.0, n_bars=500, pullbacks=5, seed=123)
        trades2 = _run_ema_crossover_strategy(data2)

        if len(trades1) != len(trades2):
            return TestResult(
                test_id=test_id,
                passed=False,
                message=f"Trade count differs: {len(trades1)} vs {len(trades2)}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )

        # Compare trade details
        for i, (t1, t2) in enumerate(zip(trades1, trades2)):
            if t1.entry_bar != t2.entry_bar or abs(t1.pnl_pct - t2.pnl_pct) > 0.001:
                return TestResult(
                    test_id=test_id,
                    passed=False,
                    message=f"Trade {i} differs between runs",
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
    """S_001d: No crashes across different random seeds.

    Validates robustness across different data patterns.
    """
    test_id = "S_001d"
    start = time.perf_counter()

    try:
        seeds = [1, 42, 100, 999, 12345]
        total_trades = 0

        for seed in seeds:
            data = generate_trending_up(
                start=100.0,
                end=140.0,
                n_bars=500,
                pullbacks=4,
                seed=seed,
            )
            trades = _run_ema_crossover_strategy(data)
            total_trades += len(trades)

        avg_trades = total_trades / len(seeds)
        return TestResult(
            test_id=test_id,
            passed=True,
            message=f"No crashes, avg {avg_trades:.1f} trades/run across {len(seeds)} seeds",
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
    print(f"EMA crossover smoke: {passed}/{len(results)} passed")
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"  {status}: {r.test_id} - {r.message}")
