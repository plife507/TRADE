"""
Functional Test Runner for TRADE Engine.

Tier 5: Uses real historical data to validate engine functionality.

Key Principle:
    If a strategy doesn't produce signals for a date range,
    change the DATE RANGE, not the strategy.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .date_range_finder import DateRangeFinder, DateRange
from .engine_validator import EngineValidator, ValidationResult


@dataclass
class FunctionalTestResult:
    """Result from a functional test run."""

    play_id: str
    success: bool
    date_range: DateRange | None = None
    signal_count: int = 0
    trade_count: int = 0
    validation_results: list[ValidationResult] = field(default_factory=list)
    error_message: str | None = None
    backtest_result: Any = None

    @property
    def all_validations_passed(self) -> bool:
        """Check if all validation assertions passed."""
        return all(v.passed for v in self.validation_results)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "play_id": self.play_id,
            "success": self.success,
            "date_range": self.date_range.to_dict() if self.date_range else None,
            "signal_count": self.signal_count,
            "trade_count": self.trade_count,
            "validations": [v.to_dict() for v in self.validation_results],
            "error_message": self.error_message,
        }

    def print_summary(self) -> None:
        """Print a summary of test results."""
        status = "PASS" if self.success else "FAIL"
        print(f"\n{'='*60}")
        print(f"  [{status}] {self.play_id}")
        print(f"{'='*60}")

        if self.date_range:
            print(f"  Date Range: {self.date_range.start.date()} to {self.date_range.end.date()}")
        print(f"  Signals: {self.signal_count}")
        print(f"  Trades: {self.trade_count}")

        if self.validation_results:
            print(f"\n  Validations:")
            for v in self.validation_results:
                v_status = "PASS" if v.passed else "FAIL"
                print(f"    [{v_status}] {v.name}")
                if not v.passed and v.message:
                    print(f"          {v.message}")

        if self.error_message:
            print(f"\n  Error: {self.error_message}")

        print(f"{'='*60}\n")


class FunctionalTestRunner:
    """
    Runs functional tests against real data.

    For each strategy Play:
    1. Find a date range that produces signals (auto-adjust)
    2. Run backtest against that range
    3. Validate engine behavior assertions
    """

    def __init__(
        self,
        plays_dir: Path | None = None,
        output_dir: Path = Path("tests/functional/results"),
        data_env: str = "live",
    ):
        """
        Initialize the functional test runner.

        Args:
            plays_dir: Directory containing Play YAML files
            output_dir: Directory for test artifacts
            data_env: Data environment (live or demo)
        """
        self.plays_dir = plays_dir or Path("tests/functional/strategies/plays")
        self.output_dir = output_dir
        self.data_env = data_env

        self._date_finder = DateRangeFinder(data_env=data_env)
        self._validator = EngineValidator()

    def run_test(
        self,
        play_id: str,
        min_signals: int = 5,
        max_signals: int = 50,
        window_days: int = 30,
    ) -> FunctionalTestResult:
        """
        Run a single functional test for a Play.

        Args:
            play_id: Play ID (filename without .yml)
            min_signals: Minimum signals required
            max_signals: Maximum signals allowed
            window_days: Window size for date range search

        Returns:
            FunctionalTestResult with test outcome
        """
        result = FunctionalTestResult(play_id=play_id, success=False)

        try:
            # Load Play
            from src.backtest.play import load_play

            play = load_play(play_id, base_dir=self.plays_dir)
            symbol = play.symbol_universe[0] if play.symbol_universe else "BTCUSDT"
            tf = play.execution_tf

            # Step 1: Find date range with signals
            print(f"\n[SEARCH] Finding date range for {play_id}...")
            date_range = self._date_finder.find_optimal_range(
                play_id=play_id,
                plays_dir=self.plays_dir,
                min_signals=min_signals,
                max_signals=max_signals,
                window_days=window_days,
            )

            if not date_range:
                result.error_message = f"No date range found with {min_signals}-{max_signals} signals"
                return result

            result.date_range = date_range
            print(f"[FOUND] Date range: {date_range.start.date()} to {date_range.end.date()}")
            print(f"        Expected signals: ~{date_range.expected_signals}")

            # Step 2: Run backtest
            print(f"\n[RUN] Running backtest...")
            from src.backtest.runner import RunnerConfig, run_backtest_with_gates
            from src.data.historical_data_store import get_historical_store

            store = get_historical_store(env=self.data_env)

            def data_loader(symbol: str, tf: str, start: datetime, end: datetime):
                return store.get_ohlcv(symbol=symbol, tf=tf, start=start, end=end)

            config = RunnerConfig(
                play_id=play_id,
                play=play,
                window_start=date_range.start,
                window_end=date_range.end,
                data_loader=data_loader,
                base_output_dir=self.output_dir,
                plays_dir=self.plays_dir,
                data_env=self.data_env,
            )

            backtest_result = run_backtest_with_gates(config)
            result.backtest_result = backtest_result

            if not backtest_result.success:
                result.error_message = backtest_result.error_message or "Backtest failed"
                return result

            # Extract counts
            if backtest_result.summary:
                result.trade_count = backtest_result.summary.trades_count or 0

            # Count signals from events if available
            result.signal_count = date_range.expected_signals

            # Step 3: Run validations
            print(f"\n[VALIDATE] Running engine validations...")
            validations = self._validator.validate_all(backtest_result, play)
            result.validation_results = validations

            # Determine success
            result.success = backtest_result.success and all(v.passed for v in validations)

            return result

        except Exception as e:
            import traceback
            result.error_message = f"{type(e).__name__}: {e}"
            traceback.print_exc()
            return result

    def run_all(
        self,
        pattern: str = "F_*.yml",
        min_signals: int = 5,
        max_signals: int = 50,
    ) -> list[FunctionalTestResult]:
        """
        Run all functional tests matching pattern.

        Args:
            pattern: Glob pattern for Play files
            min_signals: Minimum signals required
            max_signals: Maximum signals allowed

        Returns:
            List of FunctionalTestResult
        """
        results: list[FunctionalTestResult] = []

        play_files = sorted(self.plays_dir.glob(pattern))

        if not play_files:
            print(f"[WARN] No plays found matching {pattern} in {self.plays_dir}")
            return results

        print(f"\n{'='*60}")
        print(f"  FUNCTIONAL TEST SUITE")
        print(f"  Found {len(play_files)} plays to test")
        print(f"{'='*60}")

        for play_file in play_files:
            play_id = play_file.stem
            result = self.run_test(
                play_id=play_id,
                min_signals=min_signals,
                max_signals=max_signals,
            )
            result.print_summary()
            results.append(result)

        # Print overall summary
        passed = sum(1 for r in results if r.success)
        failed = len(results) - passed

        print(f"\n{'='*60}")
        print(f"  SUMMARY: {passed} passed, {failed} failed")
        print(f"{'='*60}\n")

        return results

    def list_plays(self, pattern: str = "F_*.yml") -> list[str]:
        """List available functional test plays."""
        play_files = sorted(self.plays_dir.glob(pattern))
        return [f.stem for f in play_files]


def run_functional_tests(
    play_id: str | None = None,
    pattern: str = "F_*.yml",
    plays_dir: Path | None = None,
    output_dir: Path = Path("tests/functional/results"),
    data_env: str = "live",
    min_signals: int = 5,
    max_signals: int = 50,
) -> list[FunctionalTestResult]:
    """
    Convenience function to run functional tests.

    Args:
        play_id: Specific Play to test, or None for all
        pattern: Glob pattern for Play files (if play_id is None)
        plays_dir: Directory containing Play YAMLs
        output_dir: Directory for test artifacts
        data_env: Data environment
        min_signals: Minimum signals required
        max_signals: Maximum signals allowed

    Returns:
        List of FunctionalTestResult
    """
    runner = FunctionalTestRunner(
        plays_dir=plays_dir,
        output_dir=output_dir,
        data_env=data_env,
    )

    if play_id:
        result = runner.run_test(
            play_id=play_id,
            min_signals=min_signals,
            max_signals=max_signals,
        )
        return [result]
    else:
        return runner.run_all(
            pattern=pattern,
            min_signals=min_signals,
            max_signals=max_signals,
        )


# =============================================================================
# CLI Entry Point
# =============================================================================

def main():
    """CLI entry point for functional tests."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Run TRADE Functional Tests (Tier 5)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "play_id",
        nargs="?",
        help="Specific Play ID to test (omit for all)",
    )
    parser.add_argument(
        "--pattern",
        default="F_*.yml",
        help="Glob pattern for Play files (default: F_*.yml)",
    )
    parser.add_argument(
        "--plays-dir",
        default="tests/functional/strategies/plays",
        help="Directory containing Play YAMLs",
    )
    parser.add_argument(
        "--output-dir",
        default="tests/functional/results",
        help="Directory for test artifacts",
    )
    parser.add_argument(
        "--env",
        choices=["live", "demo"],
        default="live",
        help="Data environment",
    )
    parser.add_argument(
        "--min-signals",
        type=int,
        default=5,
        help="Minimum signals required (default: 5)",
    )
    parser.add_argument(
        "--max-signals",
        type=int,
        default=50,
        help="Maximum signals allowed (default: 50)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available functional test plays",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )

    args = parser.parse_args()

    plays_dir = Path(args.plays_dir)
    output_dir = Path(args.output_dir)

    # List mode
    if args.list:
        runner = FunctionalTestRunner(plays_dir=plays_dir, data_env=args.env)
        plays = runner.list_plays(pattern=args.pattern)
        print(f"\nAvailable Functional Test Plays ({len(plays)}):")
        for play in plays:
            print(f"  - {play}")
        sys.exit(0)

    # Run tests
    results = run_functional_tests(
        play_id=args.play_id,
        pattern=args.pattern,
        plays_dir=plays_dir,
        output_dir=output_dir,
        data_env=args.env,
        min_signals=args.min_signals,
        max_signals=args.max_signals,
    )

    # Exit code
    all_passed = all(r.success for r in results)
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
