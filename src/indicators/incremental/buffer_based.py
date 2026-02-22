"""
SMA/Buffer-based indicators using ring buffers and running sums.

Includes WMA, TRIMA, LINREG, CMF, CMO, and MFI -- indicators that
maintain sliding windows of historical values.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .base import IncrementalIndicator
from .core import IncrementalSMA


@dataclass
class IncrementalWMA(IncrementalIndicator):
    """
    Weighted Moving Average with TRUE O(1) updates.

    Formula:
        wma = sum(weight[i] * close[i]) / sum(weights)
        where weight[i] = i + 1 (linear weights, most recent has highest weight)

    O(1) update technique:
        - New value enters with weight `length` (highest)
        - All existing values shift down, losing 1 from their weight
        - weighted_sum = weighted_sum - buffer_sum + new_value * length
        - When oldest leaves (had weight 1), subtract it from buffer_sum

    Matches pandas_ta.wma() output.
    """

    length: int = 20
    _buffer: deque = field(default_factory=deque, init=False)
    _count: int = field(default=0, init=False)
    _weight_divisor: int = field(default=0, init=False)
    _weighted_sum: float = field(default=0.0, init=False)
    _buffer_sum: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        # Weight divisor = 1 + 2 + ... + length = length * (length + 1) / 2
        self._weight_divisor = self.length * (self.length + 1) // 2

    def update(self, close: float, **kwargs: Any) -> None:
        """Update with new close price - O(1) operation."""
        self._count += 1

        if len(self._buffer) < self.length:
            # Warmup phase: build up buffer
            self._buffer.append(close)
            self._buffer_sum += close
            # Incrementally build weighted sum
            # New value gets weight equal to current buffer length
            self._weighted_sum += close * len(self._buffer)
        else:
            # Steady state: O(1) update
            oldest = self._buffer.popleft()
            self._buffer.append(close)

            # O(1) WMA update:
            # - Remove oldest (had weight 1): subtract oldest from weighted_sum
            # - Shift all remaining down by 1 weight: subtract buffer_sum (BEFORE modification)
            # - Add new value with highest weight: add close * length
            self._weighted_sum = self._weighted_sum - self._buffer_sum + close * self.length

            # Update buffer_sum: remove oldest, add new
            self._buffer_sum = self._buffer_sum - oldest + close

    def reset(self) -> None:
        self._buffer.clear()
        self._count = 0
        self._weighted_sum = 0.0
        self._buffer_sum = 0.0

    @property
    def value(self) -> float:
        if not self.is_ready:
            return np.nan
        return self._weighted_sum / self._weight_divisor

    @property
    def is_ready(self) -> bool:
        return len(self._buffer) >= self.length


@dataclass
class IncrementalTRIMA(IncrementalIndicator):
    """
    Triangular Moving Average with O(1) updates.

    Formula (matching pandas_ta):
        half_length = round(0.5 * (length + 1))
        trima = sma(sma(close, half_length), half_length)

    Uses two incremental SMAs with identical window sizes.
    Matches pandas_ta.trima(talib=False) output.
    """

    length: int = 20
    _sma1: IncrementalSMA = field(init=False)
    _sma2: IncrementalSMA = field(init=False)
    _count: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        # pandas_ta uses round(0.5 * (length + 1)) for both SMA windows
        half_length = round(0.5 * (self.length + 1))
        self._sma1 = IncrementalSMA(length=half_length)
        self._sma2 = IncrementalSMA(length=half_length)

    def update(self, close: float, **kwargs: Any) -> None:
        """Update with new close price."""
        self._count += 1
        self._sma1.update(close=close)

        if self._sma1.is_ready:
            self._sma2.update(close=self._sma1.value)

    def reset(self) -> None:
        self._sma1.reset()
        self._sma2.reset()
        self._count = 0

    @property
    def value(self) -> float:
        if not self.is_ready:
            return np.nan
        return self._sma2.value

    @property
    def is_ready(self) -> bool:
        return self._sma2.is_ready


@dataclass
class IncrementalLINREG(IncrementalIndicator):
    """
    Linear Regression with TRUE O(1) updates using running sums.

    O(1) update technique:
        - Track sum_y incrementally (add new, subtract oldest)
        - Track sum_xy incrementally:
          * When oldest leaves (index 0), it contributes 0 to sum_xy
          * Remaining values shift down 1 position: sum_xy -= sum_y
          * New value enters at index (n-1): sum_xy += new_val * (n-1)

    Matches pandas_ta.linreg() output.
    """

    length: int = 14
    _buffer: deque = field(default_factory=deque, init=False)
    _count: int = field(default=0, init=False)
    _sum_y: float = field(default=0.0, init=False)
    _sum_xy: float = field(default=0.0, init=False)
    # Precomputed constants
    _sum_x: float = field(default=0.0, init=False)
    _sum_xx: float = field(default=0.0, init=False)
    _denominator: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        n = self.length
        # Precompute constants (these never change)
        self._sum_x = (n - 1) * n / 2.0  # 0 + 1 + ... + (n-1)
        self._sum_xx = (n - 1) * n * (2 * n - 1) / 6.0  # Sum of squares
        self._denominator = n * self._sum_xx - self._sum_x * self._sum_x

    def update(self, close: float, **kwargs: Any) -> None:
        """Update with new close price - O(1) operation."""
        self._count += 1

        if len(self._buffer) < self.length:
            # Warmup phase: build incrementally
            current_idx = len(self._buffer)
            self._buffer.append(close)
            self._sum_y += close
            self._sum_xy += current_idx * close
        else:
            # Steady state: O(1) update
            oldest = self._buffer.popleft()
            self._buffer.append(close)

            # Oldest was at index 0, contributed 0 to sum_xy
            self._sum_y -= oldest

            # All remaining shift down 1 position: sum_xy decreases by sum of remaining values
            # But we already removed oldest from sum_y, so use current sum_y
            self._sum_xy -= self._sum_y

            # Add new value at index (length - 1)
            self._sum_y += close
            self._sum_xy += close * (self.length - 1)

    def reset(self) -> None:
        self._buffer.clear()
        self._count = 0
        self._sum_y = 0.0
        self._sum_xy = 0.0

    @property
    def value(self) -> float:
        if not self.is_ready:
            return np.nan

        n = self.length

        if self._denominator == 0:
            return self._buffer[-1]  # Fallback to last value

        # b = (n*sum_xy - sum_x*sum_y) / denominator
        b = (n * self._sum_xy - self._sum_x * self._sum_y) / self._denominator
        # a = (sum_y - b*sum_x) / n
        a = (self._sum_y - b * self._sum_x) / n

        # Value at last point (x = n - 1)
        return a + b * (n - 1)

    @property
    def is_ready(self) -> bool:
        return len(self._buffer) >= self.length


@dataclass
class IncrementalCMF(IncrementalIndicator):
    """
    Chaikin Money Flow with O(1) updates.

    Formula:
        mfv = ((close - low) - (high - close)) / (high - low) * volume
        cmf = sum(mfv over length) / sum(volume over length)

    Matches pandas_ta.cmf() output.
    """

    length: int = 20
    _mfv_buffer: deque = field(default_factory=deque, init=False)
    _vol_buffer: deque = field(default_factory=deque, init=False)
    _mfv_sum: float = field(default=0.0, init=False)
    _vol_sum: float = field(default=0.0, init=False)
    _count: int = field(default=0, init=False)

    def update(
        self, high: float, low: float, close: float, volume: float, **kwargs: Any
    ) -> None:
        """Update with new OHLCV data."""
        self._count += 1

        # Money Flow Multiplier
        hl_range = high - low
        if hl_range == 0:
            mfv = 0.0
        else:
            mfm = ((close - low) - (high - close)) / hl_range
            mfv = mfm * volume

        self._mfv_sum += mfv
        self._vol_sum += volume
        self._mfv_buffer.append(mfv)
        self._vol_buffer.append(volume)

        if len(self._mfv_buffer) > self.length:
            oldest_mfv = self._mfv_buffer.popleft()
            oldest_vol = self._vol_buffer.popleft()
            self._mfv_sum -= oldest_mfv
            self._vol_sum -= oldest_vol

    def reset(self) -> None:
        self._mfv_buffer.clear()
        self._vol_buffer.clear()
        self._mfv_sum = 0.0
        self._vol_sum = 0.0
        self._count = 0

    @property
    def value(self) -> float:
        if not self.is_ready:
            return np.nan

        if self._vol_sum == 0:
            return 0.0

        return self._mfv_sum / self._vol_sum

    @property
    def is_ready(self) -> bool:
        return len(self._mfv_buffer) >= self.length


@dataclass
class IncrementalCMO(IncrementalIndicator):
    """
    Chande Momentum Oscillator with O(1) updates.

    Formula (rolling sum, matches pandas_ta.cmo(talib=False)):
        pos_sum = rolling_sum(positive_changes, length)
        neg_sum = rolling_sum(abs(negative_changes), length)
        cmo = ((pos_sum - neg_sum) / (pos_sum + neg_sum)) * 100
    """

    length: int = 14
    _prev_close: float = field(default=np.nan, init=False)
    _pos_buf: deque[float] = field(default_factory=deque, init=False)
    _neg_buf: deque[float] = field(default_factory=deque, init=False)
    _pos_sum: float = field(default=0.0, init=False)
    _neg_sum: float = field(default=0.0, init=False)
    _change_count: int = field(default=0, init=False)
    _count: int = field(default=0, init=False)

    def update(self, close: float, **kwargs: Any) -> None:
        """Update with new close price."""
        self._count += 1

        if self._count == 1:
            self._prev_close = close
            return

        change = close - self._prev_close
        self._prev_close = close
        self._change_count += 1

        pos = max(0.0, change)
        neg = max(0.0, -change)

        self._pos_buf.append(pos)
        self._neg_buf.append(neg)
        self._pos_sum += pos
        self._neg_sum += neg

        # Evict oldest when buffer exceeds length
        if len(self._pos_buf) > self.length:
            self._pos_sum -= self._pos_buf.popleft()
            self._neg_sum -= self._neg_buf.popleft()

    def reset(self) -> None:
        self._prev_close = np.nan
        self._pos_buf.clear()
        self._neg_buf.clear()
        self._pos_sum = 0.0
        self._neg_sum = 0.0
        self._change_count = 0
        self._count = 0

    @property
    def value(self) -> float:
        if not self.is_ready:
            return np.nan

        total = self._pos_sum + self._neg_sum
        if total == 0:
            return 0.0

        return ((self._pos_sum - self._neg_sum) / total) * 100.0

    @property
    def is_ready(self) -> bool:
        return self._change_count >= self.length


@dataclass
class IncrementalMFI(IncrementalIndicator):
    """
    Money Flow Index with O(1) updates.

    Formula:
        tp = (high + low + close) / 3
        raw_mf = tp * volume
        positive_mf = raw_mf when tp > prev_tp
        negative_mf = raw_mf when tp < prev_tp
        mfi = 100 - (100 / (1 + (sum(pos_mf) / sum(neg_mf))))

    Like RSI but with volume weighting.
    Matches pandas_ta.mfi() output.
    """

    length: int = 14
    _prev_tp: float = field(default=np.nan, init=False)
    _pos_mf_buffer: deque = field(default_factory=deque, init=False)
    _neg_mf_buffer: deque = field(default_factory=deque, init=False)
    _pos_mf_sum: float = field(default=0.0, init=False)
    _neg_mf_sum: float = field(default=0.0, init=False)
    _count: int = field(default=0, init=False)

    def update(
        self, high: float, low: float, close: float, volume: float, **kwargs: Any
    ) -> None:
        """Update with new OHLCV data."""
        self._count += 1

        tp = (high + low + close) / 3.0
        raw_mf = tp * volume

        if self._count == 1:
            self._prev_tp = tp
            # H-I1: First bar has no previous TP, so no flow direction.
            # Don't append to buffers — keeps buffer length and sum in sync.
            return

        # Determine flow direction
        if tp > self._prev_tp:
            pos_mf = raw_mf
            neg_mf = 0.0
        elif tp < self._prev_tp:
            pos_mf = 0.0
            neg_mf = raw_mf
        else:
            pos_mf = 0.0
            neg_mf = 0.0

        self._prev_tp = tp

        self._pos_mf_sum += pos_mf
        self._neg_mf_sum += neg_mf
        self._pos_mf_buffer.append(pos_mf)
        self._neg_mf_buffer.append(neg_mf)

        if len(self._pos_mf_buffer) > self.length:
            oldest_pos = self._pos_mf_buffer.popleft()
            oldest_neg = self._neg_mf_buffer.popleft()
            self._pos_mf_sum -= oldest_pos
            self._neg_mf_sum -= oldest_neg

    def reset(self) -> None:
        self._prev_tp = np.nan
        self._pos_mf_buffer.clear()
        self._neg_mf_buffer.clear()
        self._pos_mf_sum = 0.0
        self._neg_mf_sum = 0.0
        self._count = 0

    @property
    def value(self) -> float:
        if not self.is_ready:
            return np.nan

        if self._neg_mf_sum == 0:
            return 100.0 if self._pos_mf_sum > 0 else 50.0

        mf_ratio = self._pos_mf_sum / self._neg_mf_sum
        return 100.0 - (100.0 / (1.0 + mf_ratio))

    @property
    def is_ready(self) -> bool:
        return len(self._pos_mf_buffer) >= self.length
