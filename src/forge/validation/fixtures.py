"""
Validation Fixtures - Synthetic data generators for testing.

Provides deterministic, predictable data patterns for validating:
- DSL operators (comparison, crossover, window)
- Structure detection (swing, fib, zone, trend)
- Integration tests (full signal generation)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


# =============================================================================
# Core Data Structures
# =============================================================================

@dataclass
class SyntheticBar:
    """Single OHLCV bar."""
    timestamp: pd.Timestamp
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class SyntheticData:
    """Collection of OHLCV bars as pandas DataFrame."""
    df: pd.DataFrame

    @property
    def open(self) -> pd.Series:
        return self.df["open"]

    @property
    def high(self) -> pd.Series:
        return self.df["high"]

    @property
    def low(self) -> pd.Series:
        return self.df["low"]

    @property
    def close(self) -> pd.Series:
        return self.df["close"]

    @property
    def volume(self) -> pd.Series:
        return self.df["volume"]

    def __len__(self) -> int:
        return len(self.df)


# =============================================================================
# Basic Generators
# =============================================================================

def generate_constant(
    value: float,
    n_bars: int = 100,
    seed: int = 42,
) -> SyntheticData:
    """
    Generate constant price data (flat line).

    Useful for testing threshold comparisons.
    """
    np.random.seed(seed)
    dates = pd.date_range("2024-01-01", periods=n_bars, freq="1min")

    # Small random variation around constant
    noise = np.random.randn(n_bars) * 0.01
    close = value + noise
    high = close + np.abs(np.random.randn(n_bars) * 0.1)
    low = close - np.abs(np.random.randn(n_bars) * 0.1)
    open_ = close + np.random.randn(n_bars) * 0.05
    volume = np.random.randint(1000, 10000, n_bars).astype(float)

    df = pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }, index=dates)

    return SyntheticData(df=df)


def generate_linear_trend(
    start: float,
    end: float,
    n_bars: int = 100,
    seed: int = 42,
) -> SyntheticData:
    """
    Generate linear trending data from start to end.

    Useful for testing crossover operators.
    """
    np.random.seed(seed)
    dates = pd.date_range("2024-01-01", periods=n_bars, freq="1min")

    # Linear interpolation with noise
    trend = np.linspace(start, end, n_bars)
    noise = np.random.randn(n_bars) * abs(end - start) * 0.02
    close = trend + noise

    high = close + np.abs(np.random.randn(n_bars) * 0.5)
    low = close - np.abs(np.random.randn(n_bars) * 0.5)
    open_ = np.roll(close, 1)
    open_[0] = start
    volume = np.random.randint(1000, 10000, n_bars).astype(float)

    df = pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }, index=dates)

    return SyntheticData(df=df)


# =============================================================================
# Pattern Generators
# =============================================================================

def generate_trending_up(
    start: float = 100.0,
    end: float = 120.0,
    n_bars: int = 200,
    pullbacks: int = 3,
    seed: int = 42,
) -> SyntheticData:
    """
    Generate uptrend with pullbacks.

    Creates clear higher highs and higher lows with
    2-3 pullbacks for crossover testing.
    """
    np.random.seed(seed)
    dates = pd.date_range("2024-01-01", periods=n_bars, freq="1min")

    # Base trend
    trend = np.linspace(start, end, n_bars)

    # Add pullbacks (sine wave modulation)
    pullback_amplitude = (end - start) * 0.15
    pullback_freq = pullbacks * 2 * np.pi / n_bars
    pullback = pullback_amplitude * np.sin(np.arange(n_bars) * pullback_freq)

    # Combine with noise
    noise = np.random.randn(n_bars) * (end - start) * 0.01
    close = trend + pullback + noise

    high = close + np.abs(np.random.randn(n_bars) * 0.3)
    low = close - np.abs(np.random.randn(n_bars) * 0.3)
    open_ = np.roll(close, 1)
    open_[0] = start
    volume = np.random.randint(1000, 10000, n_bars).astype(float)

    df = pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }, index=dates)

    return SyntheticData(df=df)


def generate_trending_down(
    start: float = 120.0,
    end: float = 100.0,
    n_bars: int = 200,
    pullbacks: int = 3,
    seed: int = 42,
) -> SyntheticData:
    """
    Generate downtrend with pullbacks.

    Creates clear lower highs and lower lows.
    """
    return generate_trending_up(
        start=start,
        end=end,
        n_bars=n_bars,
        pullbacks=pullbacks,
        seed=seed,
    )


def generate_ranging(
    center: float = 100.0,
    amplitude: float = 5.0,
    n_bars: int = 200,
    cycles: int = 4,
    seed: int = 42,
) -> SyntheticData:
    """
    Generate ranging/sideways market.

    Oscillates between support and resistance levels.
    """
    np.random.seed(seed)
    dates = pd.date_range("2024-01-01", periods=n_bars, freq="1min")

    # Sine wave oscillation
    freq = cycles * 2 * np.pi / n_bars
    oscillation = amplitude * np.sin(np.arange(n_bars) * freq)

    # Add noise
    noise = np.random.randn(n_bars) * amplitude * 0.1
    close = center + oscillation + noise

    high = close + np.abs(np.random.randn(n_bars) * 0.3)
    low = close - np.abs(np.random.randn(n_bars) * 0.3)
    open_ = np.roll(close, 1)
    open_[0] = center
    volume = np.random.randint(1000, 10000, n_bars).astype(float)

    df = pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }, index=dates)

    return SyntheticData(df=df)


def generate_swing_pattern(
    n_bars: int = 50,
    left: int = 5,
    right: int = 5,
    seed: int = 42,
) -> SyntheticData:
    """
    Generate data with clear swing high and low.

    Creates a V-shape or inverted-V for swing detection testing.
    """
    np.random.seed(seed)
    dates = pd.date_range("2024-01-01", periods=n_bars, freq="1min")

    # Create V-shape: down then up
    mid = n_bars // 2
    down = np.linspace(110, 90, mid)
    up = np.linspace(90, 110, n_bars - mid)
    close = np.concatenate([down, up])

    # Add small noise
    noise = np.random.randn(n_bars) * 0.5
    close = close + noise

    high = close + np.abs(np.random.randn(n_bars) * 0.3)
    low = close - np.abs(np.random.randn(n_bars) * 0.3)
    open_ = np.roll(close, 1)
    open_[0] = 110
    volume = np.random.randint(1000, 10000, n_bars).astype(float)

    df = pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }, index=dates)

    return SyntheticData(df=df)


def generate_volume_spikes(
    n_bars: int = 100,
    spike_indices: list[int] | None = None,
    spike_multiplier: float = 5.0,
    base_volume: float = 1000.0,
    seed: int = 42,
) -> SyntheticData:
    """
    Generate data with volume spikes at specific indices.

    Useful for testing volume-based conditions.
    """
    np.random.seed(seed)
    dates = pd.date_range("2024-01-01", periods=n_bars, freq="1min")

    # Default spike positions
    if spike_indices is None:
        spike_indices = [20, 50, 80]

    # Base price (slight uptrend)
    close = np.linspace(100, 105, n_bars) + np.random.randn(n_bars) * 0.5

    # Volume with spikes
    volume = np.random.uniform(base_volume * 0.8, base_volume * 1.2, n_bars)
    for idx in spike_indices:
        if 0 <= idx < n_bars:
            volume[idx] = base_volume * spike_multiplier

    high = close + np.abs(np.random.randn(n_bars) * 0.3)
    low = close - np.abs(np.random.randn(n_bars) * 0.3)
    open_ = np.roll(close, 1)
    open_[0] = 100

    df = pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }, index=dates)

    return SyntheticData(df=df)


# =============================================================================
# Specialized Generators for Testing
# =============================================================================

def generate_rsi_oversold(
    n_bars: int = 100,
    oversold_start: int = 30,
    oversold_end: int = 50,
    seed: int = 42,
) -> SyntheticData:
    """
    Generate data that produces RSI < 30 in a specific window.

    Creates a sharp drop followed by recovery.
    """
    np.random.seed(seed)
    dates = pd.date_range("2024-01-01", periods=n_bars, freq="1min")

    # Normal market
    close = np.ones(n_bars) * 100

    # Sharp drop (causes RSI to plunge)
    for i in range(oversold_start, min(oversold_end, n_bars)):
        close[i] = close[i - 1] * 0.98  # 2% drop per bar

    # Recovery
    for i in range(oversold_end, n_bars):
        close[i] = close[i - 1] * 1.01  # 1% rise per bar

    # Add small noise
    noise = np.random.randn(n_bars) * 0.1
    close = close + noise

    high = close + np.abs(np.random.randn(n_bars) * 0.2)
    low = close - np.abs(np.random.randn(n_bars) * 0.2)
    open_ = np.roll(close, 1)
    open_[0] = 100
    volume = np.random.randint(1000, 10000, n_bars).astype(float)

    df = pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }, index=dates)

    return SyntheticData(df=df)


def generate_crossover_setup(
    n_bars: int = 100,
    cross_index: int = 50,
    fast_length: int = 9,
    slow_length: int = 21,
    seed: int = 42,
) -> SyntheticData:
    """
    Generate data that produces an EMA crossover at a specific index.

    Creates a trend that causes fast EMA to cross slow EMA.
    """
    np.random.seed(seed)
    dates = pd.date_range("2024-01-01", periods=n_bars, freq="1min")

    # Start flat, then trend up to cause crossover
    warmup = max(fast_length, slow_length) * 3
    flat_end = cross_index - 10

    close = np.zeros(n_bars)

    # Flat/slightly down (fast below slow)
    close[:flat_end] = 100 - np.linspace(0, 2, flat_end)

    # Sharp uptrend (causes crossover)
    close[flat_end:cross_index + 10] = np.linspace(98, 110, cross_index + 10 - flat_end)

    # Continue up
    close[cross_index + 10:] = np.linspace(110, 115, n_bars - cross_index - 10)

    # Add small noise
    noise = np.random.randn(n_bars) * 0.3
    close = close + noise

    high = close + np.abs(np.random.randn(n_bars) * 0.2)
    low = close - np.abs(np.random.randn(n_bars) * 0.2)
    open_ = np.roll(close, 1)
    open_[0] = 100
    volume = np.random.randint(1000, 10000, n_bars).astype(float)

    df = pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }, index=dates)

    return SyntheticData(df=df)


# =============================================================================
# Mock Snapshot for Operator Testing
# =============================================================================

class MockSnapshot:
    """
    Mock snapshot for testing DSL operators without full engine.

    Provides get_indicator_value() and get_feature_value() methods
    that return pre-configured values.
    """

    def __init__(self, values: dict[str, Any] | None = None):
        """
        Initialize mock snapshot with values.

        Args:
            values: Dict mapping feature_id to value or list of values
                   (for offset support). If list, index 0 is current,
                   index 1 is prev (offset=1), etc.
        """
        self._values = values or {}
        self._prev_last_price: float | None = None
        self.last_price: float = 0.0

    def set_value(self, key: str, value: Any, offset: int = 0) -> None:
        """Set a value at a specific offset."""
        if key not in self._values:
            self._values[key] = {}
        if isinstance(self._values[key], dict):
            self._values[key][offset] = value
        else:
            # Convert to dict format
            current = self._values[key]
            self._values[key] = {0: current, offset: value}

    def get_indicator_value(self, indicator_key: str, offset: int = 0) -> float:
        """Get indicator value, supporting offset for crossover operators."""
        if indicator_key == "last_price":
            if offset == 0:
                return self.last_price
            elif offset == 1:
                if self._prev_last_price is None:
                    raise ValueError("last_price offset=1 requires prev_last_price")
                return self._prev_last_price

        if indicator_key not in self._values:
            raise KeyError(f"Unknown indicator: {indicator_key}")

        val = self._values[indicator_key]
        if isinstance(val, dict):
            if offset in val:
                return val[offset]
            return val.get(0, 0.0)
        elif isinstance(val, list):
            if offset < len(val):
                return val[offset]
            return val[0]
        else:
            return val

    def get_feature_value(
        self,
        feature_id: str,
        field: str = "value",
        offset: int = 0,
    ) -> Any:
        """Get feature value (indicator or structure)."""
        key = f"{feature_id}.{field}" if field != "value" else feature_id
        return self.get_indicator_value(key, offset)
