"""
HTF/MTF index management for forward-fill behavior.

This module provides a unified implementation of HTF/MTF index tracking
that works identically for both BacktestEngine and PlayEngine.

Forward-Fill Principle:
    Any TF slower than exec keeps its index constant until its bar closes.
    This ensures no-lookahead (values reflect last CLOSED bar only).

Example (exec=15m, HTF=1h):
    exec bars:      |  1  |  2  |  3  |  4  |  5  |  ...
    htf_idx:        [  0     0     0     0  ] [  1  ...
    htf_changed:       F     F     F     T      F  ...

Uses O(1) ts_close_ms_to_idx mapping from FeedStore.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...backtest.runtime.feed_store import FeedStore


@dataclass(slots=True, frozen=True)
class HTFIndexUpdate:
    """Result of an HTF/MTF index update operation.

    Attributes:
        htf_changed: True if HTF index changed (new HTF bar closed)
        mtf_changed: True if MTF index changed (new MTF bar closed)
        htf_idx: Current HTF forward-fill index
        mtf_idx: Current MTF forward-fill index
    """

    htf_changed: bool
    mtf_changed: bool
    htf_idx: int
    mtf_idx: int


class HTFIndexManager:
    """
    Manages HTF/MTF forward-fill indices for multi-timeframe backtesting.

    This class tracks which bar index to use for HTF/MTF indicators at any
    given exec bar. The indices are "forward-filled" meaning they stay
    constant until the slower TF's bar actually closes.

    Usage:
        manager = HTFIndexManager(htf_feed, mtf_feed, exec_feed)

        for exec_bar in bars:
            update = manager.update_indices(exec_bar.ts_close)
            if update.htf_changed:
                # New HTF bar closed - update incremental structures
                update_htf_incremental_state()

    Thread Safety:
        NOT thread-safe. Use one manager per engine instance.
    """

    def __init__(
        self,
        htf_feed: "FeedStore | None",
        mtf_feed: "FeedStore | None",
        exec_feed: "FeedStore | None",
    ) -> None:
        """
        Initialize HTFIndexManager.

        Args:
            htf_feed: HTF FeedStore (may be None if no HTF)
            mtf_feed: MTF FeedStore (may be None if no MTF)
            exec_feed: Exec FeedStore (required for comparison)
        """
        self._htf_feed = htf_feed
        self._mtf_feed = mtf_feed
        self._exec_feed = exec_feed

        # Current forward-fill indices
        self._current_htf_idx: int = 0
        self._current_mtf_idx: int = 0

    @property
    def htf_idx(self) -> int:
        """Current HTF forward-fill index."""
        return self._current_htf_idx

    @property
    def mtf_idx(self) -> int:
        """Current MTF forward-fill index."""
        return self._current_mtf_idx

    def reset(self) -> None:
        """Reset indices to initial state."""
        self._current_htf_idx = 0
        self._current_mtf_idx = 0

    def update_indices(self, exec_ts_close: datetime) -> HTFIndexUpdate:
        """
        Update HTF/MTF indices based on exec bar close timestamp.

        Uses O(1) lookup via FeedStore.get_idx_at_ts_close() to determine
        if the exec bar's ts_close aligns with an HTF/MTF bar close.

        Args:
            exec_ts_close: Current exec bar's close timestamp

        Returns:
            HTFIndexUpdate with change flags and current indices
        """
        htf_changed = False
        mtf_changed = False

        # Check if HTF bar closed at this exec bar close
        if self._htf_feed is not None and self._htf_feed is not self._exec_feed:
            htf_idx = self._htf_feed.get_idx_at_ts_close(exec_ts_close)
            if htf_idx is not None and 0 <= htf_idx < self._htf_feed.length:
                # Check if this is a NEW HTF bar (index actually changed)
                if htf_idx != self._current_htf_idx:
                    htf_changed = True
                self._current_htf_idx = htf_idx

        # Check if MTF bar closed at this exec bar close
        if self._mtf_feed is not None and self._mtf_feed is not self._exec_feed:
            mtf_idx = self._mtf_feed.get_idx_at_ts_close(exec_ts_close)
            if mtf_idx is not None and 0 <= mtf_idx < self._mtf_feed.length:
                # Check if this is a NEW MTF bar (index actually changed)
                if mtf_idx != self._current_mtf_idx:
                    mtf_changed = True
                self._current_mtf_idx = mtf_idx

        return HTFIndexUpdate(
            htf_changed=htf_changed,
            mtf_changed=mtf_changed,
            htf_idx=self._current_htf_idx,
            mtf_idx=self._current_mtf_idx,
        )

    def set_indices(self, htf_idx: int, mtf_idx: int) -> None:
        """
        Directly set HTF/MTF indices (for state restoration).

        Args:
            htf_idx: HTF index to set
            mtf_idx: MTF index to set
        """
        self._current_htf_idx = htf_idx
        self._current_mtf_idx = mtf_idx


def update_htf_mtf_indices_impl(
    exec_ts_close: datetime,
    htf_feed: "FeedStore | None",
    mtf_feed: "FeedStore | None",
    exec_feed: "FeedStore",
    current_htf_idx: int,
    current_mtf_idx: int,
) -> tuple[bool, bool, int, int]:
    """
    Functional implementation of HTF/MTF index update.

    This is the stateless version used by BacktestEngine via engine_snapshot.py.
    Returns tuple format for backward compatibility.

    Note: The "changed" semantics differ from HTFIndexManager:
    - This returns htf_updated=True when a valid alignment is found
    - HTFIndexManager returns htf_changed=True only when index CHANGES

    The BacktestEngine doesn't need "changed" semantics since it doesn't
    track incremental state per HTF bar. PlayEngine uses HTFIndexManager
    which provides proper "changed" detection.

    Args:
        exec_ts_close: Current exec bar's ts_close
        htf_feed: HTF FeedStore (may be None or same as exec_feed)
        mtf_feed: MTF FeedStore (may be None or same as exec_feed)
        exec_feed: Exec FeedStore
        current_htf_idx: Current HTF index
        current_mtf_idx: Current MTF index

    Returns:
        Tuple of (htf_updated, mtf_updated, new_htf_idx, new_mtf_idx)
    """
    htf_updated = False
    mtf_updated = False
    new_htf_idx = current_htf_idx
    new_mtf_idx = current_mtf_idx

    if htf_feed is not None and htf_feed is not exec_feed:
        # Check if this exec ts_close aligns with an HTF close
        htf_idx = htf_feed.get_idx_at_ts_close(exec_ts_close)
        # Bounds check: index must be valid within feed data
        if htf_idx is not None and 0 <= htf_idx < len(htf_feed.ts_close):
            new_htf_idx = htf_idx
            htf_updated = True

    if mtf_feed is not None and mtf_feed is not exec_feed:
        # Check if this exec ts_close aligns with an MTF close
        mtf_idx = mtf_feed.get_idx_at_ts_close(exec_ts_close)
        # Bounds check: index must be valid within feed data
        if mtf_idx is not None and 0 <= mtf_idx < len(mtf_feed.ts_close):
            new_mtf_idx = mtf_idx
            mtf_updated = True

    return htf_updated, mtf_updated, new_htf_idx, new_mtf_idx
