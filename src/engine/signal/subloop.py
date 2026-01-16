"""
Unified 1m sub-loop evaluation for signal generation.

This module extracts the common 1m sub-loop pattern from both BacktestEngine
and PlayEngine into a shared, engine-agnostic implementation.

The SubLoopEvaluator handles:
- Iterating through 1m bars within an exec bar
- Building snapshots with proper 1m prices
- Evaluating signals at each 1m tick
- Returning on first signal (max one entry per exec bar)
- Graceful fallback when 1m data is unavailable

Engines provide a SubLoopContext that implements the engine-specific parts:
- Snapshot building with 1m prices
- Signal evaluation (strategy function or PlaySignalEvaluator)
- Entry skip logic (entries_disabled check)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol, TypeVar

if TYPE_CHECKING:
    from ...backtest.runtime.snapshot_view import RuntimeSnapshotView
    from ...backtest.runtime.feed_store import FeedStore
    from ...core.risk_manager import Signal


# Type variable for snapshot (could be RuntimeSnapshotView or compatible)
SnapshotT = TypeVar("SnapshotT")


@dataclass(slots=True)
class SubLoopResult:
    """Result from 1m sub-loop evaluation.

    Attributes:
        signal: Signal if triggered, None otherwise
        snapshot: Last snapshot evaluated (for metric tracking)
        signal_ts: Timestamp of signal (1m close time) if triggered
    """

    signal: "Signal | None"
    snapshot: Any  # RuntimeSnapshotView or compatible
    signal_ts: datetime | None


class SubLoopContext(Protocol):
    """Protocol for engine-specific sub-loop behavior.

    Engines implement this to provide their specific snapshot building
    and signal evaluation logic while sharing the 1m iteration logic.
    """

    def build_snapshot_1m(
        self,
        exec_idx: int,
        price_1m: float,
        prev_price_1m: float | None,
        quote_idx: int,
    ) -> Any:
        """Build snapshot with 1m prices for signal evaluation.

        Args:
            exec_idx: Current exec bar index
            price_1m: Current 1m close price
            prev_price_1m: Previous 1m close price (for crossover operators)
            quote_idx: Current 1m bar index in quote feed

        Returns:
            Snapshot object suitable for evaluate_signal()
        """
        ...

    def evaluate_signal(self, snapshot: Any) -> "Signal | None":
        """Evaluate strategy/rules and return signal.

        Args:
            snapshot: Snapshot from build_snapshot_1m()

        Returns:
            Signal if triggered, None otherwise
        """
        ...

    def should_skip_entry(self) -> bool:
        """Check if entries are disabled and no position exists.

        When True, the sub-loop skips signal evaluation for that tick
        (allows exits when entries disabled, but blocks new entries).

        Returns:
            True if should skip, False to evaluate
        """
        ...

    def build_fallback_snapshot(self, exec_idx: int, exec_close: float) -> Any:
        """Build fallback snapshot when 1m data unavailable.

        Args:
            exec_idx: Current exec bar index
            exec_close: Exec bar close price

        Returns:
            Snapshot for fallback evaluation
        """
        ...


class SubLoopEvaluator:
    """Engine-agnostic 1m sub-loop evaluator.

    This class encapsulates the shared logic for evaluating signals at
    1m granularity within exec bars. Both BacktestEngine and PlayEngine
    can use this with their own SubLoopContext implementations.

    Example:
        # In PlayEngine
        evaluator = SubLoopEvaluator(
            quote_feed=self._quote_feed,
            exec_tf=self.timeframe,
            logger=self.logger,
        )
        result = evaluator.evaluate(
            exec_idx=bar_index,
            context=PlayEngineSubLoopContext(self, candle, position),
        )
    """

    # TF_MINUTES mapping (duplicated to avoid circular imports)
    TF_MINUTES: dict[str, int] = {
        "1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
        "1h": 60, "2h": 120, "4h": 240, "6h": 360, "12h": 720,
        "d": 1440, "w": 10080, "m": 43200,
    }

    def __init__(
        self,
        quote_feed: "FeedStore | None",
        exec_tf: str,
        logger: Any | None = None,
    ):
        """Initialize the sub-loop evaluator.

        Args:
            quote_feed: 1m price data feed (None if unavailable)
            exec_tf: Execution timeframe (e.g., "15m", "1h")
            logger: Logger for warnings (optional)
        """
        self._quote_feed = quote_feed
        self._exec_tf = exec_tf.lower()
        self._exec_tf_minutes = self.TF_MINUTES.get(self._exec_tf, 15)
        self._logger = logger
        self._fallback_warned = False

    def evaluate(
        self,
        exec_idx: int,
        context: SubLoopContext,
        exec_close: float,
    ) -> SubLoopResult:
        """Evaluate strategy at 1m granularity within an exec bar.

        Iterates through 1m bars within the current exec bar and evaluates
        the strategy at each 1m close. Returns on first signal (max one
        entry per exec bar).

        Args:
            exec_idx: Current exec bar index
            context: Engine-specific context for snapshot/evaluation
            exec_close: Exec bar close price (for fallback)

        Returns:
            SubLoopResult with signal, snapshot, and signal_ts
        """
        # Check if 1m quote feed is available
        if self._quote_feed is None or self._quote_feed.length == 0:
            return self._evaluate_fallback(exec_idx, context, exec_close)

        # Get 1m bar range for this exec bar
        start_1m, end_1m = self._quote_feed.get_1m_indices_for_exec(
            exec_idx, self._exec_tf_minutes
        )

        # Clamp to available 1m data (both start and end)
        max_valid_idx = self._quote_feed.length - 1
        start_1m = min(start_1m, max_valid_idx)
        end_1m = min(end_1m, max_valid_idx)

        # If start > end after clamping, quote feed doesn't cover this exec bar
        if start_1m > end_1m:
            if not self._fallback_warned and self._logger:
                self._logger.warning(
                    f"1m quote feed doesn't cover exec bar {exec_idx} - "
                    f"using exec_tf close."
                )
                self._fallback_warned = True
            return self._evaluate_fallback(exec_idx, context, exec_close)

        # Track last snapshot for return
        last_snapshot = None

        # Track previous 1m price for crossover operators
        # Seed with the 1m bar BEFORE start_1m to enable crossover on first iteration
        if start_1m > 0 and start_1m - 1 <= max_valid_idx:
            prev_price_1m: float | None = float(self._quote_feed.close[start_1m - 1])
        else:
            prev_price_1m = None

        # Iterate through 1m bars (mandatory 1m action loop)
        for sub_idx in range(start_1m, end_1m + 1):
            # Get 1m close price
            price_1m = float(self._quote_feed.close[sub_idx])

            # Build snapshot with 1m prices
            snapshot = context.build_snapshot_1m(
                exec_idx=exec_idx,
                price_1m=price_1m,
                prev_price_1m=prev_price_1m,
                quote_idx=sub_idx,
            )
            last_snapshot = snapshot

            # Update previous price for next iteration
            prev_price_1m = price_1m

            # Skip if entries disabled and no position
            if context.should_skip_entry():
                continue

            # Skip if snapshot build failed
            if snapshot is None:
                continue

            # Evaluate strategy
            signal = context.evaluate_signal(snapshot)

            if signal is not None:
                # Get 1m close timestamp for order submission
                signal_ts = self._quote_feed.get_ts_close_datetime(sub_idx)
                return SubLoopResult(
                    signal=signal,
                    snapshot=snapshot,
                    signal_ts=signal_ts,
                )

        # No signal triggered - return last snapshot for consistency
        if last_snapshot is None:
            last_snapshot = context.build_fallback_snapshot(exec_idx, exec_close)

        return SubLoopResult(
            signal=None,
            snapshot=last_snapshot,
            signal_ts=None,
        )

    def _evaluate_fallback(
        self,
        exec_idx: int,
        context: SubLoopContext,
        exec_close: float,
    ) -> SubLoopResult:
        """Fallback evaluation when 1m data unavailable.

        Evaluates at exec close only (no 1m sub-loop).
        """
        if not self._fallback_warned and self._logger:
            self._logger.warning(
                f"1m quote feed unavailable - using exec_tf close for "
                f"signal evaluation. For full 1m action semantics, "
                f"sync 1m data."
            )
            self._fallback_warned = True

        snapshot = context.build_fallback_snapshot(exec_idx, exec_close)
        signal = None

        if not context.should_skip_entry() and snapshot is not None:
            signal = context.evaluate_signal(snapshot)

        return SubLoopResult(
            signal=signal,
            snapshot=snapshot,
            signal_ts=None,
        )
