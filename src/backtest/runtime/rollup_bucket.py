"""
ExecRollupBucket for 1m price rollups between exec closes.

This module provides the rollup aggregation mechanism that accumulates
1m bar data between exec TF closes. At each exec close, the bucket is
frozen into packet keys and reset for the next interval.

Phase 3: Price Feed (1m) + Preflight Gate + Packet Injection

Key concepts:
- Rollups aggregate 1m bar data (high/low/count) between exec closes
- At exec close: freeze() → inject into packet → reset()
- No intrabar strategy evaluation; rollups are read-only views
- Zone interaction fields are placeholders for Market Structure phase

PERFORMANCE CONTRACT:
- accumulate() is O(1) - simple min/max/count updates
- freeze() is O(1) - dict construction from fields
- reset() is O(1) - field resets
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .quote_state import QuoteState


# =============================================================================
# Rollup Key Constants
# =============================================================================

ROLLUP_KEYS = {
    "px.rollup.min_1m": "Minimum 1m low price since last exec close",
    "px.rollup.max_1m": "Maximum 1m high price since last exec close",
    "px.rollup.bars_1m": "Count of 1m bars since last exec close",
    "px.rollup.open_1m": "First 1m open price since last exec close",
    "px.rollup.close_1m": "Last 1m close price since last exec close",
    "px.rollup.volume_1m": "Sum of 1m volume since last exec close",
}


# =============================================================================
# ExecRollupBucket
# =============================================================================


@dataclass
class ExecRollupBucket:
    """
    Accumulates 1m bar data between exec TF closes.

    The bucket tracks price extremes, bar count, and volume across the
    1m bars that occur between two consecutive exec TF closes. At each
    exec close, the bucket is frozen into a dict of packet keys and reset.

    Usage:
        bucket = ExecRollupBucket()

        # Between exec closes, accumulate 1m quotes
        for quote in quotes_since_last_exec:
            bucket.accumulate(quote)

        # At exec close, freeze and inject into packet
        rollups = bucket.freeze()
        packet.update(rollups)

        # Reset for next interval
        bucket.reset()

    Attributes:
        min_price_1m: Minimum 1m low since last exec close
        max_price_1m: Maximum 1m high since last exec close
        bar_count_1m: Number of 1m bars accumulated
        open_price_1m: First 1m open (set on first accumulate)
        close_price_1m: Last 1m close (updated on each accumulate)
        volume_1m: Sum of 1m volume

    Note:
        Zone interaction fields (touched_since_last_exec, etc.) are
        placeholders for the Market Structure phase. They will be
        implemented when market structure state machines are added.
    """

    min_price_1m: float = field(default=float('inf'))
    max_price_1m: float = field(default=float('-inf'))
    bar_count_1m: int = field(default=0)
    open_price_1m: float = field(default=0.0)
    close_price_1m: float = field(default=0.0)
    volume_1m: float = field(default=0.0)

    # Zone interaction placeholders (Market Structure phase)
    # These will be wired when market structure state machines are added
    # touched_since_last_exec: bool = field(default=False)
    # entered_since_last_exec: bool = field(default=False)
    # minutes_in_zone: int = field(default=0)
    # min_distance_to_zone: float = field(default=float('inf'))

    def accumulate(self, quote: "QuoteState") -> None:
        """
        Accumulate a 1m quote into the rollup bucket.

        Called for each 1m bar that closes between exec TF closes.
        Updates running min/max, tracks first open, last close, and sums volume.

        Args:
            quote: QuoteState from the most recent closed 1m bar

        Performance: O(1) - simple comparisons and updates
        """
        # Track first open (P2-001 FIX: use actual 1m open, not close proxy)
        if self.bar_count_1m == 0:
            self.open_price_1m = quote.open_1m

        # Update price extremes
        self.min_price_1m = min(self.min_price_1m, quote.low_1m)
        self.max_price_1m = max(self.max_price_1m, quote.high_1m)

        # Track last close
        self.close_price_1m = quote.last

        # Sum volume
        self.volume_1m += quote.volume_1m

        # Increment count
        self.bar_count_1m += 1

    def freeze(self) -> dict[str, float]:
        """
        Freeze the rollup bucket into a dict of packet keys.

        Called at each exec TF close to inject rollup data into the
        strategy packet. Returns the current state without modifying it.

        Returns:
            Dict with px.rollup.* keys and their values

        Performance: O(1) - dict construction from fields

        Note:
            If no 1m bars were accumulated (bar_count_1m == 0), the
            returned values will reflect the reset state (inf/-inf/0).
            Strategies should check px.rollup.bars_1m > 0 before using
            price extremes.
        """
        nan = float('nan')
        empty = self.bar_count_1m == 0
        return {
            "px.rollup.min_1m": nan if empty else self.min_price_1m,
            "px.rollup.max_1m": nan if empty else self.max_price_1m,
            "px.rollup.bars_1m": float(self.bar_count_1m),
            "px.rollup.open_1m": nan if empty else self.open_price_1m,
            "px.rollup.close_1m": nan if empty else self.close_price_1m,
            "px.rollup.volume_1m": nan if empty else self.volume_1m,
        }

    def reset(self) -> None:
        """
        Reset the rollup bucket for the next exec interval.

        Called after freeze() at each exec TF close. Resets all fields
        to their initial state to begin accumulating the next interval.

        Performance: O(1) - field resets
        """
        self.min_price_1m = float('inf')
        self.max_price_1m = float('-inf')
        self.bar_count_1m = 0
        self.open_price_1m = 0.0
        self.close_price_1m = 0.0
        self.volume_1m = 0.0

    @property
    def is_empty(self) -> bool:
        """Check if no 1m bars have been accumulated."""
        return self.bar_count_1m == 0

    @property
    def price_range_1m(self) -> float:
        """
        Get the price range (max - min) of accumulated 1m bars.

        Returns:
            Price range in quote currency, or 0.0 if no bars accumulated
        """
        if self.is_empty:
            return 0.0
        return self.max_price_1m - self.min_price_1m


def create_empty_rollup_dict() -> dict[str, float]:
    """
    Create an empty rollup dict with default values.

    Useful for initializing packet state before any 1m bars are processed.

    Returns:
        Dict with px.rollup.* keys set to their initial values
    """
    return {
        "px.rollup.min_1m": float('inf'),
        "px.rollup.max_1m": float('-inf'),
        "px.rollup.bars_1m": 0.0,
        "px.rollup.open_1m": 0.0,
        "px.rollup.close_1m": 0.0,
        "px.rollup.volume_1m": 0.0,
    }
