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

    Args:
        length: ATR period (default 14)
        prenan: If True, skip first TR (no prev_close available).
                Matches pandas_ta.atr(prenan=True) behavior.
                Default False for standalone ATR, but ADX uses True internally.

    Matches pandas_ta.atr() output.
    """

    length: int = 14
    prenan: bool = False
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
            # First bar
            if not self.prenan:
                # Include first bar TR in warmup (prenan=False behavior)
                tr = high - low
                self._warmup_tr.append(tr)
            # Either way, record prev_close for next bar's gap calculation
            self._prev_close = close
            return

        # True Range (includes gap from previous close)
        tr = max(
            high - low,
            abs(high - self._prev_close),
            abs(low - self._prev_close),
        )
        self._prev_close = close

        if self._count <= self.length:
            # Warmup phase - collect TR values
            self._warmup_tr.append(tr)
            if self._count == self.length:
                # Initialize with SMA of warmup TRs
                # With prenan=True, we have length-1 values (skipped bar 0)
                # With prenan=False, we have length values
                # Pandas mean() skips NaN, so uses actual count as divisor
                self._atr = sum(self._warmup_tr) / len(self._warmup_tr)
        else:
            # Wilder's smoothed average (RMA)
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
    def macd_value(self) -> float:
        """Returns MACD line value (alias for consistency with multi-output pattern)."""
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
    def bandwidth(self) -> float:
        """Returns bandwidth: (upper - lower) / middle * 100."""
        if not self.is_ready:
            return np.nan
        mid = self.middle
        if mid == 0:
            return np.nan
        return (self.upper - self.lower) / mid * 100.0

    @property
    def percent_b(self) -> float:
        """Returns %B: (close - lower) / (upper - lower)."""
        if not self.is_ready:
            return np.nan
        upper = self.upper
        lower = self.lower
        if upper == lower:
            return 0.5  # Midpoint when bands are equal
        # Use last close from buffer
        close = self._buffer[-1]
        return (close - lower) / (upper - lower)

    # Aliases for multi-output naming convention
    @property
    def lower_value(self) -> float:
        return self.lower

    @property
    def middle_value(self) -> float:
        return self.middle

    @property
    def upper_value(self) -> float:
        return self.upper

    @property
    def bandwidth_value(self) -> float:
        return self.bandwidth

    @property
    def percent_b_value(self) -> float:
        return self.percent_b

    @property
    def is_ready(self) -> bool:
        return len(self._buffer) >= self.length


@dataclass
class IncrementalWilliamsR(IncrementalIndicator):
    """
    Williams %R with O(1) updates using ring buffers.

    Formula:
        highest_high = max(high over length periods)
        lowest_low = min(low over length periods)
        %R = (highest_high - close) / (highest_high - lowest_low) * -100

    Matches pandas_ta.willr() output.
    """

    length: int = 14
    _high_buffer: deque = field(default_factory=deque, init=False)
    _low_buffer: deque = field(default_factory=deque, init=False)
    _last_close: float = field(default=np.nan, init=False)
    _count: int = field(default=0, init=False)

    def update(
        self, high: float, low: float, close: float, **kwargs: Any
    ) -> None:
        """Update with new OHLC data."""
        self._count += 1

        self._high_buffer.append(high)
        self._low_buffer.append(low)
        self._last_close = close

        if len(self._high_buffer) > self.length:
            self._high_buffer.popleft()
            self._low_buffer.popleft()

    def reset(self) -> None:
        self._high_buffer.clear()
        self._low_buffer.clear()
        self._last_close = np.nan
        self._count = 0

    @property
    def value(self) -> float:
        if not self.is_ready:
            return np.nan

        highest_high = max(self._high_buffer)
        lowest_low = min(self._low_buffer)

        if highest_high == lowest_low:
            return -50.0  # Midpoint when no range

        return ((highest_high - self._last_close) / (highest_high - lowest_low)) * -100.0

    @property
    def is_ready(self) -> bool:
        return len(self._high_buffer) >= self.length


@dataclass
class IncrementalCCI(IncrementalIndicator):
    """
    Commodity Channel Index with O(1) updates.

    Formula:
        tp = (high + low + close) / 3
        tp_sma = sma(tp, length)
        mean_dev = mean(|tp - tp_sma|) over length
        cci = (tp - tp_sma) / (0.015 * mean_dev)

    Uses ring buffer for typical prices and running sums.
    Matches pandas_ta.cci() output.
    """

    length: int = 14
    _tp_buffer: deque = field(default_factory=deque, init=False)
    _tp_sum: float = field(default=0.0, init=False)
    _count: int = field(default=0, init=False)

    def update(
        self, high: float, low: float, close: float, **kwargs: Any
    ) -> None:
        """Update with new OHLC data."""
        self._count += 1

        tp = (high + low + close) / 3.0
        self._tp_sum += tp
        self._tp_buffer.append(tp)

        if len(self._tp_buffer) > self.length:
            oldest = self._tp_buffer.popleft()
            self._tp_sum -= oldest

    def reset(self) -> None:
        self._tp_buffer.clear()
        self._tp_sum = 0.0
        self._count = 0

    @property
    def value(self) -> float:
        if not self.is_ready:
            return np.nan

        # TP SMA
        tp_sma = self._tp_sum / self.length

        # Mean deviation
        mean_dev = sum(abs(tp - tp_sma) for tp in self._tp_buffer) / self.length

        if mean_dev == 0:
            return 0.0

        # Current TP
        current_tp = self._tp_buffer[-1]

        return (current_tp - tp_sma) / (0.015 * mean_dev)

    @property
    def is_ready(self) -> bool:
        return len(self._tp_buffer) >= self.length


@dataclass
class IncrementalStochastic(IncrementalIndicator):
    """
    Stochastic Oscillator with O(1) updates.

    Formula:
        lowest_low = min(low over k_period)
        highest_high = max(high over k_period)
        fast_k = (close - lowest_low) / (highest_high - lowest_low) * 100
        %K = sma(fast_k, smooth_k)
        %D = sma(%K, d_period)

    Matches pandas_ta.stoch() output.
    """

    k_period: int = 14
    smooth_k: int = 3
    d_period: int = 3
    _high_buffer: deque = field(default_factory=deque, init=False)
    _low_buffer: deque = field(default_factory=deque, init=False)
    _fast_k_buffer: deque = field(default_factory=deque, init=False)
    _k_buffer: deque = field(default_factory=deque, init=False)
    _last_close: float = field(default=np.nan, init=False)
    _count: int = field(default=0, init=False)

    def update(
        self, high: float, low: float, close: float, **kwargs: Any
    ) -> None:
        """Update with new OHLC data."""
        self._count += 1

        # Update high/low buffers
        self._high_buffer.append(high)
        self._low_buffer.append(low)
        self._last_close = close

        if len(self._high_buffer) > self.k_period:
            self._high_buffer.popleft()
            self._low_buffer.popleft()

        # Compute fast %K once we have enough data
        if len(self._high_buffer) >= self.k_period:
            highest_high = max(self._high_buffer)
            lowest_low = min(self._low_buffer)

            if highest_high == lowest_low:
                fast_k = 50.0
            else:
                fast_k = ((close - lowest_low) / (highest_high - lowest_low)) * 100.0

            self._fast_k_buffer.append(fast_k)
            if len(self._fast_k_buffer) > self.smooth_k:
                self._fast_k_buffer.popleft()

            # Compute %K (smoothed)
            if len(self._fast_k_buffer) >= self.smooth_k:
                k_val = sum(self._fast_k_buffer) / self.smooth_k
                self._k_buffer.append(k_val)
                if len(self._k_buffer) > self.d_period:
                    self._k_buffer.popleft()

    def reset(self) -> None:
        self._high_buffer.clear()
        self._low_buffer.clear()
        self._fast_k_buffer.clear()
        self._k_buffer.clear()
        self._last_close = np.nan
        self._count = 0

    @property
    def value(self) -> float:
        """Returns %K value."""
        return self.k_value

    @property
    def k_value(self) -> float:
        """Returns %K value."""
        if len(self._k_buffer) < self.d_period:
            return np.nan
        return self._k_buffer[-1]

    @property
    def d_value(self) -> float:
        """Returns %D value (SMA of %K)."""
        if len(self._k_buffer) < self.d_period:
            return np.nan
        return sum(self._k_buffer) / len(self._k_buffer)

    @property
    def is_ready(self) -> bool:
        return len(self._k_buffer) >= self.d_period


@dataclass
class IncrementalStochRSI(IncrementalIndicator):
    """
    Stochastic RSI with O(1) updates.

    Formula:
        rsi = RSI(close, rsi_length)
        stochrsi = (rsi - min(rsi, length)) / (max(rsi, length) - min(rsi, length))
        %K = sma(stochrsi, k)
        %D = sma(%K, d)

    Uses IncrementalRSI internally + stochastic calculation on RSI values.
    Matches pandas_ta.stochrsi() output.
    """

    length: int = 14
    rsi_length: int = 14
    k: int = 3
    d: int = 3
    _rsi: IncrementalRSI = field(init=False)
    _rsi_buffer: deque = field(default_factory=deque, init=False)
    _fast_k_buffer: deque = field(default_factory=deque, init=False)
    _k_buffer: deque = field(default_factory=deque, init=False)
    _count: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self._rsi = IncrementalRSI(length=self.rsi_length)

    def update(self, close: float, **kwargs: Any) -> None:
        """Update with new close price."""
        self._count += 1
        self._rsi.update(close=close)

        if not self._rsi.is_ready:
            return

        # Store RSI values
        rsi_val = self._rsi.value
        self._rsi_buffer.append(rsi_val)

        if len(self._rsi_buffer) > self.length:
            self._rsi_buffer.popleft()

        # Compute stochastic RSI when we have enough RSI values
        if len(self._rsi_buffer) >= self.length:
            min_rsi = min(self._rsi_buffer)
            max_rsi = max(self._rsi_buffer)

            if max_rsi == min_rsi:
                fast_k = 50.0
            else:
                fast_k = ((rsi_val - min_rsi) / (max_rsi - min_rsi)) * 100.0

            self._fast_k_buffer.append(fast_k)
            if len(self._fast_k_buffer) > self.k:
                self._fast_k_buffer.popleft()

            # Compute %K (smoothed)
            if len(self._fast_k_buffer) >= self.k:
                k_val = sum(self._fast_k_buffer) / self.k
                self._k_buffer.append(k_val)
                if len(self._k_buffer) > self.d:
                    self._k_buffer.popleft()

    def reset(self) -> None:
        self._rsi.reset()
        self._rsi_buffer.clear()
        self._fast_k_buffer.clear()
        self._k_buffer.clear()
        self._count = 0

    @property
    def value(self) -> float:
        """Returns %K value."""
        return self.k_value

    @property
    def k_value(self) -> float:
        """Returns %K value."""
        if len(self._k_buffer) < self.d:
            return np.nan
        return self._k_buffer[-1]

    @property
    def d_value(self) -> float:
        """Returns %D value (SMA of %K)."""
        if len(self._k_buffer) < self.d:
            return np.nan
        return sum(self._k_buffer) / len(self._k_buffer)

    @property
    def is_ready(self) -> bool:
        return len(self._k_buffer) >= self.d


@dataclass
class IncrementalADX(IncrementalIndicator):
    """
    Average Directional Index with O(1) updates.

    Uses EWM (alpha=1/length) smoothing to match pandas_ta.adx(talib=False).
    Internally uses IncrementalATR for true range.

    Key insight for warmup: pandas_ta starts RMA smoothing of DM from bar 1
    (the first bar with DM values), NOT from when ATR becomes ready. This means
    by the time ATR is valid, DM smoothing has already accumulated history.

    For live trading:
    - Load sufficient historical data (recommended: 3*length bars minimum)
    - Run through all historical bars to warm up the indicator
    - Use is_ready check before using values for trading decisions
    """

    length: int = 14
    _atr: IncrementalATR = field(init=False)
    _prev_high: float = field(default=np.nan, init=False)
    _prev_low: float = field(default=np.nan, init=False)
    _smoothed_plus_dm: float = field(default=np.nan, init=False)
    _smoothed_minus_dm: float = field(default=np.nan, init=False)
    _smoothed_dx: float = field(default=np.nan, init=False)
    _dm_count: int = field(default=0, init=False)  # Counts DM values (starts at bar 1)
    _dx_count: int = field(default=0, init=False)  # Counts DX values
    _count: int = field(default=0, init=False)
    _atr_first_ready: bool = field(default=False, init=False)  # Track first ATR ready bar
    _adx_history: list = field(default_factory=list, init=False)  # G5.6: For ADXR

    def __post_init__(self) -> None:
        # pandas_ta ADX uses atr(..., prenan=True) internally
        self._atr = IncrementalATR(length=self.length, prenan=True)

    def update(
        self, high: float, low: float, close: float, **kwargs: Any
    ) -> None:
        """
        Update with new OHLC data.

        Matches pandas_ta.adx(talib=False) calculation:
        1. Start DM smoothing from bar 1 (first bar with DM values)
        2. Compute DI when ATR is ready (bar length-1)
        3. Start DX smoothing when first DI is valid
        """
        self._count += 1

        # Update ATR (tracks its own warmup)
        self._atr.update(high=high, low=low, close=close)

        if self._count == 1:
            self._prev_high = high
            self._prev_low = low
            return

        # Directional Movement - computed from bar 1 onwards
        up_move = high - self._prev_high
        down_move = self._prev_low - low

        plus_dm = up_move if up_move > down_move and up_move > 0 else 0.0
        minus_dm = down_move if down_move > up_move and down_move > 0 else 0.0

        self._prev_high = high
        self._prev_low = low

        # EWM smoothing for DM - START IMMEDIATELY from bar 1
        # (matches pandas_ta rma with adjust=False starting from first value)
        # y[0] = x[0], y[i] = alpha * x[i] + (1 - alpha) * y[i-1]
        self._dm_count += 1
        alpha = 1.0 / self.length

        if self._dm_count == 1:
            # First DM value at bar 1 - initialize
            self._smoothed_plus_dm = plus_dm
            self._smoothed_minus_dm = minus_dm
        else:
            # EWM update - continues accumulating before ATR is ready
            self._smoothed_plus_dm = alpha * plus_dm + (1 - alpha) * self._smoothed_plus_dm
            self._smoothed_minus_dm = alpha * minus_dm + (1 - alpha) * self._smoothed_minus_dm

        # Calculate DI values and DX only when ATR is ready
        # Skip the first bar when ATR becomes ready (bar 13 with length=14, prenan=True)
        # pandas_ta DMP is first valid at bar 14, not bar 13
        if self._atr.is_ready:
            if not self._atr_first_ready:
                # First bar ATR is ready - skip DI/DX computation to match pandas_ta
                self._atr_first_ready = True
                return

            atr_val = self._atr.value
            if atr_val > 0:
                # DI = 100 * smoothed_dm / atr
                plus_di = (self._smoothed_plus_dm / atr_val) * 100.0
                minus_di = (self._smoothed_minus_dm / atr_val) * 100.0

                di_sum = plus_di + minus_di
                if di_sum > 0:
                    dx = abs(plus_di - minus_di) / di_sum * 100.0
                else:
                    dx = 0.0

                # EWM smoothing for DX (same formula as DM)
                self._dx_count += 1
                if self._dx_count == 1:
                    self._smoothed_dx = dx
                else:
                    self._smoothed_dx = alpha * dx + (1 - alpha) * self._smoothed_dx

                # G5.6: Track ADX history for ADXR calculation
                self._adx_history.append(self._smoothed_dx)
                if len(self._adx_history) > self.length:
                    self._adx_history.pop(0)

    def reset(self) -> None:
        self._atr.reset()
        self._prev_high = np.nan
        self._prev_low = np.nan
        self._smoothed_plus_dm = np.nan
        self._smoothed_minus_dm = np.nan
        self._smoothed_dx = np.nan
        self._dm_count = 0
        self._dx_count = 0
        self._count = 0
        self._atr_first_ready = False
        self._adx_history = []

    @property
    def value(self) -> float:
        """Returns ADX value."""
        return self.adx_value

    @property
    def adx_value(self) -> float:
        """Returns ADX value."""
        if not self.is_ready:
            return np.nan
        return self._smoothed_dx

    @property
    def dmp_value(self) -> float:
        """Returns +DI value."""
        # Use is_ready to match pandas_ta warmup (DI first valid at bar 14, not 13)
        if not self.is_ready:
            return np.nan
        atr_val = self._atr.value
        if atr_val <= 0 or np.isnan(self._smoothed_plus_dm):
            return np.nan
        return (self._smoothed_plus_dm / atr_val) * 100.0

    @property
    def dmn_value(self) -> float:
        """Returns -DI value."""
        # Use is_ready to match pandas_ta warmup (DI first valid at bar 14, not 13)
        if not self.is_ready:
            return np.nan
        atr_val = self._atr.value
        if atr_val <= 0 or np.isnan(self._smoothed_minus_dm):
            return np.nan
        return (self._smoothed_minus_dm / atr_val) * 100.0

    @property
    def adxr_value(self) -> float:
        """
        Returns ADXR value (Average Directional Index Rating).

        ADXR = (ADX_current + ADX_n_bars_ago) / 2
        Provides a smoothed view of ADX trend strength.
        """
        if len(self._adx_history) < self.length:
            return np.nan
        adx_current = self._adx_history[-1]
        adx_lag = self._adx_history[0]
        return (adx_current + adx_lag) / 2.0

    @property
    def is_ready(self) -> bool:
        # ADX is ready as soon as first DX is computed (pandas_ta RMA uses
        # first DX as seed, no warmup wait)
        return self._dx_count >= 1


@dataclass
class IncrementalSuperTrend(IncrementalIndicator):
    """
    SuperTrend with O(1) updates.

    Uses IncrementalATR internally. Tracks trend direction and levels.

    Matches pandas_ta.supertrend() output.

    Note: pandas_ta.supertrend uses TA-Lib ATR internally (if installed),
    which is first valid at bar `length` (vs pure Python at bar `length-1`).
    We skip the first ATR-ready bar to match this +1 bar warmup delay.
    """

    length: int = 10
    multiplier: float = 3.0
    _atr: IncrementalATR = field(init=False)
    _prev_close: float = field(default=np.nan, init=False)
    _prev_upper: float = field(default=np.nan, init=False)
    _prev_lower: float = field(default=np.nan, init=False)
    _prev_trend: float = field(default=np.nan, init=False)
    _direction: int = field(default=1, init=False)  # 1 = up, -1 = down
    _count: int = field(default=0, init=False)
    _atr_first_ready: bool = field(default=False, init=False)  # Track first ATR-ready bar

    def __post_init__(self) -> None:
        # Use prenan=True to match TA-Lib ATR behavior used by pandas_ta.supertrend
        self._atr = IncrementalATR(length=self.length, prenan=True)

    def update(
        self, high: float, low: float, close: float, **kwargs: Any
    ) -> None:
        """
        Update with new OHLC data.

        Logic matches pandas_ta.supertrend() exactly:
        1. Determine direction using PREVIOUS bar's (final) bands
        2. Apply band holding ONLY when direction unchanged
        3. Set trend value based on direction
        """
        self._count += 1

        # Update ATR
        self._atr.update(high=high, low=low, close=close)

        if not self._atr.is_ready:
            self._prev_close = close
            return

        # Skip first ATR-ready bar to match TA-Lib ATR's +1 bar warmup delay.
        # pandas_ta.supertrend uses TA-Lib ATR (first valid at bar `length`),
        # while our IncrementalATR matches pure Python (first valid at bar `length-1`).
        if not self._atr_first_ready:
            self._atr_first_ready = True
            self._prev_close = close
            return

        atr_val = self._atr.value
        hl2 = (high + low) / 2.0

        # Basic bands for THIS bar (before any holding logic)
        basic_upper = hl2 + (self.multiplier * atr_val)
        basic_lower = hl2 - (self.multiplier * atr_val)

        if np.isnan(self._prev_upper):
            # First valid bar - initialize
            self._direction = 1
            self._prev_upper = basic_upper
            self._prev_lower = basic_lower
            self._prev_trend = basic_lower  # Start in uptrend
            self._prev_close = close
            return

        # STEP 1: Determine direction using PREVIOUS bar's (final) bands
        # This matches pandas_ta: close[i] compared to ub[i-1] and lb[i-1]
        if close > self._prev_upper:
            self._direction = 1
        elif close < self._prev_lower:
            self._direction = -1
        # else: keep previous direction (already set)

        # STEP 2: Apply band holding logic
        # In pandas_ta, holding only happens when direction is unchanged (else branch)
        if close > self._prev_upper or close < self._prev_lower:
            # Direction changed - use basic bands without holding
            final_upper = basic_upper
            final_lower = basic_lower
        else:
            # Direction unchanged - apply holding
            if self._direction > 0:
                # Uptrend: hold lower band if it contracts (new < old)
                final_lower = max(basic_lower, self._prev_lower)
                final_upper = basic_upper
            else:
                # Downtrend: hold upper band if it expands (new > old)
                final_upper = min(basic_upper, self._prev_upper)
                final_lower = basic_lower

        # STEP 3: Set trend value based on direction
        if self._direction > 0:
            self._prev_trend = final_lower
        else:
            self._prev_trend = final_upper

        # Store final bands for next bar's comparison
        self._prev_upper = final_upper
        self._prev_lower = final_lower
        self._prev_close = close

    def reset(self) -> None:
        self._atr.reset()
        self._prev_close = np.nan
        self._prev_upper = np.nan
        self._prev_lower = np.nan
        self._prev_trend = np.nan
        self._direction = 1
        self._count = 0
        self._atr_first_ready = False

    @property
    def value(self) -> float:
        """Returns SuperTrend level."""
        return self.trend_value

    @property
    def trend_value(self) -> float:
        """Returns SuperTrend level."""
        if not self.is_ready:
            return np.nan
        return self._prev_trend

    @property
    def direction_value(self) -> int:
        """Returns direction: 1 = up, -1 = down."""
        if not self.is_ready:
            return 0
        return self._direction

    @property
    def long_value(self) -> float:
        """Returns long stop level (NaN when short)."""
        if not self.is_ready or self._direction != 1:
            return np.nan
        return self._prev_lower

    @property
    def short_value(self) -> float:
        """Returns short stop level (NaN when long)."""
        if not self.is_ready or self._direction != -1:
            return np.nan
        return self._prev_upper

    @property
    def is_ready(self) -> bool:
        return self._atr.is_ready and self._count > self.length


# =============================================================================
# Phase 1: Trivial Indicators (O(1) direct computation)
# =============================================================================


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
    Midprice with O(1) updates using ring buffer.

    Formula:
        midprice = (max(high over length) + min(low over length)) / 2

    Note: pandas_ta.midprice uses highest high and lowest low over the period,
    NOT just (high + low) / 2 of a single bar.

    Matches pandas_ta.midprice() output.
    """

    length: int = 14
    _high_buffer: deque = field(default_factory=deque, init=False)
    _low_buffer: deque = field(default_factory=deque, init=False)
    _count: int = field(default=0, init=False)

    def update(self, high: float, low: float, **kwargs: Any) -> None:
        """Update with new high/low data."""
        self._count += 1

        self._high_buffer.append(high)
        self._low_buffer.append(low)

        if len(self._high_buffer) > self.length:
            self._high_buffer.popleft()
            self._low_buffer.popleft()

    def reset(self) -> None:
        self._high_buffer.clear()
        self._low_buffer.clear()
        self._count = 0

    @property
    def value(self) -> float:
        if not self.is_ready:
            return np.nan
        highest = max(self._high_buffer)
        lowest = min(self._low_buffer)
        return (highest + lowest) / 2.0

    @property
    def is_ready(self) -> bool:
        return len(self._high_buffer) >= self.length


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
        First bar: obv = volume (signed by close direction vs 0)
        Subsequent: if close > prev_close: obv += volume
                   if close < prev_close: obv -= volume
                   if close == prev_close: obv unchanged

    Matches pandas_ta.obv() output.
    """

    _prev_close: float = field(default=np.nan, init=False)
    _obv: float = field(default=np.nan, init=False)
    _count: int = field(default=0, init=False)

    def update(self, close: float, volume: float, **kwargs: Any) -> None:
        """Update with new close and volume."""
        self._count += 1

        if self._count == 1:
            # First bar - OBV starts with first volume (pandas_ta behavior)
            self._obv = volume
            self._prev_close = close
            return

        # Compare with previous close
        if close > self._prev_close:
            self._obv += volume
        elif close < self._prev_close:
            self._obv -= volume
        # else: unchanged

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
        return self._count >= 1


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


# =============================================================================
# Phase 2: EMA-Composable Indicators
# =============================================================================


@dataclass
class IncrementalDEMA(IncrementalIndicator):
    """
    Double Exponential Moving Average with O(1) updates.

    Formula:
        dema = 2 * ema1 - ema2
        where ema2 = ema(ema1)

    Matches pandas_ta.dema() output.
    """

    length: int = 20
    _ema1: IncrementalEMA = field(init=False)
    _ema2: IncrementalEMA = field(init=False)
    _count: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self._ema1 = IncrementalEMA(length=self.length)
        self._ema2 = IncrementalEMA(length=self.length)

    def update(self, close: float, **kwargs: Any) -> None:
        """Update with new close price."""
        self._count += 1
        self._ema1.update(close=close)

        if self._ema1.is_ready:
            self._ema2.update(close=self._ema1.value)

    def reset(self) -> None:
        self._ema1.reset()
        self._ema2.reset()
        self._count = 0

    @property
    def value(self) -> float:
        if not self.is_ready:
            return np.nan
        return 2.0 * self._ema1.value - self._ema2.value

    @property
    def is_ready(self) -> bool:
        return self._ema2.is_ready


@dataclass
class IncrementalTEMA(IncrementalIndicator):
    """
    Triple Exponential Moving Average with O(1) updates.

    Formula:
        tema = 3 * ema1 - 3 * ema2 + ema3
        where ema2 = ema(ema1), ema3 = ema(ema2)

    Matches pandas_ta.tema() output.
    """

    length: int = 20
    _ema1: IncrementalEMA = field(init=False)
    _ema2: IncrementalEMA = field(init=False)
    _ema3: IncrementalEMA = field(init=False)
    _count: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self._ema1 = IncrementalEMA(length=self.length)
        self._ema2 = IncrementalEMA(length=self.length)
        self._ema3 = IncrementalEMA(length=self.length)

    def update(self, close: float, **kwargs: Any) -> None:
        """Update with new close price."""
        self._count += 1
        self._ema1.update(close=close)

        if self._ema1.is_ready:
            self._ema2.update(close=self._ema1.value)

            if self._ema2.is_ready:
                self._ema3.update(close=self._ema2.value)

    def reset(self) -> None:
        self._ema1.reset()
        self._ema2.reset()
        self._ema3.reset()
        self._count = 0

    @property
    def value(self) -> float:
        if not self.is_ready:
            return np.nan
        return 3.0 * self._ema1.value - 3.0 * self._ema2.value + self._ema3.value

    @property
    def is_ready(self) -> bool:
        return self._ema3.is_ready


@dataclass
class IncrementalPPO(IncrementalIndicator):
    """
    Percentage Price Oscillator with O(1) updates.

    Formula:
        ppo = ((fast_sma - slow_sma) / slow_sma) * 100
        signal = ema(ppo, signal_length)
        histogram = ppo - signal

    Uses SMA for fast/slow (pandas_ta default mamode='sma').
    Signal line uses EMA.
    Matches pandas_ta.ppo() output.
    """

    fast: int = 12
    slow: int = 26
    signal: int = 9
    _sma_fast: IncrementalSMA = field(init=False)
    _sma_slow: IncrementalSMA = field(init=False)
    _ema_signal: IncrementalEMA = field(init=False)
    _ppo_line: float = field(default=np.nan, init=False)
    _signal_line: float = field(default=np.nan, init=False)
    _histogram: float = field(default=np.nan, init=False)
    _count: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self._sma_fast = IncrementalSMA(length=self.fast)
        self._sma_slow = IncrementalSMA(length=self.slow)
        self._ema_signal = IncrementalEMA(length=self.signal)

    def update(self, close: float, **kwargs: Any) -> None:
        """Update with new close price."""
        self._count += 1

        self._sma_fast.update(close=close)
        self._sma_slow.update(close=close)

        if self._sma_fast.is_ready and self._sma_slow.is_ready:
            slow_val = self._sma_slow.value
            if slow_val != 0:
                self._ppo_line = ((self._sma_fast.value - slow_val) / slow_val) * 100.0
                self._ema_signal.update(close=self._ppo_line)

                if self._ema_signal.is_ready:
                    self._signal_line = self._ema_signal.value
                    self._histogram = self._ppo_line - self._signal_line

    def reset(self) -> None:
        self._sma_fast.reset()
        self._sma_slow.reset()
        self._ema_signal.reset()
        self._ppo_line = np.nan
        self._signal_line = np.nan
        self._histogram = np.nan
        self._count = 0

    @property
    def value(self) -> float:
        """Returns PPO line value."""
        return self._ppo_line

    @property
    def ppo_value(self) -> float:
        """Returns PPO line value."""
        return self._ppo_line

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
class IncrementalTRIX(IncrementalIndicator):
    """
    TRIX (Triple Exponential Average Rate of Change) with O(1) updates.

    Formula:
        ema1 = ema(close)
        ema2 = ema(ema1)
        ema3 = ema(ema2)
        trix = pct_change(ema3) * 100 = ((ema3 - ema3_prev) / ema3_prev) * 100
        signal = sma(trix, signal_length)  # pandas_ta uses SMA for signal

    Matches pandas_ta.trix() output.
    """

    length: int = 18
    signal: int = 9
    _ema1: IncrementalEMA = field(init=False)
    _ema2: IncrementalEMA = field(init=False)
    _ema3: IncrementalEMA = field(init=False)
    _sma_signal: IncrementalSMA = field(init=False)
    _prev_ema3: float = field(default=np.nan, init=False)
    _trix_value: float = field(default=np.nan, init=False)
    _signal_line: float = field(default=np.nan, init=False)
    _count: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self._ema1 = IncrementalEMA(length=self.length)
        self._ema2 = IncrementalEMA(length=self.length)
        self._ema3 = IncrementalEMA(length=self.length)
        self._sma_signal = IncrementalSMA(length=self.signal)

    def update(self, close: float, **kwargs: Any) -> None:
        """Update with new close price."""
        self._count += 1

        self._ema1.update(close=close)

        if self._ema1.is_ready:
            self._ema2.update(close=self._ema1.value)

            if self._ema2.is_ready:
                self._ema3.update(close=self._ema2.value)

                if self._ema3.is_ready:
                    ema3_val = self._ema3.value
                    if not np.isnan(self._prev_ema3) and self._prev_ema3 != 0:
                        self._trix_value = ((ema3_val - self._prev_ema3) / self._prev_ema3) * 100.0
                        self._sma_signal.update(close=self._trix_value)

                        if self._sma_signal.is_ready:
                            self._signal_line = self._sma_signal.value

                    self._prev_ema3 = ema3_val

    def reset(self) -> None:
        self._ema1.reset()
        self._ema2.reset()
        self._ema3.reset()
        self._sma_signal.reset()
        self._prev_ema3 = np.nan
        self._trix_value = np.nan
        self._signal_line = np.nan
        self._count = 0

    @property
    def value(self) -> float:
        """Returns TRIX value."""
        return self._trix_value

    @property
    def trix_value(self) -> float:
        """Returns TRIX value."""
        return self._trix_value

    @property
    def signal_value(self) -> float:
        """Returns signal line value."""
        return self._signal_line

    @property
    def is_ready(self) -> bool:
        return not np.isnan(self._trix_value)


@dataclass
class IncrementalTSI(IncrementalIndicator):
    """
    True Strength Index with O(1) updates.

    Formula:
        pc = close - prev_close (momentum)
        double_smoothed_pc = ema(ema(pc, fast), slow)
        double_smoothed_apc = ema(ema(abs(pc), fast), slow)
        tsi = (double_smoothed_pc / double_smoothed_apc) * 100
        signal = ema(tsi, signal_length)

    Matches pandas_ta.tsi() output.
    """

    fast: int = 13
    slow: int = 25
    signal: int = 13
    _prev_close: float = field(default=np.nan, init=False)
    _pc_ema1: IncrementalEMA = field(init=False)
    _pc_ema2: IncrementalEMA = field(init=False)
    _apc_ema1: IncrementalEMA = field(init=False)
    _apc_ema2: IncrementalEMA = field(init=False)
    _ema_signal: IncrementalEMA = field(init=False)
    _tsi_value: float = field(default=np.nan, init=False)
    _signal_line: float = field(default=np.nan, init=False)
    _count: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self._pc_ema1 = IncrementalEMA(length=self.slow)
        self._pc_ema2 = IncrementalEMA(length=self.fast)
        self._apc_ema1 = IncrementalEMA(length=self.slow)
        self._apc_ema2 = IncrementalEMA(length=self.fast)
        self._ema_signal = IncrementalEMA(length=self.signal)

    def update(self, close: float, **kwargs: Any) -> None:
        """Update with new close price."""
        self._count += 1

        if self._count == 1:
            self._prev_close = close
            return

        # Momentum (price change)
        pc = close - self._prev_close
        apc = abs(pc)
        self._prev_close = close

        # Double smoothing of momentum
        self._pc_ema1.update(close=pc)
        self._apc_ema1.update(close=apc)

        if self._pc_ema1.is_ready and self._apc_ema1.is_ready:
            self._pc_ema2.update(close=self._pc_ema1.value)
            self._apc_ema2.update(close=self._apc_ema1.value)

            if self._pc_ema2.is_ready and self._apc_ema2.is_ready:
                apc_val = self._apc_ema2.value
                if apc_val != 0:
                    self._tsi_value = (self._pc_ema2.value / apc_val) * 100.0
                    self._ema_signal.update(close=self._tsi_value)

                    if self._ema_signal.is_ready:
                        self._signal_line = self._ema_signal.value

    def reset(self) -> None:
        self._prev_close = np.nan
        self._pc_ema1.reset()
        self._pc_ema2.reset()
        self._apc_ema1.reset()
        self._apc_ema2.reset()
        self._ema_signal.reset()
        self._tsi_value = np.nan
        self._signal_line = np.nan
        self._count = 0

    @property
    def value(self) -> float:
        """Returns TSI value."""
        return self._tsi_value

    @property
    def tsi_value(self) -> float:
        """Returns TSI value."""
        return self._tsi_value

    @property
    def signal_value(self) -> float:
        """Returns signal line value."""
        return self._signal_line

    @property
    def is_ready(self) -> bool:
        return not np.isnan(self._tsi_value)


# =============================================================================
# Phase 3: SMA/Buffer-Based Indicators
# =============================================================================


@dataclass
class IncrementalWMA(IncrementalIndicator):
    """
    Weighted Moving Average with O(1) updates using ring buffer.

    Formula:
        wma = sum(weight[i] * close[i]) / sum(weights)
        where weight[i] = i + 1 (linear weights, most recent has highest weight)

    Uses running weighted sum technique for O(1) updates.
    Matches pandas_ta.wma() output.
    """

    length: int = 20
    _buffer: deque = field(default_factory=deque, init=False)
    _count: int = field(default=0, init=False)
    _weight_sum: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        # Weight sum = 1 + 2 + ... + length = length * (length + 1) / 2
        self._weight_sum = self.length * (self.length + 1) // 2

    def update(self, close: float, **kwargs: Any) -> None:
        """Update with new close price."""
        self._count += 1
        self._buffer.append(close)

        if len(self._buffer) > self.length:
            self._buffer.popleft()

    def reset(self) -> None:
        self._buffer.clear()
        self._count = 0

    @property
    def value(self) -> float:
        if not self.is_ready:
            return np.nan

        # Compute weighted sum: weight[i] = i + 1
        weighted_sum = 0.0
        for i, val in enumerate(self._buffer):
            weighted_sum += (i + 1) * val

        return weighted_sum / self._weight_sum

    @property
    def is_ready(self) -> bool:
        return len(self._buffer) >= self.length


@dataclass
class IncrementalTRIMA(IncrementalIndicator):
    """
    Triangular Moving Average with O(1) updates.

    Formula:
        trima = sma(sma(close, ceil(length/2)), floor(length/2)+1)

    Uses two incremental SMAs.
    Matches pandas_ta.trima() output.
    """

    length: int = 20
    _sma1: IncrementalSMA = field(init=False)
    _sma2: IncrementalSMA = field(init=False)
    _count: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        # TRIMA uses ceil(length/2) and floor(length/2)+1
        import math
        sma1_len = math.ceil(self.length / 2)
        sma2_len = (self.length // 2) + 1
        self._sma1 = IncrementalSMA(length=sma1_len)
        self._sma2 = IncrementalSMA(length=sma2_len)

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
    Linear Regression with O(1) updates using running sums.

    Uses incremental formulas for linear regression.
    Matches pandas_ta.linreg() output.
    """

    length: int = 14
    _buffer: deque = field(default_factory=deque, init=False)
    _count: int = field(default=0, init=False)

    def update(self, close: float, **kwargs: Any) -> None:
        """Update with new close price."""
        self._count += 1
        self._buffer.append(close)

        if len(self._buffer) > self.length:
            self._buffer.popleft()

    def reset(self) -> None:
        self._buffer.clear()
        self._count = 0

    @property
    def value(self) -> float:
        if not self.is_ready:
            return np.nan

        n = self.length
        # Precompute x indices: 0, 1, 2, ..., n-1
        # For linear regression: y = a + b*x
        # b = (n*sum_xy - sum_x*sum_y) / (n*sum_xx - sum_x^2)
        # a = (sum_y - b*sum_x) / n
        # linreg value = a + b*(n-1) (value at last point)

        sum_x = (n - 1) * n / 2  # 0 + 1 + ... + (n-1)
        sum_xx = (n - 1) * n * (2 * n - 1) / 6  # Sum of squares

        sum_y = sum(self._buffer)
        sum_xy = sum(i * val for i, val in enumerate(self._buffer))

        denominator = n * sum_xx - sum_x * sum_x
        if denominator == 0:
            return self._buffer[-1]  # Fallback to last value

        b = (n * sum_xy - sum_x * sum_y) / denominator
        a = (sum_y - b * sum_x) / n

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

    Formula (using RMA/Wilder's smoothing for pandas_ta default):
        pos = rma(positive_changes)
        neg = rma(abs(negative_changes))
        cmo = ((pos - neg) / (pos + neg)) * 100

    Uses RMA (Wilder's smoothing) to match pandas_ta.cmo(talib=True) default.
    Matches pandas_ta.cmo() output.
    """

    length: int = 14
    _prev_close: float = field(default=np.nan, init=False)
    _pos_rma: float = field(default=np.nan, init=False)
    _neg_rma: float = field(default=np.nan, init=False)
    _warmup_pos: list = field(default_factory=list, init=False)
    _warmup_neg: list = field(default_factory=list, init=False)
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

        # RMA (Wilder's smoothing): first value is SMA, then exponential
        if self._change_count <= self.length:
            self._warmup_pos.append(pos)
            self._warmup_neg.append(neg)

            if self._change_count == self.length:
                self._pos_rma = sum(self._warmup_pos) / self.length
                self._neg_rma = sum(self._warmup_neg) / self.length
        else:
            alpha = 1.0 / self.length
            self._pos_rma = alpha * pos + (1 - alpha) * self._pos_rma
            self._neg_rma = alpha * neg + (1 - alpha) * self._neg_rma

    def reset(self) -> None:
        self._prev_close = np.nan
        self._pos_rma = np.nan
        self._neg_rma = np.nan
        self._warmup_pos.clear()
        self._warmup_neg.clear()
        self._change_count = 0
        self._count = 0

    @property
    def value(self) -> float:
        if not self.is_ready:
            return np.nan

        total = self._pos_rma + self._neg_rma
        if total == 0:
            return 0.0

        return ((self._pos_rma - self._neg_rma) / total) * 100.0

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
            # First bar: no previous TP, no flow direction
            self._pos_mf_buffer.append(0.0)
            self._neg_mf_buffer.append(0.0)
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


# =============================================================================
# Phase 4: Lookback-Based Indicators
# =============================================================================


@dataclass
class IncrementalAROON(IncrementalIndicator):
    """
    Aroon Indicator with O(1) updates.

    Formula:
        aroon_up = ((length - bars_since_high) / length) * 100
        aroon_down = ((length - bars_since_low) / length) * 100
        aroon_osc = aroon_up - aroon_down

    Matches pandas_ta.aroon() output.
    """

    length: int = 25
    _high_buffer: deque = field(default_factory=deque, init=False)
    _low_buffer: deque = field(default_factory=deque, init=False)
    _count: int = field(default=0, init=False)

    def update(self, high: float, low: float, **kwargs: Any) -> None:
        """Update with new high/low data."""
        self._count += 1

        self._high_buffer.append(high)
        self._low_buffer.append(low)

        if len(self._high_buffer) > self.length + 1:
            self._high_buffer.popleft()
            self._low_buffer.popleft()

    def reset(self) -> None:
        self._high_buffer.clear()
        self._low_buffer.clear()
        self._count = 0

    def _bars_since_high(self) -> int:
        """Find bars since highest high."""
        max_val = max(self._high_buffer)
        # Find most recent occurrence of max
        for i in range(len(self._high_buffer) - 1, -1, -1):
            if self._high_buffer[i] == max_val:
                return len(self._high_buffer) - 1 - i
        return 0

    def _bars_since_low(self) -> int:
        """Find bars since lowest low."""
        min_val = min(self._low_buffer)
        # Find most recent occurrence of min
        for i in range(len(self._low_buffer) - 1, -1, -1):
            if self._low_buffer[i] == min_val:
                return len(self._low_buffer) - 1 - i
        return 0

    @property
    def value(self) -> float:
        """Returns Aroon Oscillator value."""
        return self.osc_value

    @property
    def up_value(self) -> float:
        """Returns Aroon Up value."""
        if not self.is_ready:
            return np.nan
        bars_since = self._bars_since_high()
        return ((self.length - bars_since) / self.length) * 100.0

    @property
    def down_value(self) -> float:
        """Returns Aroon Down value."""
        if not self.is_ready:
            return np.nan
        bars_since = self._bars_since_low()
        return ((self.length - bars_since) / self.length) * 100.0

    @property
    def osc_value(self) -> float:
        """Returns Aroon Oscillator (Up - Down)."""
        if not self.is_ready:
            return np.nan
        return self.up_value - self.down_value

    @property
    def is_ready(self) -> bool:
        return len(self._high_buffer) > self.length


@dataclass
class IncrementalDonchian(IncrementalIndicator):
    """
    Donchian Channel with O(1) updates.

    Formula:
        upper = max(high over upper_length)
        lower = min(low over lower_length)
        middle = (upper + lower) / 2

    Matches pandas_ta.donchian() output.
    """

    lower_length: int = 20
    upper_length: int = 20
    _high_buffer: deque = field(default_factory=deque, init=False)
    _low_buffer: deque = field(default_factory=deque, init=False)
    _count: int = field(default=0, init=False)

    def update(self, high: float, low: float, **kwargs: Any) -> None:
        """Update with new high/low data."""
        self._count += 1

        self._high_buffer.append(high)
        self._low_buffer.append(low)

        # Use max of the two lengths for buffer size
        max_len = max(self.lower_length, self.upper_length)
        if len(self._high_buffer) > max_len:
            self._high_buffer.popleft()
            self._low_buffer.popleft()

    def reset(self) -> None:
        self._high_buffer.clear()
        self._low_buffer.clear()
        self._count = 0

    @property
    def value(self) -> float:
        """Returns middle band (default)."""
        return self.middle_value

    @property
    def upper_value(self) -> float:
        """Returns upper band (highest high)."""
        if not self.is_ready:
            return np.nan
        # Use only the most recent upper_length values
        buffer_len = len(self._high_buffer)
        start_idx = max(0, buffer_len - self.upper_length)
        return max(list(self._high_buffer)[start_idx:])

    @property
    def lower_value(self) -> float:
        """Returns lower band (lowest low)."""
        if not self.is_ready:
            return np.nan
        # Use only the most recent lower_length values
        buffer_len = len(self._low_buffer)
        start_idx = max(0, buffer_len - self.lower_length)
        return min(list(self._low_buffer)[start_idx:])

    @property
    def middle_value(self) -> float:
        """Returns middle band."""
        if not self.is_ready:
            return np.nan
        return (self.upper_value + self.lower_value) / 2.0

    @property
    def is_ready(self) -> bool:
        return len(self._high_buffer) >= max(self.lower_length, self.upper_length)


@dataclass
class IncrementalKC(IncrementalIndicator):
    """
    Keltner Channel with O(1) updates.

    Formula:
        basis = ema(close, length)
        band = ema(true_range, length)  # pandas_ta uses EMA, not ATR's RMA
        upper = basis + scalar * band
        lower = basis - scalar * band

    Uses EMA for both basis and band to match pandas_ta.kc() default.
    Matches pandas_ta.kc() output.
    """

    length: int = 20
    scalar: float = 2.0
    _ema_close: IncrementalEMA = field(init=False)
    _ema_tr: IncrementalEMA = field(init=False)
    _prev_close: float = field(default=np.nan, init=False)
    _count: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self._ema_close = IncrementalEMA(length=self.length)
        self._ema_tr = IncrementalEMA(length=self.length)

    def update(
        self, high: float, low: float, close: float, **kwargs: Any
    ) -> None:
        """Update with new OHLC data."""
        self._count += 1

        # Always update close EMA
        self._ema_close.update(close=close)

        # Calculate True Range - pandas_ta skips first bar (NaN)
        if self._count == 1:
            # First bar: no TR yet (matches pandas_ta true_range which returns NaN)
            pass
        else:
            tr = max(
                high - low,
                abs(high - self._prev_close),
                abs(low - self._prev_close)
            )
            self._ema_tr.update(close=tr)

        self._prev_close = close

    def reset(self) -> None:
        self._ema_close.reset()
        self._ema_tr.reset()
        self._prev_close = np.nan
        self._count = 0

    @property
    def value(self) -> float:
        """Returns basis (middle band)."""
        return self.basis_value

    @property
    def basis_value(self) -> float:
        """Returns basis (EMA)."""
        if not self.is_ready:
            return np.nan
        return self._ema_close.value

    @property
    def upper_value(self) -> float:
        """Returns upper band."""
        if not self.is_ready:
            return np.nan
        return self._ema_close.value + self.scalar * self._ema_tr.value

    @property
    def lower_value(self) -> float:
        """Returns lower band."""
        if not self.is_ready:
            return np.nan
        return self._ema_close.value - self.scalar * self._ema_tr.value

    @property
    def is_ready(self) -> bool:
        return self._ema_close.is_ready and self._ema_tr.is_ready


@dataclass
class IncrementalDM(IncrementalIndicator):
    """
    Directional Movement with O(1) updates.

    Formula (TA-Lib compatible):
        +DM = max(high - prev_high, 0) if (high - prev_high) > (prev_low - low) else 0
        -DM = max(prev_low - low, 0) if (prev_low - low) > (high - prev_high) else 0

    Smoothing (Wilder's cumulative method):
        First value = sum of first 'length' DM values
        Subsequent = prev - (prev / length) + current

    This matches TA-Lib's PLUS_DM/MINUS_DM which pandas_ta uses by default.
    """

    length: int = 14
    _prev_high: float = field(default=np.nan, init=False)
    _prev_low: float = field(default=np.nan, init=False)
    _smoothed_plus_dm: float = field(default=np.nan, init=False)
    _smoothed_minus_dm: float = field(default=np.nan, init=False)
    _dm_count: int = field(default=0, init=False)
    _warmup_plus: list = field(default_factory=list, init=False)
    _warmup_minus: list = field(default_factory=list, init=False)
    _count: int = field(default=0, init=False)

    def update(self, high: float, low: float, **kwargs: Any) -> None:
        """Update with new high/low data."""
        self._count += 1

        if self._count == 1:
            self._prev_high = high
            self._prev_low = low
            return

        # Compute directional movement
        up_move = high - self._prev_high
        down_move = self._prev_low - low

        plus_dm = up_move if up_move > down_move and up_move > 0 else 0.0
        minus_dm = down_move if down_move > up_move and down_move > 0 else 0.0

        self._prev_high = high
        self._prev_low = low

        # Wilder's cumulative smoothing (TA-Lib style)
        # TA-Lib first valid at index (length-1), using (length-1) raw DM values
        self._dm_count += 1

        if self._dm_count < self.length:
            self._warmup_plus.append(plus_dm)
            self._warmup_minus.append(minus_dm)

            if self._dm_count == self.length - 1:
                # First smoothed value is sum of first (length-1) values
                self._smoothed_plus_dm = sum(self._warmup_plus)
                self._smoothed_minus_dm = sum(self._warmup_minus)
        else:
            # Decay formula: prev - (prev / length) + current
            self._smoothed_plus_dm = self._smoothed_plus_dm - (self._smoothed_plus_dm / self.length) + plus_dm
            self._smoothed_minus_dm = self._smoothed_minus_dm - (self._smoothed_minus_dm / self.length) + minus_dm

    def reset(self) -> None:
        self._prev_high = np.nan
        self._prev_low = np.nan
        self._smoothed_plus_dm = np.nan
        self._smoothed_minus_dm = np.nan
        self._dm_count = 0
        self._warmup_plus.clear()
        self._warmup_minus.clear()
        self._count = 0

    @property
    def value(self) -> float:
        """Returns +DM value."""
        return self.dmp_value

    @property
    def dmp_value(self) -> float:
        """Returns +DM (smoothed)."""
        if not self.is_ready:
            return np.nan
        return self._smoothed_plus_dm

    @property
    def dmn_value(self) -> float:
        """Returns -DM (smoothed)."""
        if not self.is_ready:
            return np.nan
        return self._smoothed_minus_dm

    @property
    def is_ready(self) -> bool:
        return self._dm_count >= self.length - 1


@dataclass
class IncrementalVortex(IncrementalIndicator):
    """
    Vortex Indicator with O(1) updates.

    Formula:
        VM+ = |high - prev_low|
        VM- = |low - prev_high|
        TR = true range
        VI+ = sum(VM+, length) / sum(TR, length)
        VI- = sum(VM-, length) / sum(TR, length)

    Matches pandas_ta.vortex() output.
    """

    length: int = 14
    _prev_high: float = field(default=np.nan, init=False)
    _prev_low: float = field(default=np.nan, init=False)
    _prev_close: float = field(default=np.nan, init=False)
    _vmp_buffer: deque = field(default_factory=deque, init=False)
    _vmm_buffer: deque = field(default_factory=deque, init=False)
    _tr_buffer: deque = field(default_factory=deque, init=False)
    _vmp_sum: float = field(default=0.0, init=False)
    _vmm_sum: float = field(default=0.0, init=False)
    _tr_sum: float = field(default=0.0, init=False)
    _count: int = field(default=0, init=False)

    def update(
        self, high: float, low: float, close: float, **kwargs: Any
    ) -> None:
        """Update with new HLC data."""
        self._count += 1

        if self._count == 1:
            self._prev_high = high
            self._prev_low = low
            self._prev_close = close
            # First bar: no VM or TR yet
            self._vmp_buffer.append(0.0)
            self._vmm_buffer.append(0.0)
            self._tr_buffer.append(high - low)
            self._tr_sum += high - low
            return

        # Vortex Movement
        vmp = abs(high - self._prev_low)
        vmm = abs(low - self._prev_high)

        # True Range
        tr = max(
            high - low,
            abs(high - self._prev_close),
            abs(low - self._prev_close),
        )

        self._prev_high = high
        self._prev_low = low
        self._prev_close = close

        self._vmp_sum += vmp
        self._vmm_sum += vmm
        self._tr_sum += tr
        self._vmp_buffer.append(vmp)
        self._vmm_buffer.append(vmm)
        self._tr_buffer.append(tr)

        if len(self._vmp_buffer) > self.length:
            oldest_vmp = self._vmp_buffer.popleft()
            oldest_vmm = self._vmm_buffer.popleft()
            oldest_tr = self._tr_buffer.popleft()
            self._vmp_sum -= oldest_vmp
            self._vmm_sum -= oldest_vmm
            self._tr_sum -= oldest_tr

    def reset(self) -> None:
        self._prev_high = np.nan
        self._prev_low = np.nan
        self._prev_close = np.nan
        self._vmp_buffer.clear()
        self._vmm_buffer.clear()
        self._tr_buffer.clear()
        self._vmp_sum = 0.0
        self._vmm_sum = 0.0
        self._tr_sum = 0.0
        self._count = 0

    @property
    def value(self) -> float:
        """Returns VI+ value."""
        return self.vip_value

    @property
    def vip_value(self) -> float:
        """Returns VI+ (bullish vortex)."""
        if not self.is_ready:
            return np.nan
        if self._tr_sum == 0:
            return 0.0
        return self._vmp_sum / self._tr_sum

    @property
    def vim_value(self) -> float:
        """Returns VI- (bearish vortex)."""
        if not self.is_ready:
            return np.nan
        if self._tr_sum == 0:
            return 0.0
        return self._vmm_sum / self._tr_sum

    @property
    def is_ready(self) -> bool:
        return len(self._vmp_buffer) >= self.length


# =============================================================================
# Phase 5: Complex Adaptive Indicators
# =============================================================================


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
    Arnaud Legoux Moving Average with O(1) updates.

    Formula (matching pandas_ta):
        k = floor(offset * (length - 1))
        weight[i] = exp(-0.5 * ((sigma / length) * (i - k))^2)

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
        """Update with new close price."""
        self._count += 1
        self._buffer.append(close)

        if len(self._buffer) > self.length:
            self._buffer.popleft()

    def reset(self) -> None:
        self._buffer.clear()
        self._count = 0

    @property
    def value(self) -> float:
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


# =============================================================================
# Phase 6: Stateful Multi-Output Indicators
# =============================================================================


@dataclass
class IncrementalPSAR(IncrementalIndicator):
    """
    Parabolic SAR with O(1) updates.

    Matches pandas_ta.psar() exactly:
    - Bar 0: sar = close (first close), ep based on initial trend
    - Bar 1+: sar = prev_sar + af * (ep - prev_sar), then clamp and check reversal
    - Initial trend determined by _falling(first 2 bars)
    """

    af0: float = 0.02
    af: float = 0.02
    max_af: float = 0.2
    _falling: bool = field(default=False, init=False)  # True = downtrend
    _sar: float = field(default=np.nan, init=False)
    _ep: float = field(default=np.nan, init=False)  # Extreme point
    _af_current: float = field(default=0.02, init=False)
    _prev_high: float = field(default=np.nan, init=False)
    _prev_low: float = field(default=np.nan, init=False)
    _first_high: float = field(default=np.nan, init=False)
    _first_low: float = field(default=np.nan, init=False)
    _reversal: bool = field(default=False, init=False)
    _count: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self._af_current = self.af0

    def update(
        self, high: float, low: float, close: float, **kwargs: Any
    ) -> None:
        """Update with new HLC data."""
        self._count += 1
        self._reversal = False

        if self._count == 1:
            # Bar 0: save values, set sar = close, will determine trend on bar 1
            self._first_high = high
            self._first_low = low
            self._sar = close
            self._prev_high = high
            self._prev_low = low
            return

        if self._count == 2:
            # Determine initial falling (using pandas_ta _falling logic)
            # _falling = (high[1] < high[0]) & (low[1] < low[0])
            self._falling = (high < self._first_high) and (low < self._first_low)
            self._ep = self._first_low if self._falling else self._first_high

        # Calculate new SAR
        new_sar = self._sar + self._af_current * (self._ep - self._sar)

        if self._falling:
            # Downtrend: check for upward reversal
            reverse = high > new_sar
            if low < self._ep:
                self._ep = low
                self._af_current = min(self._af_current + self.af0, self.max_af)
            # Clamp SAR: can't be below prior high
            new_sar = max(self._prev_high, new_sar)
        else:
            # Uptrend: check for downward reversal
            reverse = low < new_sar
            if high > self._ep:
                self._ep = high
                self._af_current = min(self._af_current + self.af0, self.max_af)
            # Clamp SAR: can't be above prior low
            new_sar = min(self._prev_low, new_sar)

        if reverse:
            new_sar = self._ep
            self._af_current = self.af0
            self._falling = not self._falling
            self._ep = low if self._falling else high
            self._reversal = True

        self._sar = new_sar
        self._prev_high = high
        self._prev_low = low

    def reset(self) -> None:
        self._falling = False
        self._sar = np.nan
        self._ep = np.nan
        self._af_current = self.af0
        self._prev_high = np.nan
        self._prev_low = np.nan
        self._first_high = np.nan
        self._first_low = np.nan
        self._reversal = False
        self._count = 0

    @property
    def value(self) -> float:
        """Returns current SAR value."""
        if self._count < 2:
            return np.nan
        return self._sar

    @property
    def long_value(self) -> float:
        """Returns SAR value when in uptrend (NaN when downtrend)."""
        if self._count < 2:
            return np.nan
        return np.nan if self._falling else self._sar

    @property
    def short_value(self) -> float:
        """Returns SAR value when in downtrend (NaN when uptrend)."""
        if self._count < 2:
            return np.nan
        return self._sar if self._falling else np.nan

    @property
    def af_value(self) -> float:
        """Returns current acceleration factor."""
        if not self.is_ready:
            return np.nan
        return self._af_current

    @property
    def reversal_value(self) -> int:
        """Returns 1 if reversal occurred this bar, else 0."""
        return self._reversal

    @property
    def is_ready(self) -> bool:
        return self._count >= 2


@dataclass
class IncrementalSqueeze(IncrementalIndicator):
    """
    Squeeze Momentum Indicator with O(1) updates.

    Formula (pandas_ta default, lazybear=False, mamode='sma'):
        sqz = sma(mom(close, mom_length), mom_smooth)

    Also tracks squeeze on/off state via BBands vs KC comparison.
    Matches pandas_ta.squeeze() output.
    """

    bb_length: int = 20
    bb_std: float = 2.0
    kc_length: int = 20
    kc_scalar: float = 1.5
    mom_length: int = 12
    mom_smooth: int = 6
    _bbands: IncrementalBBands = field(init=False)
    _kc: IncrementalKC = field(init=False)
    _mom: IncrementalMOM = field(init=False)
    _sma_mom: IncrementalSMA = field(init=False)
    _count: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self._bbands = IncrementalBBands(length=self.bb_length, std_dev=self.bb_std)
        self._kc = IncrementalKC(length=self.kc_length, scalar=self.kc_scalar)
        self._mom = IncrementalMOM(length=self.mom_length)
        self._sma_mom = IncrementalSMA(length=self.mom_smooth)

    def update(
        self, high: float, low: float, close: float, **kwargs: Any
    ) -> None:
        """Update with new HLC data."""
        self._count += 1
        self._bbands.update(close=close)
        self._kc.update(high=high, low=low, close=close)
        self._mom.update(close=close)
        if self._mom.is_ready:
            self._sma_mom.update(close=self._mom.value)

    def reset(self) -> None:
        self._bbands.reset()
        self._kc.reset()
        self._mom.reset()
        self._sma_mom.reset()
        self._count = 0

    @property
    def value(self) -> float:
        """Returns squeeze momentum value."""
        return self.sqz_value

    @property
    def sqz_value(self) -> float:
        """Returns squeeze momentum (SMA of momentum)."""
        if not self._sma_mom.is_ready:
            return np.nan
        return self._sma_mom.value

    @property
    def on_value(self) -> int:
        """Returns 1 if squeeze is ON (BB inside KC)."""
        if not self.is_ready:
            return 0
        bb_lower = self._bbands.lower
        bb_upper = self._bbands.upper
        kc_lower = self._kc.lower_value
        kc_upper = self._kc.upper_value
        return 1 if bb_lower > kc_lower and bb_upper < kc_upper else 0

    @property
    def off_value(self) -> int:
        """Returns 1 if squeeze is OFF (BB outside KC)."""
        if not self.is_ready:
            return 0
        bb_lower = self._bbands.lower
        bb_upper = self._bbands.upper
        kc_lower = self._kc.lower_value
        kc_upper = self._kc.upper_value
        return 1 if bb_lower < kc_lower and bb_upper > kc_upper else 0

    @property
    def no_sqz_value(self) -> int:
        """Returns 1 if no squeeze condition (neutral)."""
        if not self.is_ready:
            return 0
        return 1 if self.on_value == 0 and self.off_value == 0 else 0

    @property
    def is_ready(self) -> bool:
        return self._bbands.is_ready and self._kc.is_ready and self._sma_mom.is_ready


@dataclass
class IncrementalFisher(IncrementalIndicator):
    """
    Fisher Transform with O(1) updates.

    Formula (matching pandas_ta):
        hl2 = (high + low) / 2
        highest_hl2 = max(hl2) over length
        lowest_hl2 = min(hl2) over length
        position = ((hl2 - lowest_hl2) / range) - 0.5
        v = 0.66 * position + 0.67 * v_prev (smoothed)
        v = clip(v, -0.999, 0.999)
        fisher = 0.5 * (log((1 + v) / (1 - v)) + fisher_prev)
        signal = fisher shifted by signal_length (default 1)

    First fisher value at index length-1 is 0.
    """

    length: int = 9
    signal: int = 1
    _hl2_buffer: deque = field(default_factory=deque, init=False)
    _v: float = field(default=0.0, init=False)
    _fisher: float = field(default=np.nan, init=False)
    _fisher_hist: deque = field(default_factory=deque, init=False)
    _signal_val: float = field(default=np.nan, init=False)
    _count: int = field(default=0, init=False)
    _initialized: bool = field(default=False, init=False)

    def update(self, high: float, low: float, **kwargs: Any) -> None:
        """Update with new high/low data."""
        self._count += 1

        hl2 = (high + low) / 2.0
        self._hl2_buffer.append(hl2)

        if len(self._hl2_buffer) > self.length:
            self._hl2_buffer.popleft()

        if len(self._hl2_buffer) < self.length:
            return

        if not self._initialized:
            # First bar with enough data (index = length-1)
            # pandas_ta starts fisher at 0
            self._fisher = 0.0
            self._fisher_hist.append(0.0)
            self._initialized = True
            return

        # Subsequent bars - compute fisher
        highest_hl2 = max(self._hl2_buffer)
        lowest_hl2 = min(self._hl2_buffer)

        hlr = highest_hl2 - lowest_hl2
        if hlr < 0.001:
            hlr = 0.001

        position = ((hl2 - lowest_hl2) / hlr) - 0.5

        # Smooth position
        self._v = 0.66 * position + 0.67 * self._v
        if self._v < -0.99:
            self._v = -0.999
        if self._v > 0.99:
            self._v = 0.999

        # Fisher transform with recursive smoothing
        prev_fisher = self._fisher
        self._fisher = 0.5 * (np.log((1 + self._v) / (1 - self._v)) + prev_fisher)

        # Track history for signal
        self._fisher_hist.append(self._fisher)
        if len(self._fisher_hist) > self.signal + 1:
            self._fisher_hist.popleft()

        # Signal is fisher shifted by signal_length
        if len(self._fisher_hist) > self.signal:
            self._signal_val = self._fisher_hist[-self.signal - 1]

    def reset(self) -> None:
        self._hl2_buffer.clear()
        self._v = 0.0
        self._fisher = np.nan
        self._fisher_hist.clear()
        self._signal_val = np.nan
        self._count = 0
        self._initialized = False

    @property
    def value(self) -> float:
        """Returns Fisher value."""
        if not self.is_ready:
            return np.nan
        return self._fisher

    @property
    def fisher_value(self) -> float:
        """Returns Fisher value."""
        if not self.is_ready:
            return np.nan
        return self._fisher

    @property
    def signal_value(self) -> float:
        """Returns signal (Fisher shifted by signal period)."""
        return self._signal_val

    @property
    def is_ready(self) -> bool:
        return len(self._hl2_buffer) >= self.length


# =============================================================================
# Phase 7: Volume Complex Indicators
# =============================================================================


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

    Note: VWAP typically resets daily. This implementation is cumulative
    from start. For daily reset, call reset() at session boundaries.

    Matches pandas_ta.vwap() output for cumulative mode.
    """

    _cum_tp_vol: float = field(default=0.0, init=False)
    _cum_vol: float = field(default=0.0, init=False)
    _count: int = field(default=0, init=False)

    def update(
        self, high: float, low: float, close: float, volume: float, **kwargs: Any
    ) -> None:
        """Update with new OHLCV data."""
        self._count += 1

        tp = (high + low + close) / 3.0
        self._cum_tp_vol += tp * volume
        self._cum_vol += volume

    def reset(self) -> None:
        """Reset VWAP (call at session boundaries)."""
        self._cum_tp_vol = 0.0
        self._cum_vol = 0.0
        self._count = 0

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
    elif indicator_type == "willr":
        return IncrementalWilliamsR(length=params.get("length", 14))
    elif indicator_type == "cci":
        return IncrementalCCI(length=params.get("length", 14))
    elif indicator_type == "stoch":
        return IncrementalStochastic(
            k_period=params.get("k", 14),
            smooth_k=params.get("smooth_k", 3),
            d_period=params.get("d", 3),
        )
    elif indicator_type == "stochrsi":
        return IncrementalStochRSI(
            length=params.get("length", 14),
            rsi_length=params.get("rsi_length", 14),
            k=params.get("k", 3),
            d=params.get("d", 3),
        )
    elif indicator_type == "adx":
        return IncrementalADX(length=params.get("length", 14))
    elif indicator_type == "supertrend":
        return IncrementalSuperTrend(
            length=params.get("length", 10),
            multiplier=params.get("multiplier", 3.0),
        )
    # Phase 1: Trivial indicators
    elif indicator_type == "ohlc4":
        return IncrementalOHLC4()
    elif indicator_type == "midprice":
        return IncrementalMidprice(length=params.get("length", 14))
    elif indicator_type == "roc":
        return IncrementalROC(length=params.get("length", 10))
    elif indicator_type == "mom":
        return IncrementalMOM(length=params.get("length", 10))
    elif indicator_type == "obv":
        return IncrementalOBV()
    elif indicator_type == "natr":
        return IncrementalNATR(length=params.get("length", 14))
    # Phase 2: EMA-composable indicators
    elif indicator_type == "dema":
        return IncrementalDEMA(length=params.get("length", 20))
    elif indicator_type == "tema":
        return IncrementalTEMA(length=params.get("length", 20))
    elif indicator_type == "ppo":
        return IncrementalPPO(
            fast=params.get("fast", 12),
            slow=params.get("slow", 26),
            signal=params.get("signal", 9),
        )
    elif indicator_type == "trix":
        return IncrementalTRIX(
            length=params.get("length", 18),
            signal=params.get("signal", 9),
        )
    elif indicator_type == "tsi":
        return IncrementalTSI(
            fast=params.get("fast", 13),
            slow=params.get("slow", 25),
            signal=params.get("signal", 13),
        )
    # Phase 3: SMA/Buffer-based indicators
    elif indicator_type == "wma":
        return IncrementalWMA(length=params.get("length", 20))
    elif indicator_type == "trima":
        return IncrementalTRIMA(length=params.get("length", 20))
    elif indicator_type == "linreg":
        return IncrementalLINREG(length=params.get("length", 14))
    elif indicator_type == "cmf":
        return IncrementalCMF(length=params.get("length", 20))
    elif indicator_type == "cmo":
        return IncrementalCMO(length=params.get("length", 14))
    elif indicator_type == "mfi":
        return IncrementalMFI(length=params.get("length", 14))
    # Phase 4: Lookback-based indicators
    elif indicator_type == "aroon":
        return IncrementalAROON(length=params.get("length", 25))
    elif indicator_type == "donchian":
        return IncrementalDonchian(
            lower_length=params.get("lower_length", 20),
            upper_length=params.get("upper_length", 20),
        )
    elif indicator_type == "kc":
        return IncrementalKC(
            length=params.get("length", 20),
            scalar=params.get("scalar", 2.0),
        )
    elif indicator_type == "dm":
        return IncrementalDM(length=params.get("length", 14))
    elif indicator_type == "vortex":
        return IncrementalVortex(length=params.get("length", 14))
    # Phase 5: Complex adaptive indicators
    elif indicator_type == "kama":
        return IncrementalKAMA(length=params.get("length", 10))
    elif indicator_type == "alma":
        return IncrementalALMA(
            length=params.get("length", 10),
            sigma=params.get("sigma", 6.0),
            offset=params.get("offset", 0.85),
        )
    elif indicator_type == "zlma":
        return IncrementalZLMA(length=params.get("length", 20))
    elif indicator_type == "uo":
        return IncrementalUO(
            fast=params.get("fast", 7),
            medium=params.get("medium", 14),
            slow=params.get("slow", 28),
        )
    # Phase 6: Stateful multi-output indicators
    elif indicator_type == "psar":
        return IncrementalPSAR(
            af0=params.get("af0", 0.02),
            af=params.get("af", 0.02),
            max_af=params.get("max_af", 0.2),
        )
    elif indicator_type == "squeeze":
        return IncrementalSqueeze(
            bb_length=params.get("bb_length", 20),
            bb_std=params.get("bb_std", 2.0),
            kc_length=params.get("kc_length", 20),
            kc_scalar=params.get("kc_scalar", 1.5),
        )
    elif indicator_type == "fisher":
        return IncrementalFisher(length=params.get("length", 9))
    # Phase 7: Volume complex indicators
    elif indicator_type == "kvo":
        return IncrementalKVO(
            fast=params.get("fast", 34),
            slow=params.get("slow", 55),
            signal=params.get("signal", 13),
        )
    elif indicator_type == "vwap":
        return IncrementalVWAP()
    else:
        # Not supported incrementally - will fall back to vectorized
        return None


# =============================================================================
# Registry Integration
# =============================================================================
# The canonical source of truth for incremental support is indicator_registry.py.
# These functions delegate to the registry to maintain a single source of truth.


def supports_incremental(indicator_type: str) -> bool:
    """
    Check if indicator type supports incremental computation.

    Delegates to indicator_registry for single source of truth.
    """
    from src.backtest.indicator_registry import supports_incremental as registry_supports
    return registry_supports(indicator_type)


def list_incremental_indicators() -> list[str]:
    """
    Get list of all indicators that support incremental computation.

    Delegates to indicator_registry for single source of truth.
    """
    from src.backtest.indicator_registry import list_incremental_indicators as registry_list
    return registry_list()


# INCREMENTAL_INDICATORS is computed from registry at import time
# This ensures backward compatibility while using the registry as source of truth
INCREMENTAL_INDICATORS = frozenset(list_incremental_indicators())
