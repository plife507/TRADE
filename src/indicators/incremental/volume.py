"""
Volume-based complex indicators.

Includes KVO, VWAP, and AnchoredVWAP -- indicators that incorporate
volume data in their calculations.
"""

from __future__ import annotations

from collections import deque
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


@dataclass
class IncrementalVolumeProfile(IncrementalIndicator):
    """
    Incremental Volume Profile with O(buckets) updates.

    Distributes volume across price buckets over a rolling lookback window.
    Computes Point of Control (POC), Value Area High/Low (VAH/VAL), and
    price position relative to these levels.

    Algorithm:
        1. Each bar distributes its volume across buckets spanned by [low, high]
        2. A deque tracks per-bar contributions for rolling eviction
        3. When price exceeds the tracked range by 10%+, buckets are lazily rebinned
        4. POC = price level of the bucket with highest volume
        5. Value Area = smallest set of contiguous buckets around POC
           containing value_area_pct of total volume

    Params:
        num_buckets: Number of price buckets (default: 50)
        lookback: Rolling window in bars (default: 50)
        value_area_pct: Fraction of volume defining the value area (default: 0.70)
    """

    num_buckets: int = 50
    lookback: int = 50
    value_area_pct: float = 0.70

    _count: int = field(default=0, init=False)
    _bucket_volumes: np.ndarray = field(init=False)
    _range_low: float = field(default=np.nan, init=False)
    _range_high: float = field(default=np.nan, init=False)
    _bucket_width: float = field(default=0.0, init=False)
    _bar_contributions: deque = field(init=False)

    _poc: float = field(default=np.nan, init=False)
    _vah: float = field(default=np.nan, init=False)
    _val: float = field(default=np.nan, init=False)
    _poc_volume: float = field(default=np.nan, init=False)
    _above_poc: bool = field(default=False, init=False)
    _in_value_area: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self._bucket_volumes = np.zeros(self.num_buckets)
        self._bar_contributions = deque(maxlen=self.lookback)

    def update(
        self, high: float, low: float, close: float, volume: float, **kwargs: Any
    ) -> None:
        """Update volume profile with new bar data."""
        self._count += 1

        if np.isnan(high) or np.isnan(low) or np.isnan(close) or np.isnan(volume):
            self._bar_contributions.append((np.array([], dtype=int), np.array([])))
            self._recompute_outputs(close)
            return

        if volume <= 0:
            self._bar_contributions.append((np.array([], dtype=int), np.array([])))
            self._recompute_outputs(close)
            return

        # Initialize range on first valid bar
        if np.isnan(self._range_low):
            spread = high - low
            if spread <= 0:
                spread = high * 0.01
            self._range_low = low - spread * 2
            self._range_high = high + spread * 2
            self._bucket_width = (self._range_high - self._range_low) / self.num_buckets

        # Lazy rebinning: only when price exceeds range by 10%+
        current_range = self._range_high - self._range_low
        if high > self._range_high or low < self._range_low:
            overshoot = max(
                (high - self._range_high) / current_range if high > self._range_high else 0,
                (self._range_low - low) / current_range if low < self._range_low else 0,
            )
            if overshoot > 0.10:
                self._rebin(low, high)

        # Distribute volume across touched buckets
        lo_bucket = self._price_to_bucket(low)
        hi_bucket = self._price_to_bucket(high)
        n_touched = hi_bucket - lo_bucket + 1
        vol_per_bucket = volume / max(n_touched, 1)

        indices = np.arange(lo_bucket, hi_bucket + 1, dtype=int)
        volumes_arr = np.full(len(indices), vol_per_bucket)

        # Evict oldest bar if at capacity
        if len(self._bar_contributions) == self.lookback:
            old_indices, old_volumes = self._bar_contributions[0]
            if len(old_indices) > 0:
                self._bucket_volumes[old_indices] -= old_volumes
                self._bucket_volumes[old_indices] = np.maximum(
                    0, self._bucket_volumes[old_indices]
                )

        self._bucket_volumes[indices] += volumes_arr
        self._bar_contributions.append((indices, volumes_arr))
        self._recompute_outputs(close)

    def _price_to_bucket(self, price: float) -> int:
        if self._bucket_width <= 0:
            return 0
        idx = int((price - self._range_low) / self._bucket_width)
        return max(0, min(self.num_buckets - 1, idx))

    def _bucket_to_price(self, bucket: int) -> float:
        return self._range_low + (bucket + 0.5) * self._bucket_width

    def _rebin(self, new_low: float, new_high: float) -> None:
        """Rebin buckets to cover new price range."""
        spread = new_high - new_low
        if spread <= 0:
            spread = new_high * 0.01
        new_range_low = new_low - spread * 0.5
        new_range_high = new_high + spread * 0.5
        new_width = (new_range_high - new_range_low) / self.num_buckets

        new_buckets = np.zeros(self.num_buckets)
        new_contributions: deque = deque(maxlen=self.lookback)

        for old_indices, old_volumes in self._bar_contributions:
            if len(old_indices) == 0:
                new_contributions.append((np.array([], dtype=int), np.array([])))
                continue
            new_bar_indices = []
            new_bar_volumes = []
            for j, vol in zip(old_indices, old_volumes):
                price = self._bucket_to_price(j)
                new_idx = int((price - new_range_low) / new_width)
                new_idx = max(0, min(self.num_buckets - 1, new_idx))
                new_buckets[new_idx] += vol
                new_bar_indices.append(new_idx)
                new_bar_volumes.append(vol)
            new_contributions.append(
                (np.array(new_bar_indices, dtype=int), np.array(new_bar_volumes))
            )

        self._range_low = new_range_low
        self._range_high = new_range_high
        self._bucket_width = new_width
        self._bucket_volumes = new_buckets
        self._bar_contributions = new_contributions

    def _recompute_outputs(self, close: float) -> None:
        """Recompute POC, VAH, VAL from current bucket volumes."""
        total_vol = self._bucket_volumes.sum()
        if total_vol <= 0 or self._count < 2:
            self._poc = np.nan
            self._vah = np.nan
            self._val = np.nan
            self._poc_volume = np.nan
            self._above_poc = False
            self._in_value_area = False
            return

        poc_bucket = int(np.argmax(self._bucket_volumes))
        self._poc = self._bucket_to_price(poc_bucket)
        self._poc_volume = float(self._bucket_volumes[poc_bucket])

        # Value Area: expand outward from POC
        target_vol = total_vol * self.value_area_pct
        va_low = poc_bucket
        va_high = poc_bucket
        accumulated = float(self._bucket_volumes[poc_bucket])

        while accumulated < target_vol:
            expand_low = (
                float(self._bucket_volumes[va_low - 1]) if va_low > 0 else 0.0
            )
            expand_high = (
                float(self._bucket_volumes[va_high + 1])
                if va_high < self.num_buckets - 1
                else 0.0
            )
            if expand_low == 0 and expand_high == 0:
                break
            if expand_high >= expand_low:
                va_high += 1
                accumulated += expand_high
            else:
                va_low -= 1
                accumulated += expand_low

        self._vah = self._bucket_to_price(va_high)
        self._val = self._bucket_to_price(va_low)
        self._above_poc = close > self._poc
        self._in_value_area = self._val <= close <= self._vah

    def reset(self) -> None:
        self._count = 0
        self._bucket_volumes = np.zeros(self.num_buckets)
        self._bar_contributions = deque(maxlen=self.lookback)
        self._range_low = np.nan
        self._range_high = np.nan
        self._bucket_width = 0.0
        self._poc = np.nan
        self._vah = np.nan
        self._val = np.nan
        self._poc_volume = np.nan
        self._above_poc = False
        self._in_value_area = False

    @property
    def value(self) -> float:
        """Primary output: POC price level."""
        return self._poc

    @property
    def poc(self) -> float:
        return self._poc

    @property
    def vah(self) -> float:
        return self._vah

    @property
    def val(self) -> float:
        return self._val

    @property
    def poc_volume(self) -> float:
        return self._poc_volume

    @property
    def above_poc(self) -> float:
        """1.0 if close > POC, 0.0 otherwise."""
        return 1.0 if self._above_poc else 0.0

    @property
    def in_value_area(self) -> float:
        """1.0 if close within VAL-VAH, 0.0 otherwise."""
        return 1.0 if self._in_value_area else 0.0

    @property
    def is_ready(self) -> bool:
        return self._count >= 2 and not np.isnan(self._poc)
