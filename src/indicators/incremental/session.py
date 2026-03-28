"""
Session-based indicators.

Tracks session boundaries (daily, weekly) and computes previous/current
session highs and lows. Key ICT levels for institutional zone identification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .base import IncrementalIndicator

_MS_PER_DAY = 86_400_000
_MS_PER_WEEK = _MS_PER_DAY * 7


@dataclass
class IncrementalSessionLevels(IncrementalIndicator):
    """
    Previous and current session high/low tracker with O(1) updates.

    Tracks daily and weekly session boundaries using ts_open timestamps.
    At each session boundary, the current session's high/low become the
    previous session's high/low, and the current session resets.

    Requires ts_open (bar open timestamp in milliseconds) to detect
    session crossings. Without ts_open, outputs remain NaN.

    Outputs:
        prev_day_high: Previous day's high price
        prev_day_low: Previous day's low price
        current_day_high: Current day's running high
        current_day_low: Current day's running low
        prev_week_high: Previous week's high price
        prev_week_low: Previous week's low price
    """

    # Daily tracking
    _day_boundary: int = field(default=-1, init=False)
    _current_day_high: float = field(default=np.nan, init=False)
    _current_day_low: float = field(default=np.nan, init=False)
    _prev_day_high: float = field(default=np.nan, init=False)
    _prev_day_low: float = field(default=np.nan, init=False)

    # Weekly tracking
    _week_boundary: int = field(default=-1, init=False)
    _current_week_high: float = field(default=np.nan, init=False)
    _current_week_low: float = field(default=np.nan, init=False)
    _prev_week_high: float = field(default=np.nan, init=False)
    _prev_week_low: float = field(default=np.nan, init=False)

    _count: int = field(default=0, init=False)
    _has_prev_day: bool = field(default=False, init=False)
    _has_prev_week: bool = field(default=False, init=False)

    def update(
        self, high: float, low: float, close: float, volume: float, **kwargs: Any
    ) -> None:
        """Update session levels with new bar data.

        Args:
            high: Bar high price.
            low: Bar low price.
            close: Bar close price (unused, required by interface).
            volume: Bar volume (unused, required by interface).
            ts_open: Bar open timestamp in milliseconds (required for session detection).
        """
        self._count += 1

        if np.isnan(high) or np.isnan(low):
            return

        ts_open = kwargs.get("ts_open")
        if ts_open is None:
            # Without timestamps, just track running high/low but no session boundaries
            if np.isnan(self._current_day_high):
                self._current_day_high = high
                self._current_day_low = low
            else:
                self._current_day_high = max(self._current_day_high, high)
                self._current_day_low = min(self._current_day_low, low)
            return

        ts = int(ts_open)

        # Daily boundary detection
        day_id = ts // _MS_PER_DAY
        if day_id != self._day_boundary:
            if self._day_boundary >= 0:
                # Roll: current becomes previous
                self._prev_day_high = self._current_day_high
                self._prev_day_low = self._current_day_low
                self._has_prev_day = True
            self._day_boundary = day_id
            self._current_day_high = high
            self._current_day_low = low
        else:
            self._current_day_high = max(self._current_day_high, high)
            self._current_day_low = min(self._current_day_low, low)

        # Weekly boundary detection (Monday-based, matching VWAP)
        week_id = (ts + 3 * _MS_PER_DAY) // _MS_PER_WEEK
        if week_id != self._week_boundary:
            if self._week_boundary >= 0:
                self._prev_week_high = self._current_week_high
                self._prev_week_low = self._current_week_low
                self._has_prev_week = True
            self._week_boundary = week_id
            self._current_week_high = high
            self._current_week_low = low
        else:
            self._current_week_high = max(self._current_week_high, high)
            self._current_week_low = min(self._current_week_low, low)

    def reset(self) -> None:
        self._day_boundary = -1
        self._current_day_high = np.nan
        self._current_day_low = np.nan
        self._prev_day_high = np.nan
        self._prev_day_low = np.nan
        self._week_boundary = -1
        self._current_week_high = np.nan
        self._current_week_low = np.nan
        self._prev_week_high = np.nan
        self._prev_week_low = np.nan
        self._count = 0
        self._has_prev_day = False
        self._has_prev_week = False

    @property
    def value(self) -> float:
        """Primary output: previous day high."""
        return self._prev_day_high

    @property
    def prev_day_high(self) -> float:
        return self._prev_day_high

    @property
    def prev_day_low(self) -> float:
        return self._prev_day_low

    @property
    def current_day_high(self) -> float:
        return self._current_day_high

    @property
    def current_day_low(self) -> float:
        return self._current_day_low

    @property
    def prev_week_high(self) -> float:
        return self._prev_week_high

    @property
    def prev_week_low(self) -> float:
        return self._prev_week_low

    @property
    def is_ready(self) -> bool:
        return self._has_prev_day
