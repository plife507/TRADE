"""
Stateful multi-output indicators with complex internal state machines.

Includes PSAR, Squeeze, and Fisher -- indicators that track directional
state, reversals, or squeeze conditions.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .base import IncrementalIndicator
from .core import IncrementalBBands, IncrementalSMA
from .lookback import IncrementalKC
from .trivial import IncrementalMOM


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
