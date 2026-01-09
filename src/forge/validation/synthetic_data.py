"""
Synthetic candle data generation for Forge validation.

Generates deterministic, reproducible OHLCV data for validating:
- Structure detection (swing, zone, fibonacci, trend)
- Indicator computation (INDICATOR_REGISTRY parity)
- Multi-timeframe alignment

NO hard coding. All values flow through parameters.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

import numpy as np
import pandas as pd


# =============================================================================
# Constants (named, not magic numbers)
# =============================================================================
DEFAULT_SEED = 42
DEFAULT_BARS_PER_TF = 1000
DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_BASE_PRICE = 50000.0
DEFAULT_VOLATILITY = 0.02  # 2% daily volatility
DEFAULT_TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h"]
HASH_LENGTH = 12  # SHA256 prefix length

# Timeframe to minutes mapping (Bybit intervals only)
# Bybit intervals: 1,3,5,15,30,60,120,240,360,720,D,W,M
TF_TO_MINUTES: dict[str, int] = {
    "1m": 1,
    "3m": 3,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "2h": 120,
    "4h": 240,
    "6h": 360,
    "12h": 720,
    "D": 1440,
    "W": 10080,
    "M": 43200,
}


# =============================================================================
# Pattern Types
# =============================================================================
PatternType = Literal["trending", "ranging", "volatile", "mtf_aligned"]


# =============================================================================
# Result Dataclasses
# =============================================================================
@dataclass
class SyntheticCandles:
    """
    Container for generated synthetic OHLCV data.

    Attributes:
        symbol: Trading symbol (e.g., "BTCUSDT")
        timeframes: Mapping of timeframe -> DataFrame with OHLCV columns
        seed: Random seed used for reproducibility
        pattern: Pattern type used for generation
        bars_per_tf: Number of bars for slowest TF (or all TFs if align_mtf=False)
        bar_counts: Actual bar count per timeframe (differs when align_mtf=True)
        align_mtf: Whether MTF alignment was used
        total_minutes: Total time range covered in minutes
        base_price: Starting price
        volatility: Volatility parameter
        data_hash: SHA256[:12] of the generated data for verification
    """
    symbol: str
    timeframes: dict[str, pd.DataFrame]
    seed: int
    pattern: PatternType
    bars_per_tf: int
    bar_counts: dict[str, int]  # Actual bars per TF
    align_mtf: bool
    total_minutes: int  # Time range covered
    base_price: float
    volatility: float
    data_hash: str

    # Generation metadata
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def get_tf(self, tf: str) -> pd.DataFrame:
        """Get DataFrame for a specific timeframe."""
        if tf not in self.timeframes:
            raise KeyError(f"Timeframe {tf} not in generated data. Available: {list(self.timeframes.keys())}")
        return self.timeframes[tf]

    def to_dict(self) -> dict:
        """Convert to dict for serialization (excludes DataFrames)."""
        return {
            "symbol": self.symbol,
            "timeframes": list(self.timeframes.keys()),
            "seed": self.seed,
            "pattern": self.pattern,
            "bars_per_tf": self.bars_per_tf,
            "bar_counts": self.bar_counts,
            "align_mtf": self.align_mtf,
            "total_minutes": self.total_minutes,
            "base_price": self.base_price,
            "volatility": self.volatility,
            "data_hash": self.data_hash,
            "generated_at": self.generated_at,
        }


# =============================================================================
# Hash Computation
# =============================================================================
def _compute_dataframe_hash(df: pd.DataFrame) -> str:
    """Compute deterministic hash of DataFrame."""
    # Use CSV representation for determinism (sorted columns)
    csv_data = df.to_csv(index=False)
    return hashlib.sha256(csv_data.encode('utf-8')).hexdigest()


def _compute_synthetic_hash(
    symbol: str,
    timeframes: dict[str, pd.DataFrame],
    seed: int,
    pattern: PatternType,
) -> str:
    """
    Compute hash of entire synthetic dataset.

    Hash includes:
    - Symbol
    - Seed
    - Pattern
    - Per-timeframe data hashes
    """
    tf_hashes = {}
    for tf in sorted(timeframes.keys()):
        tf_hashes[tf] = _compute_dataframe_hash(timeframes[tf])

    components = {
        "symbol": symbol,
        "seed": seed,
        "pattern": pattern,
        "tf_hashes": tf_hashes,
    }
    serialized = json.dumps(components, sort_keys=True)
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()[:HASH_LENGTH]


# =============================================================================
# Pattern Generators
# =============================================================================
def _generate_trending_prices(
    rng: np.random.Generator,
    n_bars: int,
    base_price: float,
    volatility: float,
) -> np.ndarray:
    """
    Generate prices with clear directional trend.

    Creates swing highs/lows suitable for structure detection testing.
    """
    # Trend direction: up for first half, down for second half
    trend = np.concatenate([
        np.linspace(0, 1, n_bars // 2),
        np.linspace(1, 0.5, n_bars - n_bars // 2),
    ])

    # Add noise
    noise = rng.normal(0, volatility, n_bars)

    # Combine: base + trend component + noise
    trend_magnitude = base_price * 0.2  # 20% trend move
    prices = base_price + trend * trend_magnitude + noise * base_price

    return prices


def _generate_ranging_prices(
    rng: np.random.Generator,
    n_bars: int,
    base_price: float,
    volatility: float,
) -> np.ndarray:
    """
    Generate prices in sideways consolidation.

    Creates clear support/resistance zones for zone detection testing.
    """
    # Mean-reverting around base price
    prices = np.zeros(n_bars)
    prices[0] = base_price

    mean_reversion_strength = 0.1

    for i in range(1, n_bars):
        # Mean reversion + random walk
        reversion = mean_reversion_strength * (base_price - prices[i-1])
        noise = rng.normal(0, volatility * base_price)
        prices[i] = prices[i-1] + reversion + noise

    return prices


def _generate_volatile_prices(
    rng: np.random.Generator,
    n_bars: int,
    base_price: float,
    volatility: float,
) -> np.ndarray:
    """
    Generate prices with high volatility spikes.

    Creates breakout scenarios for stop placement testing.
    """
    prices = np.zeros(n_bars)
    prices[0] = base_price

    # Higher base volatility
    high_vol = volatility * 2

    # Add occasional spikes
    spike_probability = 0.05
    spike_magnitude = 5.0

    for i in range(1, n_bars):
        # Check for spike
        if rng.random() < spike_probability:
            direction = 1 if rng.random() > 0.5 else -1
            change = direction * spike_magnitude * high_vol * base_price
        else:
            change = rng.normal(0, high_vol * base_price)

        prices[i] = prices[i-1] + change

    return prices


def _generate_mtf_aligned_prices(
    rng: np.random.Generator,
    n_bars: int,
    base_price: float,
    volatility: float,
) -> np.ndarray:
    """
    Generate prices with clear multi-timeframe structure.

    Creates aligned HTF/MTF/LTF structure for correlation testing.
    """
    # Create HTF structure (large waves)
    htf_period = n_bars // 4
    htf_wave = np.sin(np.linspace(0, 4 * np.pi, n_bars)) * base_price * 0.15

    # Add MTF structure (medium waves)
    mtf_period = n_bars // 16
    mtf_wave = np.sin(np.linspace(0, 16 * np.pi, n_bars)) * base_price * 0.05

    # Add LTF noise
    ltf_noise = rng.normal(0, volatility * base_price, n_bars)

    # Combine
    prices = base_price + htf_wave + mtf_wave + ltf_noise

    return prices


# =============================================================================
# OHLCV Generation from Close Prices
# =============================================================================
def _prices_to_ohlcv(
    rng: np.random.Generator,
    close_prices: np.ndarray,
    base_timestamp: datetime,
    tf_minutes: int,
    correlate_volume: bool = True,
) -> pd.DataFrame:
    """
    Convert close prices to OHLCV DataFrame.

    Generates realistic high/low/open from close prices.
    Volume can optionally correlate with price volatility.

    Args:
        rng: Random number generator
        close_prices: Array of close prices
        base_timestamp: Starting timestamp
        tf_minutes: Timeframe in minutes
        correlate_volume: If True, larger price moves get higher volume
    """
    n_bars = len(close_prices)

    # Generate OHLC
    opens = np.zeros(n_bars)
    highs = np.zeros(n_bars)
    lows = np.zeros(n_bars)
    volumes = np.zeros(n_bars)
    timestamps = []

    opens[0] = close_prices[0]

    for i in range(n_bars):
        close = close_prices[i]

        if i > 0:
            # Open is typically near previous close
            opens[i] = close_prices[i-1] * (1 + rng.normal(0, 0.001))

        # High is max of open/close plus some wick
        base_high = max(opens[i], close)
        highs[i] = base_high * (1 + abs(rng.normal(0, 0.005)))

        # Low is min of open/close minus some wick
        base_low = min(opens[i], close)
        lows[i] = base_low * (1 - abs(rng.normal(0, 0.005)))

        # Volume generation
        if correlate_volume and i > 0:
            # Higher volume on bigger price moves
            price_change = abs(close - close_prices[i-1]) / close_prices[i-1]
            # 1% move → ~1.5x volume, 2% move → ~2x volume
            vol_multiplier = 1 + (price_change * 50)
            base_vol = rng.lognormal(mean=10, sigma=0.8) * 1000
            volumes[i] = base_vol * vol_multiplier
        else:
            # Random uncorrelated volume
            volumes[i] = rng.lognormal(mean=10, sigma=1) * 1000

        # Timestamp
        timestamps.append(base_timestamp + timedelta(minutes=tf_minutes * i))

    # Create DataFrame with standard column names
    df = pd.DataFrame({
        "timestamp": timestamps,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": close_prices,
        "volume": volumes,
    })

    return df


# =============================================================================
# Warmup Calculation from Play
# =============================================================================
def calculate_warmup_for_play(play_id: str) -> dict[str, int]:
    """
    Calculate warmup bars needed per timeframe for a Play.

    Loads the Play, builds a feature registry, and computes the max warmup
    for each timeframe based on declared indicators and structures.

    Args:
        play_id: Play identifier (e.g., "V_100_blocks_basic")

    Returns:
        Dict mapping timeframe -> warmup bars needed

    Example:
        >>> warmup = calculate_warmup_for_play("V_100_blocks_basic")
        >>> print(warmup)  # {"15m": 60}
    """
    from src.backtest import load_play
    from src.backtest.feature_registry import FeatureRegistry

    # Load the play
    play = load_play(play_id)

    # Build feature registry from play's existing features
    # The Play already has a features tuple of Feature objects
    registry = FeatureRegistry(execution_tf=play.execution_tf)

    # Register features from the play (already Feature objects)
    for feature in play.features:
        registry.add(feature)

    # Calculate warmup per TF
    warmup_by_tf: dict[str, int] = {}
    for tf in registry.get_all_tfs():
        warmup_by_tf[tf] = registry.get_warmup_for_tf(tf)

    return warmup_by_tf


def generate_synthetic_for_play(
    play_id: str,
    extra_bars: int = 500,
    seed: int = DEFAULT_SEED,
    pattern: PatternType = "trending",
    base_price: float = DEFAULT_BASE_PRICE,
    volatility: float = DEFAULT_VOLATILITY,
    base_timestamp: datetime | None = None,
    correlate_volume: bool = True,
) -> SyntheticCandles:
    """
    Generate synthetic data sized for a specific Play's warmup requirements.

    Calculates the warmup needed for each timeframe based on the Play's
    features and structures, then generates enough data for warmup + extra_bars.

    Args:
        play_id: Play identifier (e.g., "V_100_blocks_basic")
        extra_bars: Additional bars beyond warmup for testing (default: 500)
        seed: Random seed for reproducibility
        pattern: Price pattern type
        base_price: Starting price
        volatility: Daily volatility
        base_timestamp: Starting timestamp
        correlate_volume: If True, volume correlates with price moves

    Returns:
        SyntheticCandles with enough data for the Play's warmup + extra_bars

    Example:
        >>> candles = generate_synthetic_for_play(
        ...     play_id="V_100_blocks_basic",
        ...     extra_bars=500,
        ... )
        >>> print(f"exec bars: {len(candles.get_tf(candles.timeframes.keys()[0]))}")
    """
    from src.backtest import load_play

    # Load play to get timeframes
    play = load_play(play_id)

    # Collect all TFs used by the play from features
    timeframes = set()
    timeframes.add(play.execution_tf)  # exec TF

    # Add TFs from features (Feature objects have a .tf attribute)
    for feature in play.features:
        if feature.tf:
            timeframes.add(feature.tf)

    timeframes_list = sorted(timeframes, key=lambda tf: TF_TO_MINUTES.get(tf, 0))

    # Get warmup requirements
    warmup_by_tf = calculate_warmup_for_play(play_id)

    # Find slowest TF for alignment
    slowest_tf = max(timeframes_list, key=lambda tf: TF_TO_MINUTES[tf])

    # Calculate bars needed for slowest TF
    slowest_warmup = warmup_by_tf.get(slowest_tf, 50)
    slowest_bars = slowest_warmup + extra_bars

    # Get symbol from play (first in symbol_universe or default)
    symbol = play.symbol_universe[0] if play.symbol_universe else DEFAULT_SYMBOL

    # Generate with MTF alignment
    return generate_synthetic_candles(
        symbol=symbol,
        timeframes=timeframes_list,
        bars_per_tf=slowest_bars,
        seed=seed,
        pattern=pattern,
        base_price=base_price,
        volatility=volatility,
        base_timestamp=base_timestamp,
        correlate_volume=correlate_volume,
        align_mtf=True,
    )


# =============================================================================
# Main Generation Function
# =============================================================================
def generate_synthetic_candles(
    symbol: str = DEFAULT_SYMBOL,
    timeframes: list[str] | None = None,
    bars_per_tf: int = DEFAULT_BARS_PER_TF,
    seed: int = DEFAULT_SEED,
    pattern: PatternType = "trending",
    base_price: float = DEFAULT_BASE_PRICE,
    volatility: float = DEFAULT_VOLATILITY,
    base_timestamp: datetime | None = None,
    correlate_volume: bool = True,
    align_mtf: bool = True,
) -> SyntheticCandles:
    """
    Generate synthetic OHLCV data for all timeframes.

    Args:
        symbol: Trading symbol (default: "BTCUSDT")
        timeframes: List of timeframes to generate (default: ["1m", "5m", "15m", "1h", "4h"])
        bars_per_tf: Number of bars for slowest TF (default: 1000). When align_mtf=True,
            faster TFs get proportionally more bars to cover the same time range.
        seed: Random seed for reproducibility (default: 42)
        pattern: Price pattern type:
            - "trending": Clear directional move (swing highs/lows)
            - "ranging": Sideways consolidation (zone detection)
            - "volatile": High volatility spikes (breakout detection)
            - "mtf_aligned": Multi-TF alignment (HTF/MTF/LTF correlation)
        base_price: Starting price (default: 50000.0)
        volatility: Daily volatility (default: 0.02 = 2%)
        base_timestamp: Starting timestamp (default: 2025-01-01 00:00 UTC)
        correlate_volume: If True (default), volume correlates with price moves.
            Larger price changes produce higher volume for realistic testing
            of volume-based indicators and structures.
        align_mtf: If True (default), all timeframes cover the same time range.
            Slowest TF gets bars_per_tf bars, faster TFs get proportionally more.
            Example: bars_per_tf=100, timeframes=["1m","1h"] -> 1h=100 bars, 1m=6000 bars.
            If False, all TFs get exactly bars_per_tf bars (misaligned time ranges).

    Returns:
        SyntheticCandles with OHLCV DataFrames for each timeframe

    Example:
        >>> # MTF-aligned: 1h gets 100 bars, 1m gets 6000 bars (same time range)
        >>> candles = generate_synthetic_candles(
        ...     timeframes=["1m", "1h"],
        ...     bars_per_tf=100,
        ...     align_mtf=True,
        ... )
        >>> print(candles.bar_counts)  # {"1m": 6000, "1h": 100}
        >>> print(candles.total_minutes)  # 6000
    """
    # Apply defaults
    if timeframes is None:
        timeframes = DEFAULT_TIMEFRAMES.copy()
    if base_timestamp is None:
        base_timestamp = datetime(2025, 1, 1, 0, 0, 0)

    # Validate timeframes
    for tf in timeframes:
        if tf not in TF_TO_MINUTES:
            raise ValueError(f"Unknown timeframe: {tf}. Valid: {list(TF_TO_MINUTES.keys())}")

    # Create RNG with seed for reproducibility
    rng = np.random.default_rng(seed)

    # Select pattern generator
    pattern_generators = {
        "trending": _generate_trending_prices,
        "ranging": _generate_ranging_prices,
        "volatile": _generate_volatile_prices,
        "mtf_aligned": _generate_mtf_aligned_prices,
    }

    if pattern not in pattern_generators:
        raise ValueError(f"Unknown pattern: {pattern}. Valid: {list(pattern_generators.keys())}")

    generator = pattern_generators[pattern]

    # Calculate bar counts per timeframe
    bar_counts: dict[str, int] = {}

    if align_mtf:
        # Find slowest TF (most minutes per bar)
        slowest_tf = max(timeframes, key=lambda tf: TF_TO_MINUTES[tf])
        slowest_minutes = TF_TO_MINUTES[slowest_tf]

        # Total time range = slowest TF bars * slowest TF minutes
        total_minutes = bars_per_tf * slowest_minutes

        # Calculate bars for each TF to cover same time range
        for tf in timeframes:
            tf_minutes = TF_TO_MINUTES[tf]
            bar_counts[tf] = total_minutes // tf_minutes
    else:
        # All TFs get same bar count (misaligned time ranges)
        total_minutes = bars_per_tf * min(TF_TO_MINUTES[tf] for tf in timeframes)
        for tf in timeframes:
            bar_counts[tf] = bars_per_tf

    # Generate data for each timeframe
    tf_dataframes: dict[str, pd.DataFrame] = {}

    for tf in timeframes:
        tf_minutes = TF_TO_MINUTES[tf]
        n_bars = bar_counts[tf]

        # Adjust volatility for timeframe (longer TF = higher vol per bar)
        tf_volatility = volatility * np.sqrt(tf_minutes / 1440)  # Annualized to daily

        # Generate close prices using pattern
        close_prices = generator(
            rng=rng,
            n_bars=n_bars,
            base_price=base_price,
            volatility=tf_volatility,
        )

        # Convert to OHLCV
        df = _prices_to_ohlcv(
            rng=rng,
            close_prices=close_prices,
            base_timestamp=base_timestamp,
            tf_minutes=tf_minutes,
            correlate_volume=correlate_volume,
        )

        tf_dataframes[tf] = df

    # Compute hash
    data_hash = _compute_synthetic_hash(
        symbol=symbol,
        timeframes=tf_dataframes,
        seed=seed,
        pattern=pattern,
    )

    return SyntheticCandles(
        symbol=symbol,
        timeframes=tf_dataframes,
        seed=seed,
        pattern=pattern,
        bars_per_tf=bars_per_tf,
        bar_counts=bar_counts,
        align_mtf=align_mtf,
        total_minutes=total_minutes,
        base_price=base_price,
        volatility=volatility,
        data_hash=data_hash,
    )


def verify_synthetic_hash(candles: SyntheticCandles) -> bool:
    """
    Verify that synthetic data hash matches recomputed hash.

    Used for integrity verification after serialization/deserialization.
    """
    recomputed = _compute_synthetic_hash(
        symbol=candles.symbol,
        timeframes=candles.timeframes,
        seed=candles.seed,
        pattern=candles.pattern,
    )
    return recomputed == candles.data_hash
