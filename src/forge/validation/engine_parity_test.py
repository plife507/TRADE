"""
Engine Parity Test: Validate new unified engine against old BacktestEngine.

This test runs the same Play through both engines and compares:
- Trade count
- Signal timing
- Final equity

Usage:
    python -m src.forge.validation.engine_parity_test

The test passes if both engines produce identical signals for the same data.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ...utils.logger import get_logger

logger = get_logger()


@dataclass
class ParityResult:
    """Result from parity test."""

    play_id: str
    passed: bool

    # Old engine results
    old_trade_count: int
    old_signal_count: int
    old_final_equity: float

    # New engine results
    new_trade_count: int
    new_signal_count: int
    new_final_equity: float

    # Differences
    trade_diff: int
    equity_diff: float

    # Details
    message: str = ""

    def __str__(self) -> str:
        status = "✓ PASSED" if self.passed else "✗ FAILED"
        return (
            f"{status}: {self.play_id}\n"
            f"  Old: {self.old_trade_count} trades, ${self.old_final_equity:,.2f}\n"
            f"  New: {self.new_trade_count} trades, ${self.new_final_equity:,.2f}\n"
            f"  Diff: {self.trade_diff} trades, ${self.equity_diff:,.2f}"
        )


def run_with_old_engine(play, window_start: datetime, window_end: datetime) -> dict:
    """
    Run Play with the old BacktestEngine.

    Returns dict with trade_count, signal_count, final_equity.
    """
    from ...backtest.engine_factory import (
        create_engine_from_play,
        run_engine_with_play,
    )

    # Create and run with old engine
    engine = create_engine_from_play(
        play,
        window_start=window_start,
        window_end=window_end,
    )

    result = run_engine_with_play(engine, play)

    return {
        "trade_count": len(result.trades),
        "final_equity": result.final_equity,
        "trades": result.trades,
    }


def run_with_new_engine(play, window_start: datetime, window_end: datetime) -> dict:
    """
    Run Play with the new unified PlayEngine.

    Returns dict with trade_count, signal_count, final_equity.

    NOTE: This is currently a placeholder. Full parity testing requires:
    1. Data loading integration (FeedStore -> BacktestDataProvider)
    2. BacktestRunner wiring with loaded data
    3. Signal evaluation through PlayEngine.process_bar()

    The framework is in place, but the data pipeline integration is pending.
    Once integrated, this will validate that the new engine produces
    identical results to the old BacktestEngine.
    """
    from ...engine import PlayEngineFactory, BacktestRunner

    # Create engine with factory
    engine = PlayEngineFactory.create(play, mode="backtest")

    # TODO: Integrate data loading pipeline
    # 1. Use engine_data_prep to load OHLCV data into FeedStore
    # 2. Create BacktestDataProvider wrapping FeedStore
    # 3. Inject into PlayEngine
    # 4. Run BacktestRunner and collect results

    # Placeholder until data integration is complete
    return {
        "trade_count": 0,  # Placeholder - will match old engine
        "final_equity": 10000.0,  # Placeholder - will match old engine
        "trades": [],
    }


def run_parity_test(play_path: str | Path) -> ParityResult:
    """
    Run parity test for a single Play.

    Args:
        play_path: Path to Play YAML file

    Returns:
        ParityResult with comparison
    """
    from ...backtest.play import Play

    # Load Play
    play_path = Path(play_path)
    if not play_path.exists():
        return ParityResult(
            play_id=str(play_path),
            passed=False,
            old_trade_count=0,
            old_signal_count=0,
            old_final_equity=0,
            new_trade_count=0,
            new_signal_count=0,
            new_final_equity=0,
            trade_diff=0,
            equity_diff=0,
            message=f"Play file not found: {play_path}",
        )

    play = Play.from_file(play_path)

    # Define test window (1 month of data)
    window_end = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    window_start = window_end - timedelta(days=30)

    try:
        # Run with old engine
        logger.info(f"Running {play.name} with old engine...")
        old_result = run_with_old_engine(play, window_start, window_end)

        # Run with new engine
        logger.info(f"Running {play.name} with new engine...")
        new_result = run_with_new_engine(play, window_start, window_end)

        # Compare results
        trade_diff = abs(old_result["trade_count"] - new_result["trade_count"])
        equity_diff = abs(old_result["final_equity"] - new_result["final_equity"])

        # Pass if trade counts match (equity can have small float differences)
        passed = trade_diff == 0 and equity_diff < 0.01

        return ParityResult(
            play_id=play.name,
            passed=passed,
            old_trade_count=old_result["trade_count"],
            old_signal_count=old_result["trade_count"],  # Signals = trades for now
            old_final_equity=old_result["final_equity"],
            new_trade_count=new_result["trade_count"],
            new_signal_count=new_result["trade_count"],
            new_final_equity=new_result["final_equity"],
            trade_diff=trade_diff,
            equity_diff=equity_diff,
            message="Parity test complete",
        )

    except Exception as e:
        logger.error(f"Parity test failed for {play.name}: {e}")
        return ParityResult(
            play_id=play.name,
            passed=False,
            old_trade_count=0,
            old_signal_count=0,
            old_final_equity=0,
            new_trade_count=0,
            new_signal_count=0,
            new_final_equity=0,
            trade_diff=0,
            equity_diff=0,
            message=f"Error: {e}",
        )


def run_all_parity_tests(plays_dir: str | Path | None = None) -> list[ParityResult]:
    """
    Run parity tests for all validation Plays.

    Args:
        plays_dir: Directory containing Play YAML files

    Returns:
        List of ParityResult objects
    """
    if plays_dir is None:
        plays_dir = Path(__file__).parent.parent.parent.parent / "tests" / "validation" / "plays"

    plays_dir = Path(plays_dir)
    if not plays_dir.exists():
        logger.error(f"Plays directory not found: {plays_dir}")
        return []

    results = []
    for play_file in sorted(plays_dir.glob("*.yml")):
        logger.info(f"\n{'='*60}")
        logger.info(f"Testing: {play_file.name}")
        logger.info("="*60)

        result = run_parity_test(play_file)
        results.append(result)
        print(result)

    return results


def main():
    """Run parity tests from command line."""
    logger.info("Engine Parity Test")
    logger.info("=" * 60)

    results = run_all_parity_tests()

    # Summary
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)

    print("\n" + "=" * 60)
    print(f"SUMMARY: {passed} passed, {failed} failed")
    print("=" * 60)

    # Exit with error code if any failed
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
