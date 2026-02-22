"""
Trivial indicators with O(1) direct computation.

Simple indicators that require minimal state: OHLC4, Midprice, ROC,
MOM, OBV, and NATR.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from src.structures.primitives import MonotonicDeque

from .base import IncrementalIndicator
from .core import IncrementalEMA


@dataclass
class IncrementalOHLC4(IncrementalIndicator):
    """
    OHLC4 (Typical Price) with O(1) updates.

    Formula:
        ohlc4 = (open + high + low + close) / 4

    Matches pandas_ta.ohlc4() output.
    """

    _value: float = field(default=np.nan, init=False)
    _count: int = field(default=0, init=False)

    def update(
        self, open: float, high: float, low: float, close: float, **kwargs: Any
    ) -> None:
        """Update with new OHLC data."""
        self._count += 1
        self._value = (open + high + low + close) / 4.0

    def reset(self) -> None:
        self._value = np.nan
        self._count = 0

    @property
    def value(self) -> float:
        return self._value

    @property
    def is_ready(self) -> bool:
        return self._count >= 1


@dataclass
class IncrementalMidprice(IncrementalIndicator):
    """
    Midprice with true O(1) updates using monotonic deques.

    Formula:
        midprice = (max(high over length) + min(low over length)) / 2

    Note: pandas_ta.midprice uses highest high and lowest low over the period,
    NOT just (high + low) / 2 of a single bar.

    Matches pandas_ta.midprice() output.
    """

    length: int = 14
    _count: int = field(default=0, init=False)
    _max_high: MonotonicDeque = field(init=False)
    _min_low: MonotonicDeque = field(init=False)

    def __post_init__(self) -> None:
        self._max_high = MonotonicDeque(window_size=self.length, mode="max")
        self._min_low = MonotonicDeque(window_size=self.length, mode="min")

    def update(self, high: float, low: float, **kwargs: Any) -> None:
        """Update with new high/low data."""
        self._max_high.push(self._count, high)
        self._min_low.push(self._count, low)
        self._count += 1

    def reset(self) -> None:
        self._max_high.clear()
        self._min_low.clear()
        self._count = 0

    @property
    def value(self) -> float:
        if not self.is_ready:
            return np.nan
        highest = self._max_high.get()
        lowest = self._min_low.get()
        if highest is None or lowest is None:
            return np.nan
        return (highest + lowest) / 2.0

    @property
    def is_ready(self) -> bool:
        return self._count >= self.length


@dataclass
class IncrementalROC(IncrementalIndicator):
    """
    Rate of Change with O(1) updates using ring buffer.

    Formula:
        roc = ((close - close[length]) / close[length]) * 100

    Matches pandas_ta.roc() output.
    """

    length: int = 10
    _buffer: deque = field(default_factory=deque, init=False)
    _count: int = field(default=0, init=False)

    def update(self, close: float, **kwargs: Any) -> None:
        """Update with new close price."""
        self._count += 1
        self._buffer.append(close)

        if len(self._buffer) > self.length + 1:
            self._buffer.popleft()

    def reset(self) -> None:
        self._buffer.clear()
        self._count = 0

    @property
    def value(self) -> float:
        if not self.is_ready:
            return np.nan

        # ROC = (current - previous) / previous * 100
        prev_close = self._buffer[0]
        current_close = self._buffer[-1]

        if prev_close == 0:
            return np.nan

        return ((current_close - prev_close) / prev_close) * 100.0

    @property
    def is_ready(self) -> bool:
        return len(self._buffer) > self.length


@dataclass
class IncrementalMOM(IncrementalIndicator):
    """
    Momentum with O(1) updates using ring buffer.

    Formula:
        mom = close - close[length]

    Matches pandas_ta.mom() output.
    """

    length: int = 10
    _buffer: deque = field(default_factory=deque, init=False)
    _count: int = field(default=0, init=False)

    def update(self, close: float, **kwargs: Any) -> None:
        """Update with new close price."""
        self._count += 1
        self._buffer.append(close)

        if len(self._buffer) > self.length + 1:
            self._buffer.popleft()

    def reset(self) -> None:
        self._buffer.clear()
        self._count = 0

    @property
    def value(self) -> float:
        if not self.is_ready:
            return np.nan

        # MOM = current - previous
        return self._buffer[-1] - self._buffer[0]

    @property
    def is_ready(self) -> bool:
        return len(self._buffer) > self.length


@dataclass
class IncrementalOBV(IncrementalIndicator):
    """
    On Balance Volume with O(1) updates.

    Formula:
        signed_volume = sign(close.diff()) * volume
        obv = cumsum(signed_volume)

    pandas_ta behavior: first bar has NaN diff (no previous close), so
    OBV starts accumulating from bar 1. Bar 0 produces NaN.

    Matches pandas_ta.obv(talib=False) output.
    """

    _prev_close: float = field(default=np.nan, init=False)
    _obv: float = field(default=np.nan, init=False)
    _count: int = field(default=0, init=False)

    def update(self, close: float, volume: float, **kwargs: Any) -> None:
        """Update with new close and volume."""
        self._count += 1

        if self._count == 1:
            # First bar: no previous close, sign is NaN -> OBV stays NaN
            self._prev_close = close
            return

        # Sign of close change: +1, -1, or 0
        if close > self._prev_close:
            signed_vol = volume
        elif close < self._prev_close:
            signed_vol = -volume
        else:
            signed_vol = 0.0

        if self._count == 2:
            # Second bar: first valid signed volume, start accumulation
            self._obv = signed_vol
        else:
            self._obv += signed_vol

        self._prev_close = close

    def reset(self) -> None:
        self._prev_close = np.nan
        self._obv = np.nan
        self._count = 0

    @property
    def value(self) -> float:
        if not self.is_ready:
            return np.nan
        return self._obv

    @property
    def is_ready(self) -> bool:
        return self._count >= 2


@dataclass
class IncrementalNATR(IncrementalIndicator):
    """
    Normalized Average True Range with O(1) updates.

    Formula:
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        atr = ema(tr, length)  # pandas_ta default uses EMA, not RMA
        natr = (100 / close) * atr

    Uses EMA for ATR to match pandas_ta.natr(mamode='ema') default.
    Matches pandas_ta.natr() output.
    """

    length: int = 14
    _prev_close: float = field(default=np.nan, init=False)
    _tr_ema: IncrementalEMA = field(init=False)
    _last_close: float = field(default=np.nan, init=False)
    _count: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self._tr_ema = IncrementalEMA(length=self.length)

    def update(
        self, high: float, low: float, close: float, **kwargs: Any
    ) -> None:
        """Update with new OHLC data."""
        self._count += 1

        # Compute True Range
        if self._count == 1:
            tr = high - low
        else:
            tr = max(
                high - low,
                abs(high - self._prev_close),
                abs(low - self._prev_close)
            )

        self._prev_close = close
        self._last_close = close
        self._tr_ema.update(close=tr)

    def reset(self) -> None:
        self._prev_close = np.nan
        self._tr_ema.reset()
        self._last_close = np.nan
        self._count = 0

    @property
    def value(self) -> float:
        if not self.is_ready:
            return np.nan

        atr_val = self._tr_ema.value
        if np.isnan(atr_val) or self._last_close == 0:
            return np.nan

        return (100.0 / self._last_close) * atr_val

    @property
    def is_ready(self) -> bool:
        return self._tr_ema.is_ready
