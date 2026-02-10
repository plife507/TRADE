"""
Synthetic and real OHLCV data generators for structure parity audits.

Provides various data generators that exercise different market regimes:
- Trending (up/down)
- Ranging / choppy
- High volatility / gaps
- Flat / zero ATR
- Monotonic moves
- Rapid alternating swings
"""

import numpy as np
import pandas as pd


def generate_synthetic_ohlcv(bars: int = 2000, seed: int = 42) -> pd.DataFrame:
    """
    Generate synthetic OHLCV data with trending + ranging + volatile regimes.

    Creates realistic price action by combining:
    - Random walk for base close prices
    - Regime changes (trend/range/volatile)
    - Proper OHLC relationships

    Args:
        bars: Number of bars to generate.
        seed: Random seed for reproducibility.

    Returns:
        DataFrame with columns: open, high, low, close, volume
    """
    rng = np.random.RandomState(seed)

    # Start price
    price = 50000.0
    opens = np.empty(bars)
    highs = np.empty(bars)
    lows = np.empty(bars)
    closes = np.empty(bars)
    volumes = np.empty(bars)

    for i in range(bars):
        # Regime: trending up, trending down, or ranging
        regime_phase = (i // 200) % 5
        if regime_phase in (0, 1):
            # Uptrend
            drift = 0.001
            vol = 0.015
        elif regime_phase in (2,):
            # Ranging
            drift = 0.0
            vol = 0.012
        elif regime_phase in (3, 4):
            # Downtrend
            drift = -0.001
            vol = 0.018
        else:
            drift = 0.0
            vol = 0.015

        ret = drift + rng.randn() * vol
        new_close = price * (1 + ret)

        bar_vol = abs(rng.randn()) * vol + 0.003
        bar_high = max(price, new_close) * (1 + rng.uniform(0, bar_vol))
        bar_low = min(price, new_close) * (1 - rng.uniform(0, bar_vol))

        opens[i] = price
        highs[i] = bar_high
        lows[i] = bar_low
        closes[i] = new_close
        volumes[i] = abs(rng.randn()) * 1_000_000 + 500_000

        price = new_close

    return pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })


def generate_flat_bars(bars: int = 500, price: float = 50000.0) -> pd.DataFrame:
    """
    Generate flat bars where ATR = 0 (all OHLC are identical).

    Tests edge case where no pivots should form.

    Args:
        bars: Number of bars.
        price: Constant price.

    Returns:
        DataFrame with identical OHLCV values.
    """
    return pd.DataFrame({
        "open": np.full(bars, price),
        "high": np.full(bars, price),
        "low": np.full(bars, price),
        "close": np.full(bars, price),
        "volume": np.full(bars, 1_000_000.0),
    })


def generate_gap_data(bars: int = 1000, seed: int = 99) -> pd.DataFrame:
    """
    Generate data with large overnight-style gaps.

    Every 50 bars, price jumps 5-10% to simulate gap opens.

    Args:
        bars: Number of bars.
        seed: Random seed.

    Returns:
        DataFrame with gap events.
    """
    rng = np.random.RandomState(seed)
    price = 50000.0
    opens = np.empty(bars)
    highs = np.empty(bars)
    lows = np.empty(bars)
    closes = np.empty(bars)
    volumes = np.empty(bars)

    for i in range(bars):
        # Gap every 50 bars
        if i > 0 and i % 50 == 0:
            gap = rng.choice([-1, 1]) * rng.uniform(0.05, 0.10)
            price *= (1 + gap)

        ret = rng.randn() * 0.01
        new_close = price * (1 + ret)
        bar_vol = 0.005
        bar_high = max(price, new_close) * (1 + rng.uniform(0, bar_vol))
        bar_low = min(price, new_close) * (1 - rng.uniform(0, bar_vol))

        opens[i] = price
        highs[i] = bar_high
        lows[i] = bar_low
        closes[i] = new_close
        volumes[i] = abs(rng.randn()) * 1_000_000 + 500_000
        price = new_close

    return pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })


