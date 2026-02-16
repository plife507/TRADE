"""
Core incremental indicators: the original 12 indicators.

Includes EMA, SMA, RSI, ATR, MACD, BBands, WilliamsR, CCI,
Stochastic, StochRSI, ADX, and SuperTrend.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .base import IncrementalIndicator


@dataclass
class IncrementalEMA(IncrementalIndicator):
    """
    Exponential Moving Average with O(1) updates.

    Formula:
        alpha = 2 / (length + 1)
        ema = alpha * close + (1 - alpha) * ema_prev

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

    Uses RMA (Wilder's Moving Average) via ewm(alpha=1/length, adjust=False):
        avg_gain[0] = gain[0]
        avg_gain[i] = alpha * gain[i] + (1 - alpha) * avg_gain[i-1]
        (same for avg_loss)
        rs = avg_gain / avg_loss
        rsi = 100 * avg_gain / (avg_gain + abs(avg_loss))

    Matches pandas_ta.rsi(talib=False) output exactly.
    """

    length: int = 14
    _prev_close: float = field(default=np.nan, init=False)
    _avg_gain: float = field(default=np.nan, init=False)
    _avg_loss: float = field(default=np.nan, init=False)
    _count: int = field(default=0, init=False)
    _alpha: float = field(init=False)

    def __post_init__(self) -> None:
        self._alpha = 1.0 / self.length

    def update(self, close: float, **kwargs: Any) -> None:
        """Update with new close price."""
        self._count += 1

        if self._count == 1:
            self._prev_close = close
            return

        # Compute gain/loss
        change = close - self._prev_close
        gain = max(0.0, change)
        loss = max(0.0, -change)
        self._prev_close = close

        # RMA: ewm(alpha=1/length, adjust=False)
        # First value seeds the EWM, subsequent values use exponential smoothing
        if self._count == 2:
            # First change value -- seed the EWM
            self._avg_gain = gain
            self._avg_loss = loss
        else:
            self._avg_gain = self._alpha * gain + (1 - self._alpha) * self._avg_gain
            self._avg_loss = self._alpha * loss + (1 - self._alpha) * self._avg_loss

    def reset(self) -> None:
        self._prev_close = np.nan
        self._avg_gain = np.nan
        self._avg_loss = np.nan
        self._count = 0

    @property
    def value(self) -> float:
        if not self.is_ready:
            return np.nan

        total = self._avg_gain + self._avg_loss
        if total == 0:
            return 50.0

        return 100.0 * self._avg_gain / total

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
        """Update with new OHLC data.

        Matches pandas_ta.atr(talib=False) with presma=True (default):
        1. Bar 0: TR = high - low (no prev close, matches pandas_ta pure path)
        2. Bars 1 to length-1: TR = max(H-L, |H-prevC|, |L-prevC|)
        3. Bar length-1: SMA seed = mean(TR[0:length])
        4. Bar length+: Wilder's RMA smoothing
        """
        self._count += 1

        if self._count == 1:
            if not self.prenan:
                # Bar 0: TR = high - low (pandas_ta pure true_range at bar 0)
                self._warmup_tr.append(high - low)
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
            # Warmup: collect TR for bars 1 through length-1
            self._warmup_tr.append(tr)
            if self._count == self.length:
                # SMA seed from length-1 TR values (bars 1 to length-1)
                self._atr = sum(self._warmup_tr) / len(self._warmup_tr)
        else:
            # Wilder's RMA: alpha * tr + (1-alpha) * prev
            alpha = 1.0 / self.length
            self._atr = alpha * tr + (1 - alpha) * self._atr

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
    Bollinger Bands with O(1) updates using running sums.

    Uses sample standard deviation (ddof=1) to match pandas_ta default:
        mean = running_sum / n
        variance = (sum_sq - n * mean^2) / (n - 1)
        std = sqrt(variance)

    Output:
        upper = mean + std_dev * std
        middle = mean
        lower = mean - std_dev * std

    Matches pandas_ta.bbands(ddof=1) output.
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
        # Sample variance (ddof=1) to match pandas_ta.bbands default
        # variance = sum((x - mean)^2) / (n - 1)
        #          = (sum(x^2) - n * mean^2) / (n - 1)
        variance = (self._running_sq_sum - n * mean * mean) / (n - 1)
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
    Commodity Channel Index with O(1) update, O(n) value access.

    Formula:
        tp = (high + low + close) / 3
        tp_sma = sma(tp, length)
        mean_dev = mean(|tp - tp_sma|) over length
        cci = (tp - tp_sma) / (0.015 * mean_dev)

    Note: The mean absolute deviation (MAD) calculation is inherently O(n)
    because changing the mean affects all |tp - mean| terms. This is a
    fundamental mathematical limitation - MAD cannot be computed incrementally.
    The update() is O(1), only value access is O(n).

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
    _adx_history: list = field(default_factory=list, init=False)  # G5.6: For ADXR

    def __post_init__(self) -> None:
        # pandas_ta ADX uses atr(..., prenan=True) internally (default kwarg)
        self._atr = IncrementalATR(length=self.length, prenan=True)

    def update(
        self, high: float, low: float, close: float, **kwargs: Any
    ) -> None:
        """
        Update with new OHLC data.

        Matches pandas_ta.adx(talib=False) calculation:
        1. Start DM smoothing from bar 1 (first bar with DM values)
        2. Compute DI when ATR is ready
        3. Start DX smoothing when first DI is valid
        """
        self._count += 1

        # Update ATR (tracks its own warmup)
        self._atr.update(high=high, low=low, close=close)

        alpha = 1.0 / self.length

        if self._count == 1:
            # Bar 0: No DM (pandas_ta DM[0] = NaN from diff). EWM skips NaN,
            # seeding from bar 1's DM value.
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

        # RMA smoothing for DM
        # ewm(alpha=1/length, adjust=False): first non-NaN seeds, then blends
        self._dm_count += 1
        if self._dm_count == 1:
            # First DM value (bar 1) seeds the EWM
            self._smoothed_plus_dm = plus_dm
            self._smoothed_minus_dm = minus_dm
        else:
            self._smoothed_plus_dm = alpha * plus_dm + (1 - alpha) * self._smoothed_plus_dm
            self._smoothed_minus_dm = alpha * minus_dm + (1 - alpha) * self._smoothed_minus_dm

        # Calculate DI values and DX when ATR is ready
        if self._atr.is_ready:
            atr_val = self._atr.value
            if atr_val > 0:
                # DI = (100/ATR) * smoothed_dm  (k * rma(dm))
                plus_di = (self._smoothed_plus_dm / atr_val) * 100.0
                minus_di = (self._smoothed_minus_dm / atr_val) * 100.0

                di_sum = plus_di + minus_di
                if di_sum > 0:
                    dx = abs(plus_di - minus_di) / di_sum * 100.0
                else:
                    dx = 0.0

                # RMA smoothing for DX
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
        if not self.is_ready:
            return np.nan
        atr_val = self._atr.value
        if atr_val <= 0 or np.isnan(self._smoothed_plus_dm):
            return np.nan
        return (self._smoothed_plus_dm / atr_val) * 100.0

    @property
    def dmn_value(self) -> float:
        """Returns -DI value."""
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
    pandas_ta.supertrend uses atr(mamode="rma") with default prenan=False.
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

    def __post_init__(self) -> None:
        # pandas_ta.supertrend uses default ATR (prenan=False)
        self._atr = IncrementalATR(length=self.length)

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
        return not np.isnan(self._prev_trend)
