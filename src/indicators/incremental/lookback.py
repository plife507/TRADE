"""
Lookback-based indicators using monotonic deques and sliding windows.

Includes AROON, Donchian, KC, DM, and Vortex -- indicators that track
min/max values over lookback windows.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .base import IncrementalIndicator
from .core import IncrementalEMA


@dataclass
class IncrementalAROON(IncrementalIndicator):
    """
    Aroon Indicator with TRUE O(1) updates using monotonic deques.

    Formula:
        aroon_up = ((length - bars_since_high) / length) * 100
        aroon_down = ((length - bars_since_low) / length) * 100
        aroon_osc = aroon_up - aroon_down

    O(1) technique:
        - Use monotonic deque for max tracking (decreasing order)
        - Use monotonic deque for min tracking (increasing order)
        - Each deque stores (value, index) tuples
        - Front of deque is always the max/min with its position

    Matches pandas_ta.aroon() output.
    """

    length: int = 25
    _count: int = field(default=0, init=False)
    # Monotonic deque for max: stores (value, index), decreasing by value
    _max_deque: deque = field(default_factory=deque, init=False)
    # Monotonic deque for min: stores (value, index), increasing by value
    _min_deque: deque = field(default_factory=deque, init=False)

    def update(self, high: float, low: float, **kwargs: Any) -> None:
        """Update with new high/low data - amortized O(1) operation."""
        current_idx = self._count
        self._count += 1

        # Window boundary: remove elements outside the window
        # pandas_ta uses rolling(length + 1), so window includes length+1 bars
        # Elements with index < (current_idx - length) are outside
        window_start = current_idx - self.length - 1
        while self._max_deque and self._max_deque[0][1] <= window_start:
            self._max_deque.popleft()
        while self._min_deque and self._min_deque[0][1] <= window_start:
            self._min_deque.popleft()

        # Maintain monotonic decreasing for max (remove smaller from back)
        # For tie-breaking with most recent, use >= to keep most recent max
        while self._max_deque and self._max_deque[-1][0] <= high:
            self._max_deque.pop()
        self._max_deque.append((high, current_idx))

        # Maintain monotonic increasing for min (remove larger from back)
        # For tie-breaking with most recent, use >= to keep most recent min
        while self._min_deque and self._min_deque[-1][0] >= low:
            self._min_deque.pop()
        self._min_deque.append((low, current_idx))

    def reset(self) -> None:
        self._max_deque.clear()
        self._min_deque.clear()
        self._count = 0

    @property
    def _bars_since_high(self) -> int:
        """Bars since highest high - O(1) via monotonic deque front."""
        if not self._max_deque:
            return 0
        _, max_idx = self._max_deque[0]
        return self._count - 1 - max_idx

    @property
    def _bars_since_low(self) -> int:
        """Bars since lowest low - O(1) via monotonic deque front."""
        if not self._min_deque:
            return 0
        _, min_idx = self._min_deque[0]
        return self._count - 1 - min_idx

    @property
    def value(self) -> float:
        """Returns Aroon Oscillator value."""
        return self.osc_value

    @property
    def up_value(self) -> float:
        """Returns Aroon Up value."""
        if not self.is_ready:
            return np.nan
        return ((self.length - self._bars_since_high) / self.length) * 100.0

    @property
    def down_value(self) -> float:
        """Returns Aroon Down value."""
        if not self.is_ready:
            return np.nan
        return ((self.length - self._bars_since_low) / self.length) * 100.0

    @property
    def osc_value(self) -> float:
        """Returns Aroon Oscillator (Up - Down)."""
        if not self.is_ready:
            return np.nan
        return self.up_value - self.down_value

    @property
    def is_ready(self) -> bool:
        return self._count > self.length


@dataclass
class IncrementalDonchian(IncrementalIndicator):
    """
    Donchian Channel with TRUE O(1) updates using monotonic deques.

    Formula:
        upper = max(high over upper_length)
        lower = min(low over lower_length)
        middle = (upper + lower) / 2

    O(1) technique:
        - Monotonic deque for max (decreasing order with index)
        - Monotonic deque for min (increasing order with index)
        - Front of deque is always current max/min

    Matches pandas_ta.donchian() output.
    """

    lower_length: int = 20
    upper_length: int = 20
    _count: int = field(default=0, init=False)
    # Monotonic deque for max highs: (value, index), decreasing by value
    _max_deque: deque = field(default_factory=deque, init=False)
    # Monotonic deque for min lows: (value, index), increasing by value
    _min_deque: deque = field(default_factory=deque, init=False)

    def update(self, high: float, low: float, **kwargs: Any) -> None:
        """Update with new high/low data - amortized O(1) operation."""
        current_idx = self._count
        self._count += 1

        # Remove elements outside upper_length window for max
        upper_start = current_idx - self.upper_length
        while self._max_deque and self._max_deque[0][1] <= upper_start:
            self._max_deque.popleft()

        # Remove elements outside lower_length window for min
        lower_start = current_idx - self.lower_length
        while self._min_deque and self._min_deque[0][1] <= lower_start:
            self._min_deque.popleft()

        # Maintain monotonic decreasing for max (remove smaller from back)
        while self._max_deque and self._max_deque[-1][0] <= high:
            self._max_deque.pop()
        self._max_deque.append((high, current_idx))

        # Maintain monotonic increasing for min (remove larger from back)
        while self._min_deque and self._min_deque[-1][0] >= low:
            self._min_deque.pop()
        self._min_deque.append((low, current_idx))

    def reset(self) -> None:
        self._max_deque.clear()
        self._min_deque.clear()
        self._count = 0

    @property
    def value(self) -> float:
        """Returns middle band (default)."""
        return self.middle_value

    @property
    def upper_value(self) -> float:
        """Returns upper band (highest high) - O(1) via monotonic deque."""
        if not self.is_ready:
            return np.nan
        return self._max_deque[0][0] if self._max_deque else np.nan

    @property
    def lower_value(self) -> float:
        """Returns lower band (lowest low) - O(1) via monotonic deque."""
        if not self.is_ready:
            return np.nan
        return self._min_deque[0][0] if self._min_deque else np.nan

    @property
    def middle_value(self) -> float:
        """Returns middle band."""
        if not self.is_ready:
            return np.nan
        return (self.upper_value + self.lower_value) / 2.0

    @property
    def is_ready(self) -> bool:
        return self._count >= max(self.lower_length, self.upper_length)


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
