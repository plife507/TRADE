"""
Volume-based complex indicators.

Includes KVO, VWAP, and AnchoredVWAP -- indicators that incorporate
volume data in their calculations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .base import IncrementalIndicator
from .core import IncrementalEMA


@dataclass
class IncrementalKVO(IncrementalIndicator):
    """
    Klinger Volume Oscillator with O(1) updates.

    Formula (matching pandas_ta):
        hlc3 = (high + low + close) / 3
        sign = +1 if hlc3 > prev_hlc3 else -1 (first is -1)
        signed_volume = volume * sign
        kvo = ema(signed_volume, fast) - ema(signed_volume, slow)
        signal = ema(kvo, signal_length)

    pandas_ta uses signed_series(hlc3, initial=-1) to compute sign.
    """

    fast: int = 34
    slow: int = 55
    signal: int = 13
    _prev_hlc3: float = field(default=np.nan, init=False)
    _ema_fast: IncrementalEMA = field(init=False)
    _ema_slow: IncrementalEMA = field(init=False)
    _ema_signal: IncrementalEMA = field(init=False)
    _kvo_value: float = field(default=np.nan, init=False)
    _signal_line: float = field(default=np.nan, init=False)
    _count: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self._ema_fast = IncrementalEMA(length=self.fast)
        self._ema_slow = IncrementalEMA(length=self.slow)
        self._ema_signal = IncrementalEMA(length=self.signal)

    def update(
        self, high: float, low: float, close: float, volume: float, **kwargs: Any
    ) -> None:
        """Update with new OHLCV data."""
        self._count += 1

        hlc3 = (high + low + close) / 3.0

        if self._count == 1:
            # First bar: pandas_ta signed_series returns NaN (no prev to compare)
            # Don't update EMAs with first bar
            self._prev_hlc3 = hlc3
            return

        # Subsequent: sign based on change
        diff = hlc3 - self._prev_hlc3
        if diff > 0:
            sign = 1.0
        elif diff < 0:
            sign = -1.0
        else:
            sign = 0.0  # No change = 0

        self._prev_hlc3 = hlc3

        # Signed volume
        signed_volume = volume * sign

        # Update EMAs with signed volume
        self._ema_fast.update(close=signed_volume)
        self._ema_slow.update(close=signed_volume)

        if self._ema_fast.is_ready and self._ema_slow.is_ready:
            self._kvo_value = self._ema_fast.value - self._ema_slow.value
            self._ema_signal.update(close=self._kvo_value)

            if self._ema_signal.is_ready:
                self._signal_line = self._ema_signal.value

    def reset(self) -> None:
        self._prev_hlc3 = np.nan
        self._ema_fast.reset()
        self._ema_slow.reset()
        self._ema_signal.reset()
        self._kvo_value = np.nan
        self._signal_line = np.nan
        self._count = 0

    @property
    def value(self) -> float:
        """Returns KVO value."""
        return self._kvo_value

    @property
    def kvo_value(self) -> float:
        """Returns KVO value."""
        return self._kvo_value

    @property
    def signal_value(self) -> float:
        """Returns signal line value."""
        return self._signal_line

    @property
    def is_ready(self) -> bool:
        return not np.isnan(self._kvo_value)


@dataclass
class IncrementalVWAP(IncrementalIndicator):
    """
    Volume Weighted Average Price with O(1) updates.

    Formula:
        vwap = cumsum(typical_price * volume) / cumsum(volume)
        where typical_price = (high + low + close) / 3

    Supports session-boundary resets via the `anchor` parameter:
    - anchor="D": Reset at daily boundaries (default, matches pandas_ta)
    - anchor="W": Reset at weekly boundaries
    - anchor=None: Cumulative (no reset)

    When ts_open is passed to update(), the indicator detects session
    crossings and resets automatically.

    Matches pandas_ta.vwap() output when anchor="D".
    """

    anchor: str | None = "D"
    _cum_tp_vol: float = field(default=0.0, init=False)
    _cum_vol: float = field(default=0.0, init=False)
    _count: int = field(default=0, init=False)
    _last_reset_boundary: int = field(default=-1, init=False)

    def update(
        self, high: float, low: float, close: float, volume: float, **kwargs: Any
    ) -> None:
        """Update with new OHLCV data.

        Args:
            high: High price
            low: Low price
            close: Close price
            volume: Volume
            ts_open: Bar open timestamp in milliseconds (optional, for session resets)
        """
        # Check for session boundary reset
        ts_open = kwargs.get("ts_open")
        if ts_open is not None and self.anchor:
            boundary = self._get_boundary(int(ts_open))
            if boundary != self._last_reset_boundary and self._last_reset_boundary >= 0:
                # Session crossed - reset accumulation
                self._cum_tp_vol = 0.0
                self._cum_vol = 0.0
            self._last_reset_boundary = boundary

        self._count += 1

        # Guard: skip NaN inputs to prevent permanent poisoning of cumulative sums
        if np.isnan(high) or np.isnan(low) or np.isnan(close) or np.isnan(volume):
            return

        tp = (high + low + close) / 3.0
        self._cum_tp_vol += tp * volume
        self._cum_vol += volume

    def _get_boundary(self, ts_ms: int) -> int:
        """Get session boundary identifier from timestamp.

        Returns an integer that changes when the session boundary crosses.
        For daily anchor, returns the day number (ts_ms // ms_per_day).
        For weekly anchor, returns the ISO week number (Monday-based).
        """
        ms_per_day = 86_400_000
        if self.anchor == "D":
            return ts_ms // ms_per_day
        elif self.anchor == "W":
            # ISO week boundary (Monday-based).
            # Unix epoch (1970-01-01) is a Thursday (day 0). Adding 3 days
            # shifts so that the 7-day division boundary falls on Monday.
            return (ts_ms + 3 * ms_per_day) // (ms_per_day * 7)
        raise ValueError(f"Unknown VWAP anchor: {self.anchor!r}. Use 'D', 'W', or None.")

    def reset(self) -> None:
        """Reset VWAP (call at session boundaries)."""
        self._cum_tp_vol = 0.0
        self._cum_vol = 0.0
        self._count = 0
        self._last_reset_boundary = -1

    @property
    def value(self) -> float:
        if not self.is_ready:
            return np.nan

        if self._cum_vol == 0:
            return np.nan

        return self._cum_tp_vol / self._cum_vol

    @property
    def is_ready(self) -> bool:
        return self._count >= 1


@dataclass
class IncrementalAnchoredVWAP(IncrementalIndicator):
    """
    Anchored VWAP that resets on structure events (swing pivots).

    Unlike session VWAP which resets on time boundaries, anchored VWAP
    resets when a structure event occurs (e.g., swing high/low confirmed).

    Anchor sources (raw pivot-based):
    - "swing_high": Reset when a new swing high is confirmed
    - "swing_low": Reset when a new swing low is confirmed
    - "swing_any": Reset on any swing pivot
    - "manual": Reset only when reset() is called explicitly

    Anchor sources (pair-based, recommended):
    - "pair_high": Reset when a complete pair ends on a high (bullish L->H)
    - "pair_low": Reset when a complete pair ends on a low (bearish H->L)
    - "pair_any": Reset on any complete swing pair

    Pair-based sources use pair_version which only increments on complete
    H-L swing pairs, avoiding resets on consecutive same-type pivots.

    Outputs:
    - value: Current anchored VWAP price
    - bars_since_anchor: Number of bars since last reset
    """

    anchor_source: str = "swing_any"
    _cum_tp_vol: float = field(default=0.0, init=False)
    _cum_vol: float = field(default=0.0, init=False)
    _count: int = field(default=0, init=False)
    _bars_since_anchor: int = field(default=0, init=False)
    _last_swing_high_ver: int = field(default=-1, init=False)
    _last_swing_low_ver: int = field(default=-1, init=False)
    _last_pair_version: int = field(default=-1, init=False)

    def update(
        self, high: float, low: float, close: float, volume: float, **kwargs: Any
    ) -> None:
        """Update with new OHLCV data.

        Args:
            high: High price
            low: Low price
            close: Close price
            volume: Volume
            swing_high_version: Version counter for swing high confirmations
            swing_low_version: Version counter for swing low confirmations
            swing_pair_version: Pair version (increments on complete H-L pairs)
            swing_pair_direction: Pair direction ("bullish" or "bearish")
        """
        # Check for anchor event (swing pivot confirmed)
        should_reset = False

        if self.anchor_source in ("pair_high", "pair_low", "pair_any"):
            # Pair-based anchoring: only reset on complete swing pairs
            pair_ver = kwargs.get("swing_pair_version", -1)
            pair_dir = kwargs.get("swing_pair_direction", "")
            if pair_ver > self._last_pair_version and self._last_pair_version >= 0:
                if self.anchor_source == "pair_any":
                    should_reset = True
                elif self.anchor_source == "pair_high" and pair_dir == "bullish":
                    should_reset = True  # Bullish pair = L->H = high is completing pivot
                elif self.anchor_source == "pair_low" and pair_dir == "bearish":
                    should_reset = True  # Bearish pair = H->L = low is completing pivot
            if pair_ver >= 0:
                self._last_pair_version = pair_ver
        else:
            # Raw pivot-based anchoring
            swing_high_ver = kwargs.get("swing_high_version", -1)
            swing_low_ver = kwargs.get("swing_low_version", -1)

            if self.anchor_source in ("swing_high", "swing_any"):
                if swing_high_ver > self._last_swing_high_ver and self._last_swing_high_ver >= 0:
                    should_reset = True
            if self.anchor_source in ("swing_low", "swing_any"):
                if swing_low_ver > self._last_swing_low_ver and self._last_swing_low_ver >= 0:
                    should_reset = True

            if swing_high_ver >= 0:
                self._last_swing_high_ver = swing_high_ver
            if swing_low_ver >= 0:
                self._last_swing_low_ver = swing_low_ver

        if should_reset:
            self._cum_tp_vol = 0.0
            self._cum_vol = 0.0
            self._bars_since_anchor = 0

        self._count += 1
        self._bars_since_anchor += 1

        # Guard: skip NaN inputs to prevent permanent poisoning of cumulative sums
        if np.isnan(high) or np.isnan(low) or np.isnan(close) or np.isnan(volume):
            return

        tp = (high + low + close) / 3.0
        self._cum_tp_vol += tp * volume
        self._cum_vol += volume

    def reset(self) -> None:
        """Reset anchored VWAP."""
        self._cum_tp_vol = 0.0
        self._cum_vol = 0.0
        self._count = 0
        self._bars_since_anchor = 0
        self._last_swing_high_ver = -1
        self._last_swing_low_ver = -1
        self._last_pair_version = -1

    @property
    def value(self) -> float:
        if not self.is_ready:
            return np.nan
        if self._cum_vol == 0:
            return np.nan
        return self._cum_tp_vol / self._cum_vol

    @property
    def bars_since_anchor(self) -> int:
        """Number of bars since last anchor reset."""
        return self._bars_since_anchor

    @property
    def is_ready(self) -> bool:
        return self._count >= 1
