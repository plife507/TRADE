"""
EMA-composable indicators built on top of IncrementalEMA.

Includes DEMA, TEMA, PPO, TRIX, and TSI -- all indicators that
compose one or more EMA instances internally.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .base import IncrementalIndicator
from .core import IncrementalEMA, IncrementalSMA


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
