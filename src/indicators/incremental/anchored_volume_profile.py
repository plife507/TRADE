"""
Anchored Volume Profile indicator.

Extends IncrementalVolumeProfile by resetting accumulation on structural
events (swing pair version changes). When the swing pair updates, the
volume profile resets and starts accumulating from the new range.

Same algorithm as VolumeProfile but with anchor-based resets, following
the pattern of IncrementalAnchoredVWAP.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .base import IncrementalIndicator
from .volume import IncrementalVolumeProfile


@dataclass
class IncrementalAnchoredVolumeProfile(IncrementalIndicator):
    """
    Anchored Volume Profile — resets on swing pair version change.

    Wraps IncrementalVolumeProfile and monitors swing pair version.
    When the swing pair changes (new high/low range established),
    the profile resets and begins accumulating fresh volume data
    within the new structural range.

    Params:
        num_buckets: Number of price buckets (default: 50)
        lookback: Rolling window in bars (default: 50)
        value_area_pct: Fraction for value area (default: 0.70)

    Additional output:
        bars_since_anchor: Bars since last reset (INT)

    Requires swing structure with pair_version output to be updated
    before this indicator each bar (passed via **kwargs).
    """

    num_buckets: int = 50
    lookback: int = 50
    value_area_pct: float = 0.70

    _vp: IncrementalVolumeProfile = field(init=False)
    _last_pair_version: int = field(default=-1, init=False)
    _bars_since_anchor: int = field(default=0, init=False)
    _count: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self._vp = IncrementalVolumeProfile(
            num_buckets=self.num_buckets,
            lookback=self.lookback,
            value_area_pct=self.value_area_pct,
        )

    def update(
        self, high: float, low: float, close: float, volume: float, **kwargs: Any
    ) -> None:
        """Update anchored volume profile.

        Args:
            high, low, close, volume: Bar OHLCV.
            swing_pair_version: Current swing pair version (int). When it
                changes, the profile resets. Passed via **kwargs by the engine.
        """
        self._count += 1
        self._bars_since_anchor += 1

        # Check for anchor reset
        pair_version = kwargs.get("swing_pair_version")
        if pair_version is not None:
            pv = int(pair_version)
            if pv != self._last_pair_version and self._last_pair_version >= 0:
                self._vp.reset()
                self._bars_since_anchor = 1
            self._last_pair_version = pv

        self._vp.update(high=high, low=low, close=close, volume=volume)

    def reset(self) -> None:
        self._vp.reset()
        self._last_pair_version = -1
        self._bars_since_anchor = 0
        self._count = 0

    @property
    def value(self) -> float:
        """Primary output: POC price level."""
        return self._vp.poc

    @property
    def poc(self) -> float:
        return self._vp.poc

    @property
    def vah(self) -> float:
        return self._vp.vah

    @property
    def val(self) -> float:
        return self._vp.val

    @property
    def poc_volume(self) -> float:
        return self._vp.poc_volume

    @property
    def above_poc(self) -> float:
        return self._vp.above_poc

    @property
    def in_value_area(self) -> float:
        return self._vp.in_value_area

    @property
    def bars_since_anchor(self) -> int:
        return self._bars_since_anchor

    @property
    def is_ready(self) -> bool:
        return self._vp.is_ready
