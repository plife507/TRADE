"""
Test risk validation plays on real BTC data.

Verifies that max_drawdown_hit and liquidated terminal stops fire
correctly on real market data (not just synthetic patterns).

Uses dedicated real-data (RD) plays with large position sizing
(risk_per_trade_pct=95%) so that normal BTC volatility triggers
the risk events reliably.

Usage:
    python scripts/test_risk_real_data.py
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.backtest.play import load_play
from src.backtest.engine_factory import create_engine_from_play, run_engine_with_play


# Real-data test cases:
# Each tuple: (play_id, window_start, window_end, expected_stop, description)
# All RD plays use risk_per_trade_pct=95 + always-true entry + no exit signal.
REAL_DATA_TESTS = [
    # RD_001: 3x leverage, 95% equity, max_drawdown=5%.
    # A ~1.75% BTC drop triggers 5% drawdown. Happens in any 24h period.
    (
        "V_RISK_RD_001_drawdown_5pct",
        datetime(2025, 1, 10),
        datetime(2025, 2, 1),
        "max_drawdown_hit",
        "3x lev, 95% equity, 5% max drawdown",
    ),
    # RD_002: 3x leverage, 95% equity, max_drawdown=50%.
    # A ~17.5% BTC drop triggers 50% drawdown. Feb 2025: BTC ~$105K → ~$78K.
    (
        "V_RISK_RD_002_drawdown_50pct",
        datetime(2025, 2, 1),
        datetime(2025, 3, 15),
        "max_drawdown_hit",
        "3x lev, 95% equity, 50% max drawdown (Feb-Mar 2025 ~25% BTC drop)",
    ),
    # V_RISK_004: 50x leverage, 95% equity, no SL → any 2% drop liquidates.
    (
        "V_RISK_004_liquidation",
        datetime(2025, 1, 10),
        datetime(2025, 2, 1),
        "liquidated",
        "50x lev, 95% equity, liquidation",
    ),
    # RD_003: Short 3x leverage, 95% equity, max_drawdown=5%.
    # A ~1.75% BTC rally triggers 5% drawdown. Jan 2025: BTC rallied ~$92K→$106K.
    (
        "V_RISK_RD_003_short_drawdown_5pct",
        datetime(2025, 1, 10),
        datetime(2025, 2, 1),
        "max_drawdown_hit",
        "SHORT 3x lev, 95% equity, 5% max drawdown",
    ),
    # RD_004: Short 50x leverage, 95% equity, no SL → any 2% rally liquidates.
    (
        "V_RISK_RD_004_short_liquidation",
        datetime(2025, 1, 10),
        datetime(2025, 2, 1),
        "liquidated",
        "SHORT 50x lev, 95% equity, liquidation",
    ),
]


def run_test(
    play_id: str,
    window_start: datetime,
    window_end: datetime,
    expected_stop: str,
    description: str,
) -> tuple[bool, str]:
    """Run a single real-data risk test. Returns (passed, message)."""
    try:
        play = load_play(play_id)
        engine = create_engine_from_play(
            play,
            window_start=window_start,
            window_end=window_end,
            use_synthetic=False,
            data_env="live",
        )
        result = run_engine_with_play(engine, play)

        stopped = result.stopped_early
        classification = result.stop_classification
        trades_count = len(result.trades) if hasattr(result, 'trades') else 0
        final_equity = result.final_equity

        if stopped and classification == expected_stop:
            return True, (
                f"{classification} after {trades_count} trades "
                f"(final_eq={final_equity:.2f})"
            )
        elif stopped:
            return False, (
                f"WRONG STOP: expected {expected_stop}, got {classification} "
                f"after {trades_count} trades"
            )
        else:
            return False, (
                f"NO STOP: completed {trades_count} trades without terminal event "
                f"(final_eq={final_equity:.2f})"
            )
    except Exception as e:
        return False, f"ERROR: {type(e).__name__}: {e}"


def main() -> None:
    print("=" * 70)
    print("  RISK VALIDATION ON REAL DATA")
    print("=" * 70)
    print()

    results: list[tuple[str, bool, str]] = []

    for play_id, start, end, expected, desc in REAL_DATA_TESTS:
        print(f"[TEST] {play_id}")
        print(f"       {desc}")
        print(f"       Window: {start.date()} -> {end.date()}")
        print(f"       Expected: {expected}")

        passed, msg = run_test(play_id, start, end, expected, desc)
        results.append((play_id, passed, msg))

        status = "PASS" if passed else "FAIL"
        print(f"       [{status}] {msg}")
        print()

    # Summary
    print("=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    passed_count = sum(1 for _, p, _ in results if p)
    total = len(results)
    for play_id, passed, msg in results:
        icon = "OK" if passed else "XX"
        print(f"  [{icon}] {play_id}: {msg}")
    print()
    print(f"  {passed_count}/{total} tests passed")
    print("=" * 70)

    sys.exit(0 if passed_count == total else 1)


if __name__ == "__main__":
    main()
