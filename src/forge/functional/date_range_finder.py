"""
Date Range Finder for Functional Tests.

Automatically finds date ranges where a strategy produces expected signal counts.

Key Principle:
    If a strategy doesn't produce signals for a date range,
    change the DATE RANGE, not the strategy.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


@dataclass
class DateRange:
    """A date range with expected signal count."""

    start: datetime
    end: datetime
    expected_signals: int = 0

    @property
    def days(self) -> int:
        """Number of days in range."""
        return (self.end - self.start).days

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "expected_signals": self.expected_signals,
            "days": self.days,
        }


class DateRangeFinder:
    """
    Finds date ranges where a strategy produces expected signal counts.

    Uses sliding window search through historical data.
    """

    def __init__(
        self,
        data_env: str = "live",
        cache_dir: Path | None = None,
    ):
        """
        Initialize the date range finder.

        Args:
            data_env: Data environment (live or demo)
            cache_dir: Directory to cache found ranges
        """
        self.data_env = data_env
        self.cache_dir = cache_dir

        # Cache of (play_id -> DateRange)
        self._cache: dict[str, DateRange] = {}

    def find_optimal_range(
        self,
        play_id: str,
        plays_dir: Path,
        min_signals: int = 5,
        max_signals: int = 50,
        window_days: int = 30,
        max_lookback_days: int = 365,
        step_days: int = 7,
    ) -> DateRange | None:
        """
        Find a date range where the strategy produces expected signals.

        Args:
            play_id: Play ID (filename without .yml)
            plays_dir: Directory containing Play YAMLs
            min_signals: Minimum signals required
            max_signals: Maximum signals allowed
            window_days: Size of sliding window
            max_lookback_days: Maximum days to look back
            step_days: Days to slide window on each iteration

        Returns:
            DateRange with optimal window, or None if not found
        """
        # Check cache first
        cache_key = f"{play_id}_{min_signals}_{max_signals}_{window_days}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            # Load Play
            from src.backtest.play import load_play

            play = load_play(play_id, base_dir=plays_dir)
            symbol = play.symbol_universe[0] if play.symbol_universe else "BTCUSDT"
            tf = play.execution_tf

            # Get data coverage
            from src.data.historical_data_store import get_historical_store

            store = get_historical_store(env=self.data_env)
            status = store.status(symbol)
            key = f"{symbol}_{tf}"

            if key not in status:
                print(f"[WARN] No data for {key}")
                return None

            info = status[key]
            data_start: datetime = info.get("first_timestamp")
            data_end: datetime = info.get("last_timestamp")

            if not data_start or not data_end:
                print(f"[WARN] Invalid data range for {key}")
                return None

            # Ensure timezone aware
            if data_start.tzinfo is None:
                data_start = data_start.replace(tzinfo=timezone.utc)
            if data_end.tzinfo is None:
                data_end = data_end.replace(tzinfo=timezone.utc)

            # Start from recent data and slide backward
            window = timedelta(days=window_days)
            step = timedelta(days=step_days)
            max_lookback = timedelta(days=max_lookback_days)

            end_cursor = data_end
            earliest_allowed = max(data_start, data_end - max_lookback)

            print(f"[SEARCH] Data range: {data_start.date()} to {data_end.date()}")
            print(f"[SEARCH] Sliding {window_days}-day window, step={step_days} days")

            best_range: DateRange | None = None
            iteration = 0

            while end_cursor - window >= earliest_allowed:
                iteration += 1
                window_start = end_cursor - window
                window_end = end_cursor

                # Quick signal count estimation
                signal_count = self._estimate_signals(
                    play=play,
                    symbol=symbol,
                    tf=tf,
                    start=window_start,
                    end=window_end,
                    store=store,
                )

                if signal_count is None:
                    # Data loading failed, slide backward
                    end_cursor -= step
                    continue

                print(f"  [{iteration}] {window_start.date()} to {window_end.date()}: {signal_count} signals")

                if min_signals <= signal_count <= max_signals:
                    # Found good range
                    best_range = DateRange(
                        start=window_start,
                        end=window_end,
                        expected_signals=signal_count,
                    )
                    break
                elif signal_count > max_signals:
                    # Too many signals - try smaller window or slide
                    # First try reducing window by half
                    if window_days > 7:
                        window = timedelta(days=window_days // 2)
                    else:
                        end_cursor -= step
                elif signal_count < min_signals:
                    # Too few signals - slide backward to find more action
                    end_cursor -= step

            # Cache result
            if best_range:
                self._cache[cache_key] = best_range

            return best_range

        except Exception as e:
            import traceback
            print(f"[ERROR] Date range search failed: {e}")
            traceback.print_exc()
            return None

    def _estimate_signals(
        self,
        play: Any,
        symbol: str,
        tf: str,
        start: datetime,
        end: datetime,
        store: Any,
    ) -> int | None:
        """
        Estimate signal count for a date range.

        Uses lightweight signal evaluation without full backtest.

        Args:
            play: Play configuration
            symbol: Trading symbol
            tf: Timeframe
            start: Window start
            end: Window end
            store: Historical data store

        Returns:
            Estimated signal count, or None on error
        """
        try:
            # Load data
            df = store.get_ohlcv(symbol=symbol, tf=tf, start=start, end=end)

            if df is None or df.empty:
                return None

            # Quick warmup check
            min_bars = 50  # Reasonable minimum for indicators
            if len(df) < min_bars:
                return 0

            # Use lightweight signal estimation
            # For simplicity, count bars where entry conditions might be met
            # This is a fast approximation, not exact signal count

            # Approach: Run the actual signal evaluator but in estimation mode
            return self._run_signal_estimation(play, df, symbol, tf, start, end, store)

        except Exception as e:
            print(f"[WARN] Signal estimation failed: {e}")
            return None

    def _run_signal_estimation(
        self,
        play: Any,
        df: Any,
        symbol: str,
        tf: str,
        start: datetime,
        end: datetime,
        store: Any,
    ) -> int:
        """
        Run actual signal estimation using Play evaluator.

        This runs a lightweight version of the engine to count signals.
        """
        try:
            from src.backtest.engine import create_engine_from_play, run_engine_with_play
            from src.backtest.execution_validation import compute_warmup_requirements

            # Compute warmup
            warmup_reqs = compute_warmup_requirements(play)
            warmup_by_tf = warmup_reqs.warmup_by_role

            # Create engine
            engine = create_engine_from_play(
                play=play,
                window_start=start,
                window_end=end,
                warmup_by_tf=warmup_by_tf,
            )

            # Run engine
            result = run_engine_with_play(engine, play)

            # Count entry signals from events
            if hasattr(result, 'events') and result.events:
                entry_signals = sum(
                    1 for e in result.events
                    if hasattr(e, 'event_type') and 'entry' in str(e.event_type).lower()
                )
                return entry_signals

            # Fallback: count trades (each trade = at least one signal)
            if hasattr(result, 'trades') and result.trades:
                return len(result.trades)

            return 0

        except Exception as e:
            # Signal estimation failure - return 0 (will skip this window)
            return 0

    def get_data_coverage(self, symbol: str, tf: str) -> tuple[datetime, datetime] | None:
        """
        Get available data coverage for a symbol/timeframe.

        Returns:
            Tuple of (start, end) datetimes, or None if no data
        """
        try:
            from src.data.historical_data_store import get_historical_store

            store = get_historical_store(env=self.data_env)
            status = store.status(symbol)
            key = f"{symbol}_{tf}"

            if key not in status:
                return None

            info = status[key]
            start = info.get("first_timestamp")
            end = info.get("last_timestamp")

            if start and end:
                # Ensure timezone aware
                if start.tzinfo is None:
                    start = start.replace(tzinfo=timezone.utc)
                if end.tzinfo is None:
                    end = end.replace(tzinfo=timezone.utc)
                return (start, end)

            return None

        except Exception:
            return None

    def clear_cache(self) -> None:
        """Clear the date range cache."""
        self._cache.clear()
