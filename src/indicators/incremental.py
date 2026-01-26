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
    elif indicator_type == "adx":
        return IncrementalADX(length=params.get("length", 14))
    elif indicator_type == "supertrend":
        return IncrementalSuperTrend(
            length=params.get("length", 10),
            multiplier=params.get("multiplier", 3.0),
        )
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