def generate_rapid_swing_data(bars: int = 1000, seed: int = 77) -> pd.DataFrame:
    """
    Generate fast alternating swings to stress pivot detection.

    Price oscillates with period ~10 bars and amplitude ~3%.

    Args:
        bars: Number of bars.
        seed: Random seed.

    Returns:
        DataFrame with rapid oscillations.
    """
    rng = np.random.RandomState(seed)
    base = 50000.0
    t = np.arange(bars, dtype=float)

    # Oscillating base with noise
    cycle = np.sin(2 * np.pi * t / 10) * 0.03 * base
    noise = rng.randn(bars) * 0.005 * base
    closes = base + cycle + noise

    opens = np.roll(closes, 1)
    opens[0] = closes[0]

    spread = np.abs(rng.randn(bars)) * 0.003 * base + 0.001 * base
    highs = np.maximum(opens, closes) + spread
    lows = np.minimum(opens, closes) - spread
    volumes = np.abs(rng.randn(bars)) * 1_000_000 + 500_000

    return pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })


def generate_monotonic_rise(bars: int = 500, seed: int = 11) -> pd.DataFrame:
    """
    Generate monotonically rising price (each bar higher than previous).

    Tests edge case where no swing lows form.

    Args:
        bars: Number of bars.
        seed: Random seed.

    Returns:
        DataFrame with monotonic uptrend.
    """
    rng = np.random.RandomState(seed)
    closes = 50000.0 * np.exp(np.cumsum(np.abs(rng.randn(bars)) * 0.002 + 0.001))
    opens = np.roll(closes, 1)
    opens[0] = closes[0] * 0.999
    highs = closes * (1 + np.abs(rng.randn(bars)) * 0.001)
    lows = opens * (1 - np.abs(rng.randn(bars)) * 0.0005)
    # Ensure OHLC relationships
    highs = np.maximum(highs, np.maximum(opens, closes))
    lows = np.minimum(lows, np.minimum(opens, closes))
    volumes = np.abs(rng.randn(bars)) * 1_000_000 + 500_000

    return pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })


def generate_monotonic_fall(bars: int = 500, seed: int = 22) -> pd.DataFrame:
    """
    Generate monotonically falling price (each bar lower than previous).

    Tests edge case where no swing highs form.

    Args:
        bars: Number of bars.
        seed: Random seed.

    Returns:
        DataFrame with monotonic downtrend.
    """
    rng = np.random.RandomState(seed)
    closes = 50000.0 * np.exp(np.cumsum(-np.abs(rng.randn(bars)) * 0.002 - 0.001))
    opens = np.roll(closes, 1)
    opens[0] = closes[0] * 1.001
    highs = opens * (1 + np.abs(rng.randn(bars)) * 0.0005)
    lows = closes * (1 - np.abs(rng.randn(bars)) * 0.001)
    # Ensure OHLC relationships
    highs = np.maximum(highs, np.maximum(opens, closes))
    lows = np.minimum(lows, np.minimum(opens, closes))
    volumes = np.abs(rng.randn(bars)) * 1_000_000 + 500_000

    return pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })


def load_real_ohlcv(
    symbol: str = "BTCUSDT",
    timeframe: str = "1h",
    bars: int = 2000,
) -> pd.DataFrame | None:
    """
    Load real OHLCV data from DuckDB for parity testing.

    Falls back to None if data unavailable (allows graceful degradation).

    Args:
        symbol: Trading pair symbol.
        timeframe: Candle timeframe (e.g., "1h", "4h", "D").
        bars: Maximum number of bars to load.

    Returns:
        DataFrame with columns: open, high, low, close, volume.
        None if data is not available.
    """
    try:
        from src.data.data_builder import DataBuilder

        db = DataBuilder()
        df = db.load_candles(symbol=symbol, interval=timeframe, limit=bars)

        if df is None or len(df) < 50:
            return None

        # Normalize column names to lowercase
        col_map = {}
        for col in df.columns:
            lower = col.lower()
            if lower in ("open", "high", "low", "close", "volume"):
                col_map[col] = lower
        df = df.rename(columns=col_map)

        # Ensure required columns exist
        required = {"open", "high", "low", "close", "volume"}
        if not required.issubset(set(df.columns)):
            return None

        # Return only the columns we need, reset index
        result = df[["open", "high", "low", "close", "volume"]].copy()
        result = result.astype(float)
        result = result.reset_index(drop=True)

        return result

    except Exception:
        return None
