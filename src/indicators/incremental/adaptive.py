"""
Complex adaptive indicators with dynamic smoothing parameters.

Includes KAMA, ALMA, ZLMA, and UO -- indicators that adapt their
behavior based on market conditions or use non-standard weighting.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .base import IncrementalIndicator
from .core import IncrementalEMA


@dataclass
class IncrementalKAMA(IncrementalIndicator):
    """
    Kaufman Adaptive Moving Average with O(1) updates.

    Formula (matching pandas_ta):
        change = abs(close - close[length])
        volatility = sum(abs(close[i] - close[i-1])) over length bars
        er = change / volatility (efficiency ratio)
        sc = (er * (fast_sc - slow_sc) + slow_sc)^2
        kama = prev_kama + sc * (close - prev_kama)

    First KAMA value at index length-1 is SMA of first length closes.
    """

    length: int = 10
    fast: int = 2
    slow: int = 30
    _buffer: deque = field(default_factory=deque, init=False)
    _change_buffer: deque = field(default_factory=deque, init=False)
    _change_sum: float = field(default=0.0, init=False)
    _kama: float = field(default=np.nan, init=False)
    _count: int = field(default=0, init=False)
    _fast_sc: float = field(init=False)
    _slow_sc: float = field(init=False)

    def __post_init__(self) -> None:
        self._fast_sc = 2.0 / (self.fast + 1)
        self._slow_sc = 2.0 / (self.slow + 1)

    def update(self, close: float, **kwargs: Any) -> None:
        """Update with new close price."""
        self._count += 1

        # Track bar-to-bar changes (peer_diff in pandas_ta)
        if len(self._buffer) > 0:
            change = abs(close - self._buffer[-1])
            self._change_sum += change
            self._change_buffer.append(change)

            if len(self._change_buffer) > self.length:
                oldest = self._change_buffer.popleft()
                self._change_sum -= oldest

        self._buffer.append(close)

        # Keep buffer size at length + 1 to access close[i-length]
        if len(self._buffer) > self.length + 1:
            self._buffer.popleft()

        # Compute KAMA when we have enough data
        if len(self._buffer) == self.length:
            # First KAMA value: SMA of first 'length' closes
            self._kama = sum(self._buffer) / self.length
        elif len(self._buffer) > self.length:
            # Efficiency Ratio: abs(close - close[length bars ago])
            price_change = abs(close - self._buffer[0])
            if self._change_sum == 0:
                er = 0.0
            else:
                er = price_change / self._change_sum

            # Smoothing Constant
            sc = (er * (self._fast_sc - self._slow_sc) + self._slow_sc) ** 2

            # KAMA update
            self._kama = self._kama + sc * (close - self._kama)

    def reset(self) -> None:
        self._buffer.clear()
        self._change_buffer.clear()
        self._change_sum = 0.0
        self._kama = np.nan
        self._count = 0

    @property
    def value(self) -> float:
        return self._kama

    @property
    def is_ready(self) -> bool:
        return not np.isnan(self._kama)


@dataclass
class IncrementalALMA(IncrementalIndicator):
    """
    Arnaud Legoux Moving Average with O(1) update, O(n) value access.

    Formula (matching pandas_ta):
        k = floor(offset * (length - 1))
        weight[i] = exp(-0.5 * ((sigma / length) * (i - k))^2)

    Note: ALMA uses position-based Gaussian weights. Unlike linear-weighted
    averages (WMA), when values shift positions, their weights change non-linearly.
    This makes true O(1) weighted sum tracking mathematically impossible.
    The update() is O(1), only value access is O(n).

    Matches pandas_ta.alma() output.
    """

    length: int = 10
    sigma: float = 6.0
    offset: float = 0.85
    _buffer: deque = field(default_factory=deque, init=False)
    _weights: np.ndarray = field(init=False)
    _count: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        # Precompute weights (matching pandas_ta formula)
        k = int(np.floor(self.offset * (self.length - 1)))
        x = np.arange(self.length)
        self._weights = np.exp(-0.5 * ((self.sigma / self.length) * (x - k)) ** 2)
        self._weights = self._weights / self._weights.sum()  # Normalize

    def update(self, close: float, **kwargs: Any) -> None:
        """Update with new close price - O(1) operation."""
        self._count += 1
        self._buffer.append(close)

        if len(self._buffer) > self.length:
            self._buffer.popleft()

    def reset(self) -> None:
        self._buffer.clear()
        self._count = 0

    @property
    def value(self) -> float:
        """O(n) weighted sum calculation - cannot be optimized further."""
        if not self.is_ready:
            return np.nan

        # Weights already normalized in __post_init__
        return float(np.dot(self._weights, list(self._buffer)))

    @property
    def is_ready(self) -> bool:
        return len(self._buffer) >= self.length


@dataclass
class IncrementalZLMA(IncrementalIndicator):
    """
    Zero Lag Moving Average with O(1) updates.

    Formula:
        lag = (length - 1) / 2
        zlma = ema(2 * close - close[lag])

    Matches pandas_ta.zlma() output.
    """

    length: int = 20
    _buffer: deque = field(default_factory=deque, init=False)
    _ema: IncrementalEMA = field(init=False)
    _lag: int = field(init=False)
    _count: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self._lag = (self.length - 1) // 2
        self._ema = IncrementalEMA(length=self.length)

    def update(self, close: float, **kwargs: Any) -> None:
        """Update with new close price."""
        self._count += 1
        self._buffer.append(close)

        if len(self._buffer) > self._lag + 1:
            self._buffer.popleft()

        # Compute lag-adjusted value
        if len(self._buffer) > self._lag:
            lagged = self._buffer[0]
            adjusted = 2 * close - lagged
            self._ema.update(close=adjusted)

    def reset(self) -> None:
        self._buffer.clear()
        self._ema.reset()
        self._count = 0

    @property
    def value(self) -> float:
        if not self.is_ready:
            return np.nan
        return self._ema.value

    @property
    def is_ready(self) -> bool:
        return self._ema.is_ready


@dataclass
class IncrementalUO(IncrementalIndicator):
    """
    Ultimate Oscillator with O(1) updates.

    Formula:
        bp = close - min(low, prev_close)  # Buying Pressure
        tr = max(high, prev_close) - min(low, prev_close)  # True Range
        avg1 = sum(bp, fast) / sum(tr, fast)
        avg2 = sum(bp, medium) / sum(tr, medium)
        avg3 = sum(bp, slow) / sum(tr, slow)
        uo = 100 * ((4 * avg1) + (2 * avg2) + avg3) / 7

    Matches pandas_ta.uo() output.
    """

    fast: int = 7
    medium: int = 14
    slow: int = 28
    _prev_close: float = field(default=np.nan, init=False)
    _bp_buffer: deque = field(default_factory=deque, init=False)
    _tr_buffer: deque = field(default_factory=deque, init=False)
    _count: int = field(default=0, init=False)

    def update(
        self, high: float, low: float, close: float, **kwargs: Any
    ) -> None:
        """Update with new HLC data."""
        self._count += 1

        if self._count == 1:
            self._prev_close = close
            return

        # Buying Pressure and True Range
        bp = close - min(low, self._prev_close)
        tr = max(high, self._prev_close) - min(low, self._prev_close)

        self._prev_close = close

        self._bp_buffer.append(bp)
        self._tr_buffer.append(tr)

        if len(self._bp_buffer) > self.slow:
            self._bp_buffer.popleft()
            self._tr_buffer.popleft()

    def reset(self) -> None:
        self._prev_close = np.nan
        self._bp_buffer.clear()
        self._tr_buffer.clear()
        self._count = 0

    @property
    def value(self) -> float:
        if not self.is_ready:
            return np.nan

        bp_list = list(self._bp_buffer)
        tr_list = list(self._tr_buffer)
        n = len(bp_list)

        # Get sums for each period
        bp_fast = sum(bp_list[n - self.fast :])
        tr_fast = sum(tr_list[n - self.fast :])
        bp_med = sum(bp_list[n - self.medium :])
        tr_med = sum(tr_list[n - self.medium :])
        bp_slow = sum(bp_list)
        tr_slow = sum(tr_list)

        # Avoid division by zero
        avg1 = bp_fast / tr_fast if tr_fast != 0 else 0
        avg2 = bp_med / tr_med if tr_med != 0 else 0
        avg3 = bp_slow / tr_slow if tr_slow != 0 else 0

        return 100 * ((4 * avg1) + (2 * avg2) + avg3) / 7

    @property
    def is_ready(self) -> bool:
        return len(self._bp_buffer) >= self.slow
