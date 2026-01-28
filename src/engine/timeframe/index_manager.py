"""
TF index management for 3-feed + exec role system.

This module provides unified implementation of TF index tracking
for low_tf, med_tf, high_tf feeds relative to the exec role.

The exec role is NOT a 4th feed - it's a pointer to one of the 3 feeds.
This determines which feed we "step on" during simulation.

Forward-Fill Semantics:
    - TFs SLOWER than exec: forward-fill (hold last closed bar)
    - TFs FASTER than exec: lookup most recent closed bar at exec close
    - TF EQUAL to exec: direct access (index from exec stepping)

Example (exec=med_tf, low_tf=15m, med_tf=1h, high_tf=4h):
    When stepping on 1h bars:
    - low_tf (15m): lookup most recent 15m close at 1h close
    - med_tf (1h): direct access (current bar)
    - high_tf (4h): forward-fill until 4h closes

Uses O(1) ts_close_ms_to_idx mapping from FeedStore.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...backtest.runtime.feed_store import FeedStore


@dataclass(slots=True, frozen=True)
class TFIndexUpdate:
    """Result of TF index update for all 3 feeds.

    Attributes:
        low_tf_changed: True if low_tf index changed
        med_tf_changed: True if med_tf index changed
        high_tf_changed: True if high_tf index changed
        low_tf_idx: Current low_tf index
        med_tf_idx: Current med_tf index
        high_tf_idx: Current high_tf index
    """

    low_tf_changed: bool
    med_tf_changed: bool
    high_tf_changed: bool
    low_tf_idx: int
    med_tf_idx: int
    high_tf_idx: int



class TFIndexManager:
    """
    Manages TF indices for 3-feed + exec role system.

    This class tracks which bar index to use for each TF at any given
    exec bar. The behavior depends on whether a TF is faster or slower
    than exec:

    - SLOWER than exec: Forward-fill (stays constant until bar closes)
    - FASTER than exec: Lookup most recent closed bar at exec close
    - EQUAL to exec: Direct access (index from exec stepping)

    Usage:
        manager = TFIndexManager(
            low_tf_feed=low_tf_feed,
            med_tf_feed=med_tf_feed,
            high_tf_feed=high_tf_feed,
            exec_role="low_tf",  # or "med_tf" or "high_tf"
        )

        for exec_bar in bars:
            update = manager.update_indices(exec_bar.ts_close, exec_idx)
            if update.high_tf_changed:
                # New high_tf bar closed - update incremental structures
                ...

    Thread Safety:
        NOT thread-safe. Use one manager per engine instance.
    """

    def __init__(
        self,
        low_tf_feed: "FeedStore",
        med_tf_feed: "FeedStore | None",
        high_tf_feed: "FeedStore | None",
        exec_role: str,
    ) -> None:
        """
        Initialize TFIndexManager.

        Args:
            low_tf_feed: LowTF FeedStore (always required)
            med_tf_feed: MedTF FeedStore (None if same as low_tf)
            high_tf_feed: HighTF FeedStore (None if same as med_tf or low_tf)
            exec_role: Which feed we step on ("low_tf", "med_tf", "high_tf")
        """
        self._low_tf_feed = low_tf_feed
        self._med_tf_feed = med_tf_feed
        self._high_tf_feed = high_tf_feed
        self._exec_role = exec_role

        # Resolve exec feed
        if exec_role == "low_tf":
            self._exec_feed = low_tf_feed
        elif exec_role == "med_tf":
            self._exec_feed = med_tf_feed or low_tf_feed
        elif exec_role == "high_tf":
            self._exec_feed = high_tf_feed or med_tf_feed or low_tf_feed
        else:
            raise ValueError(f"Invalid exec_role: {exec_role}")

        # Current indices
        self._current_low_tf_idx: int = 0
        self._current_med_tf_idx: int = 0
        self._current_high_tf_idx: int = 0

    @property
    def low_tf_idx(self) -> int:
        """Current low_tf index."""
        return self._current_low_tf_idx

    @property
    def med_tf_idx(self) -> int:
        """Current med_tf index."""
        return self._current_med_tf_idx

    @property
    def high_tf_idx(self) -> int:
        """Current high_tf index."""
        return self._current_high_tf_idx

    def reset(self) -> None:
        """Reset indices to initial state."""
        self._current_low_tf_idx = 0
        self._current_med_tf_idx = 0
        self._current_high_tf_idx = 0

    def update_indices(self, exec_ts_close: datetime, exec_idx: int | None = None) -> TFIndexUpdate:
        """
        Update all TF indices based on exec bar close timestamp.

        Uses O(1) lookup via FeedStore.get_idx_at_ts_close() to determine
        indices for TFs that aren't the exec TF.

        Args:
            exec_ts_close: Current exec bar's close timestamp
            exec_idx: Current exec bar index (optional, for direct assignment)

        Returns:
            TFIndexUpdate with change flags and current indices
        """
        low_tf_changed = False
        med_tf_changed = False
        high_tf_changed = False

        # Update indices based on exec role
        if self._exec_role == "low_tf":
            # Exec is low_tf: direct access for low_tf, forward-fill for med/high
            if exec_idx is not None:
                if exec_idx != self._current_low_tf_idx:
                    low_tf_changed = True
                self._current_low_tf_idx = exec_idx

            # Forward-fill med_tf (slower than exec)
            if self._med_tf_feed is not None:
                med_idx = self._med_tf_feed.get_idx_at_ts_close(exec_ts_close)
                if med_idx is not None and 0 <= med_idx < self._med_tf_feed.length:
                    if med_idx != self._current_med_tf_idx:
                        med_tf_changed = True
                    self._current_med_tf_idx = med_idx

            # Forward-fill high_tf (slower than exec)
            if self._high_tf_feed is not None:
                high_idx = self._high_tf_feed.get_idx_at_ts_close(exec_ts_close)
                if high_idx is not None and 0 <= high_idx < self._high_tf_feed.length:
                    if high_idx != self._current_high_tf_idx:
                        high_tf_changed = True
                    self._current_high_tf_idx = high_idx

        elif self._exec_role == "med_tf":
            # Exec is med_tf: lookup low_tf, direct for med_tf, forward-fill high_tf
            if exec_idx is not None:
                if exec_idx != self._current_med_tf_idx:
                    med_tf_changed = True
                self._current_med_tf_idx = exec_idx

            # Lookup low_tf (faster than exec)
            low_idx = self._low_tf_feed.get_idx_at_ts_close(exec_ts_close)
            if low_idx is not None and 0 <= low_idx < self._low_tf_feed.length:
                if low_idx != self._current_low_tf_idx:
                    low_tf_changed = True
                self._current_low_tf_idx = low_idx

            # Forward-fill high_tf (slower than exec)
            if self._high_tf_feed is not None:
                high_idx = self._high_tf_feed.get_idx_at_ts_close(exec_ts_close)
                if high_idx is not None and 0 <= high_idx < self._high_tf_feed.length:
                    if high_idx != self._current_high_tf_idx:
                        high_tf_changed = True
                    self._current_high_tf_idx = high_idx

        elif self._exec_role == "high_tf":
            # Exec is high_tf: lookup low_tf and med_tf, direct for high_tf
            if exec_idx is not None:
                if exec_idx != self._current_high_tf_idx:
                    high_tf_changed = True
                self._current_high_tf_idx = exec_idx

            # Lookup low_tf (faster than exec)
            low_idx = self._low_tf_feed.get_idx_at_ts_close(exec_ts_close)
            if low_idx is not None and 0 <= low_idx < self._low_tf_feed.length:
                if low_idx != self._current_low_tf_idx:
                    low_tf_changed = True
                self._current_low_tf_idx = low_idx

            # Lookup med_tf (faster than exec if distinct)
            if self._med_tf_feed is not None:
                med_idx = self._med_tf_feed.get_idx_at_ts_close(exec_ts_close)
                if med_idx is not None and 0 <= med_idx < self._med_tf_feed.length:
                    if med_idx != self._current_med_tf_idx:
                        med_tf_changed = True
                    self._current_med_tf_idx = med_idx

        return TFIndexUpdate(
            low_tf_changed=low_tf_changed,
            med_tf_changed=med_tf_changed,
            high_tf_changed=high_tf_changed,
            low_tf_idx=self._current_low_tf_idx,
            med_tf_idx=self._current_med_tf_idx,
            high_tf_idx=self._current_high_tf_idx,
        )

    def set_indices(self, low_tf_idx: int, med_tf_idx: int, high_tf_idx: int) -> None:
        """
        Directly set TF indices (for state restoration).

        Args:
            low_tf_idx: low_tf index to set
            med_tf_idx: med_tf index to set
            high_tf_idx: high_tf index to set
        """
        self._current_low_tf_idx = low_tf_idx
        self._current_med_tf_idx = med_tf_idx
        self._current_high_tf_idx = high_tf_idx


def update_tf_indices_impl(
    exec_ts_close: datetime,
    low_tf_feed: "FeedStore",
    med_tf_feed: "FeedStore | None",
    high_tf_feed: "FeedStore | None",
    exec_feed: "FeedStore",
    current_low_tf_idx: int,
    current_med_tf_idx: int,
    current_high_tf_idx: int,
) -> tuple[bool, bool, bool, int, int, int]:
    """
    Functional implementation of TF index update.

    This is the stateless version for backward compatibility.

    Args:
        exec_ts_close: Current exec bar's ts_close
        low_tf_feed: LowTF FeedStore
        med_tf_feed: MedTF FeedStore (may be None)
        high_tf_feed: HighTF FeedStore (may be None)
        exec_feed: Exec FeedStore (determines which TF is exec)
        current_low_tf_idx: Current low_tf index
        current_med_tf_idx: Current med_tf index
        current_high_tf_idx: Current high_tf index

    Returns:
        Tuple of (low_tf_updated, med_tf_updated, high_tf_updated,
                  new_low_tf_idx, new_med_tf_idx, new_high_tf_idx)
    """
    low_tf_updated = False
    med_tf_updated = False
    high_tf_updated = False
    new_low_tf_idx = current_low_tf_idx
    new_med_tf_idx = current_med_tf_idx
    new_high_tf_idx = current_high_tf_idx

    # Low TF index (if distinct from exec)
    if low_tf_feed is not exec_feed:
        low_idx = low_tf_feed.get_idx_at_ts_close(exec_ts_close)
        if low_idx is not None and 0 <= low_idx < low_tf_feed.length:
            new_low_tf_idx = low_idx
            low_tf_updated = True

    # Med TF index (if distinct from exec)
    if med_tf_feed is not None and med_tf_feed is not exec_feed:
        med_idx = med_tf_feed.get_idx_at_ts_close(exec_ts_close)
        if med_idx is not None and 0 <= med_idx < med_tf_feed.length:
            new_med_tf_idx = med_idx
            med_tf_updated = True

    # High TF index (if distinct from exec)
    if high_tf_feed is not None and high_tf_feed is not exec_feed:
        high_idx = high_tf_feed.get_idx_at_ts_close(exec_ts_close)
        if high_idx is not None and 0 <= high_idx < high_tf_feed.length:
            new_high_tf_idx = high_idx
            high_tf_updated = True

    return (
        low_tf_updated,
        med_tf_updated,
        high_tf_updated,
        new_low_tf_idx,
        new_med_tf_idx,
        new_high_tf_idx,
    )
