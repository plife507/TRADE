"""
Incremental indicator computation for live trading.

O(1) per-bar updates for common indicators. These MUST produce identical
results to pandas_ta vectorized computation (within floating point tolerance).

Usage:
    from src.indicators.incremental import IncrementalEMA, IncrementalRSI

    # Initialize with warmup data
    ema = IncrementalEMA(length=20)
    for price in historical_closes:
        ema.update(price)

    # Then update incrementally in live loop
    ema.update(new_close)
    current_value = ema.value
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import numpy as np


class IncrementalIndicator(ABC):
    """Base class for incremental indicators."""

    @abstractmethod
    def update(self, **kwargs: Any) -> None:
        """Update with new data."""
        ...

    @abstractmethod
    def reset(self) -> None:
        """Reset state to initial."""
        ...

    @property
    @abstractmethod
    def value(self) -> float:
        """Current indicator value."""
        ...

    @property
    @abstractmethod
    def is_ready(self) -> bool:
        """True when warmup period complete."""
        ...


@dataclass
class IncrementalEMA(IncrementalIndicator):
    """
    Exponential Moving Average with O(1) updates.

    Formula:
        α = 2 / (length + 1)
        ema = α * close + (1 - α) * ema_prev

    Matches pandas_ta.ema() output after warmup.
    """

    length: int
    _alpha: float = field(init=False)
    _ema: float = field(default=np.nan, init=False)
    _count: int = field(default=0, init=False)
    _warmup_sum: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        self._alpha = 2.0 / (self.length + 1)

    def update(self, close: float, **kwargs: Any) -> None:
        """Update with new close price."""
        self._count += 1

        if self._count <= self.length:
            # Warmup phase - use SMA for first EMA value
            self._warmup_sum += close
            if self._count == self.length:
                self._ema = self._warmup_sum / self.length
        else:
            # Incremental EMA update
            self._ema = self._alpha * close + (1 - self._alpha) * self._ema

    def reset(self) -> None:
        self._ema = np.nan
        self._count = 0
        self._warmup_sum = 0.0

    @property
    def value(self) -> float:
        return self._ema

    @property
    def is_ready(self) -> bool:
        return self._count >= self.length


@dataclass
class IncrementalSMA(IncrementalIndicator):
    """
    Simple Moving Average with O(1) updates using ring buffer.

    Uses running sum technique:
        sma = (sum + new - oldest) / length

    Matches pandas_ta.sma() output.
    """

    length: int
    _buffer: deque = field(default_factory=deque, init=False)
    _running_sum: float = field(default=0.0, init=False)
    _count: int = field(default=0, init=False)

    def update(self, close: float, **kwargs: Any) -> None:
        """Update with new close price."""
        self._running_sum += close
        self._buffer.append(close)
        self._count += 1

        if len(self._buffer) > self.length:
            oldest = self._buffer.popleft()
            self._running_sum -= oldest

    def reset(self) -> None:
        self._buffer.clear()
        self._running_sum = 0.0
        self._count = 0

    @property
    def value(self) -> float:
        if len(self._buffer) < self.length:
            return np.nan
        return self._running_sum / self.length

    @property
    def is_ready(self) -> bool:
        return len(self._buffer) >= self.length


@dataclass
class IncrementalRSI(IncrementalIndicator):
    """
    Relative Strength Index with O(1) updates.

    Uses Wilder's smoothing (same as pandas_ta default):
        avg_gain = (avg_gain_prev * (n-1) + gain) / n
        avg_loss = (avg_loss_prev * (n-1) + loss) / n
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

    Matches pandas_ta.rsi() output.
    """

    length: int = 14
    _prev_close: float = field(default=np.nan, init=False)
    _avg_gain: float = field(default=0.0, init=False)
    _avg_loss: float = field(default=0.0, init=False)
    _count: int = field(default=0, init=False)
    _warmup_gains: list = field(default_factory=list, init=False)
    _warmup_losses: list = field(default_factory=list, init=False)

    def update(self, close: float, **kwargs: Any) -> None:
        """Update with new close price."""
        self._count += 1

        if self._count == 1:
            # First bar - no change to compute
            self._prev_close = close
            return

        # Compute gain/loss
        change = close - self._prev_close
        gain = max(0.0, change)
        loss = max(0.0, -change)
        self._prev_close = close

        if self._count <= self.length + 1:
            # Warmup phase - collect gains/losses
            self._warmup_gains.append(gain)
            self._warmup_losses.append(loss)

            if self._count == self.length + 1:
                # Initialize with SMA of gains/losses
                self._avg_gain = sum(self._warmup_gains) / self.length
                self._avg_loss = sum(self._warmup_losses) / self.length
        else:
            # Wilder's smoothed moving average
            self._avg_gain = (self._avg_gain * (self.length - 1) + gain) / self.length
            self._avg_loss = (self._avg_loss * (self.length - 1) + loss) / self.length

    def reset(self) -> None:
        self._prev_close = np.nan
        self._avg_gain = 0.0
        self._avg_loss = 0.0
        self._count = 0
        self._warmup_gains.clear()
        self._warmup_losses.clear()

    @property
    def value(self) -> float:
        if not self.is_ready:
            return np.nan

        if self._avg_loss == 0:
            return 100.0 if self._avg_gain > 0 else 50.0

        rs = self._avg_gain / self._avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    @property
    def is_ready(self) -> bool:
        return self._count > self.length


@dataclass
class IncrementalATR(IncrementalIndicator):
    """
    Average True Range with O(1) updates.

    Uses Wilder's smoothing:
        tr = max(high-low, |high-prev_close|, |low-prev_close|)
        atr = (atr_prev * (n-1) + tr) / n

    Matches pandas_ta.atr() output.
    """

    length: int = 14
    _prev_close: float = field(default=np.nan, init=False)
    _atr: float = field(default=np.nan, init=False)
    _count: int = field(default=0, init=False)
    _warmup_tr: list = field(default_factory=list, init=False)

    def update(
        self, high: float, low: float, close: float, **kwargs: Any
    ) -> None:
        """Update with new OHLC data."""
        self._count += 1

        if self._count == 1:
            # First bar - TR is just high-low
            tr = high - low
            self._warmup_tr.append(tr)
            self._prev_close = close
            return

        # True Range
        tr = max(
            high - low,
            abs(high - self._prev_close),
            abs(low - self._prev_close),
        )
        self._prev_close = close

        if self._count <= self.length:
            # Warmup phase
            self._warmup_tr.append(tr)
            if self._count == self.length:
                # Initialize with SMA of TR
                self._atr = sum(self._warmup_tr) / self.length
        else:
            # Wilder's smoothed average
            self._atr = (self._atr * (self.length - 1) + tr) / self.length

    def reset(self) -> None:
        self._prev_close = np.nan
        self._atr = np.nan
        self._count = 0
        self._warmup_tr.clear()

    @property
    def value(self) -> float:
        return self._atr

    @property
    def is_ready(self) -> bool:
        return self._count >= self.length


@dataclass
class IncrementalMACD(IncrementalIndicator):
    """
    MACD with O(1) updates using incremental EMAs.

    Components:
        macd_line = ema_fast - ema_slow
        signal = ema(macd_line, signal_length)
        histogram = macd_line - signal

    Matches pandas_ta.macd() output.
    """

    fast: int = 12
    slow: int = 26
    signal: int = 9
    _ema_fast: IncrementalEMA = field(init=False)
    _ema_slow: IncrementalEMA = field(init=False)
    _ema_signal: IncrementalEMA = field(init=False)
    _macd_line: float = field(default=np.nan, init=False)
    _signal_line: float = field(default=np.nan, init=False)
    _histogram: float = field(default=np.nan, init=False)
    _count: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self._ema_fast = IncrementalEMA(length=self.fast)
        self._ema_slow = IncrementalEMA(length=self.slow)
        self._ema_signal = IncrementalEMA(length=self.signal)

    def update(self, close: float, **kwargs: Any) -> None:
        """Update with new close price."""
        self._count += 1

        self._ema_fast.update(close=close)
        self._ema_slow.update(close=close)

        if self._ema_fast.is_ready and self._ema_slow.is_ready:
            self._macd_line = self._ema_fast.value - self._ema_slow.value
            self._ema_signal.update(close=self._macd_line)

            if self._ema_signal.is_ready:
                self._signal_line = self._ema_signal.value
                self._histogram = self._macd_line - self._signal_line

    def reset(self) -> None:
        self._ema_fast.reset()
        self._ema_slow.reset()
        self._ema_signal.reset()
        self._macd_line = np.nan
        self._signal_line = np.nan
        self._histogram = np.nan
        self._count = 0

    @property
    def value(self) -> float:
        """Returns MACD line value."""
        return self._macd_line

    @property
    def signal_value(self) -> float:
        """Returns signal line value."""
        return self._signal_line

    @property
    def histogram_value(self) -> float:
        """Returns histogram value."""
        return self._histogram

    @property
    def is_ready(self) -> bool:
        return self._ema_signal.is_ready


@dataclass
class IncrementalBBands(IncrementalIndicator):
    """
    Bollinger Bands with O(1) updates using Welford's online variance.

    Uses running stats for variance:
        mean = running_sum / n
        variance = (running_sq_sum - running_sum^2/n) / n
        std = sqrt(variance)

    Output:
        upper = mean + std_dev * std
        middle = mean
        lower = mean - std_dev * std

    Matches pandas_ta.bbands() output.
    """

    length: int = 20
    std_dev: float = 2.0
    _buffer: deque = field(default_factory=deque, init=False)
    _running_sum: float = field(default=0.0, init=False)
    _running_sq_sum: float = field(default=0.0, init=False)
    _count: int = field(default=0, init=False)

    def update(self, close: float, **kwargs: Any) -> None:
        """Update with new close price."""
        self._running_sum += close
        self._running_sq_sum += close * close
        self._buffer.append(close)
        self._count += 1

        if len(self._buffer) > self.length:
            oldest = self._buffer.popleft()
            self._running_sum -= oldest
            self._running_sq_sum -= oldest * oldest

    def reset(self) -> None:
        self._buffer.clear()
        self._running_sum = 0.0
        self._running_sq_sum = 0.0
        self._count = 0

    @property
    def value(self) -> float:
        """Returns middle band (SMA)."""
        return self.middle

    @property
    def middle(self) -> float:
        if len(self._buffer) < self.length:
            return np.nan
        return self._running_sum / self.length

    @property
    def std(self) -> float:
        if len(self._buffer) < self.length:
            return np.nan
        n = self.length
        mean = self._running_sum / n
        # Variance = E[X^2] - E[X]^2 (population variance)
        variance = (self._running_sq_sum / n) - (mean * mean)
        # Handle numerical precision issues
        if variance < 0:
            variance = 0.0
        return np.sqrt(variance)

    @property
    def upper(self) -> float:
        if not self.is_ready:
            return np.nan
        return self.middle + self.std_dev * self.std

    @property
    def lower(self) -> float:
        if not self.is_ready:
            return np.nan
        return self.middle - self.std_dev * self.std

    @property
    def is_ready(self) -> bool:
        return len(self._buffer) >= self.length


# =============================================================================
# Factory for creating incremental indicators from FeatureSpec
# =============================================================================


def create_incremental_indicator(
    indicator_type: str,
    params: dict[str, Any],
) -> IncrementalIndicator | None:
    """
    Create an incremental indicator from type and params.

    Returns None if the indicator type is not supported incrementally.
    """
    indicator_type = indicator_type.lower()

    if indicator_type == "ema":
        return IncrementalEMA(length=params.get("length", 20))
    elif indicator_type == "sma":
        return IncrementalSMA(length=params.get("length", 20))
    elif indicator_type == "rsi":
        return IncrementalRSI(length=params.get("length", 14))
    elif indicator_type == "atr":
        return IncrementalATR(length=params.get("length", 14))
    elif indicator_type == "macd":
        return IncrementalMACD(
            fast=params.get("fast", 12),
            slow=params.get("slow", 26),
            signal=params.get("signal", 9),
        )
    elif indicator_type == "bbands":
        return IncrementalBBands(
            length=params.get("length", 20),
            std_dev=params.get("std", 2.0),
        )
    else:
        # Not supported incrementally - will fall back to vectorized
        return None


# Registry of indicators that support incremental computation
INCREMENTAL_INDICATORS = frozenset({"ema", "sma", "rsi", "atr", "macd", "bbands"})


def supports_incremental(indicator_type: str) -> bool:
    """Check if indicator type supports incremental computation."""
    return indicator_type.lower() in INCREMENTAL_INDICATORS
