"""
Synthetic candle data generation for Forge validation.

Generates deterministic, reproducible OHLCV data for validating:
- Structure detection (swing, zone, fibonacci, trend)
- Indicator computation (INDICATOR_REGISTRY parity)
- Multi-timeframe alignment

NO hard coding. All values flow through parameters.

This is the CANONICAL source for all synthetic data generation in TRADE.
All audit and validation code should import from this module.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal
from types import MappingProxyType

import numpy as np
import pandas as pd

# Lazy imports to avoid circular dependencies
# QuoteState and BarData are imported in functions that need them


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
# Pattern Types - Comprehensive Market Conditions
# =============================================================================
# Legacy patterns (backwards compatible)
PatternType = Literal[
    # Legacy (keep for backwards compatibility)
    "trending", "ranging", "volatile", "multi_tf_aligned",
    # Trend patterns
    "trend_up_clean", "trend_down_clean", "trend_grinding",
    "trend_parabolic", "trend_exhaustion", "trend_stairs",
    # Range patterns
    "range_tight", "range_wide", "range_ascending", "range_descending",
    # Reversal patterns
    "reversal_v_bottom", "reversal_v_top", "reversal_double_bottom", "reversal_double_top",
    # Breakout patterns
    "breakout_clean", "breakout_false", "breakout_retest",
    # Volatility patterns
    "vol_squeeze_expand", "vol_spike_recover", "vol_spike_continue", "vol_decay",
    # Liquidity/manipulation patterns
    "liquidity_hunt_lows", "liquidity_hunt_highs", "choppy_whipsaw",
    "accumulation", "distribution",
    # Multi-timeframe patterns
    "mtf_aligned_bull", "mtf_aligned_bear", "mtf_pullback_bull", "mtf_pullback_bear",
]


# =============================================================================
# Pattern Configuration
# =============================================================================
@dataclass
class PatternConfig:
    """Configuration for pattern generation."""
    # Trend parameters
    trend_magnitude: float = 0.20       # 20% price move for trends
    pullback_depth: float = 0.30        # 30% retracement on pullbacks
    stairs_steps: int = 4               # Number of steps in stair pattern

    # Volatility parameters
    volatility_base: float = 0.02       # 2% daily volatility
    volatility_spike: float = 0.10      # 10% for spike events
    volatility_squeeze: float = 0.005   # 0.5% for squeeze periods

    # Range parameters
    range_width: float = 0.08           # 8% range width
    triangle_slope: float = 0.001       # Slope for ascending/descending triangles

    # Timing (as fractions of total bars)
    trend_fraction: float = 0.6         # 60% of bars in trend phase
    range_fraction: float = 0.3         # 30% of bars in range phase
    spike_fraction: float = 0.1         # 10% of bars in spike phase

    # Noise
    noise_level: float = 0.3            # 0-1 scale for random noise overlay

    # Liquidity hunt parameters
    hunt_depth: float = 0.02            # 2% below/above level for hunt
    hunt_recovery: float = 0.8          # 80% recovery after hunt


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
        bars_per_tf: Number of bars for slowest TF (or all TFs if align_multi_tf=False)
        bar_counts: Actual bar count per timeframe (differs when align_multi_tf=True)
        align_multi_tf: Whether multi-TF alignment was used
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
    align_multi_tf: bool
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
            "align_multi_tf": self.align_multi_tf,
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


def _generate_multi_tf_aligned_prices(
    rng: np.random.Generator,
    n_bars: int,
    base_price: float,
    volatility: float,
) -> np.ndarray:
    """
    Generate prices with clear multi-timeframe structure.

    Creates aligned high_tf/med_tf/low_tf structure for correlation testing.
    """
    # Create high_tf structure (large waves)
    high_tf_period = n_bars // 4
    high_tf_wave = np.sin(np.linspace(0, 4 * np.pi, n_bars)) * base_price * 0.15

    # Add med_tf structure (medium waves)
    med_tf_period = n_bars // 16
    med_tf_wave = np.sin(np.linspace(0, 16 * np.pi, n_bars)) * base_price * 0.05

    # Add low_tf noise
    low_tf_noise = rng.normal(0, volatility * base_price, n_bars)

    # Combine
    prices = base_price + high_tf_wave + med_tf_wave + low_tf_noise

    return prices


# =============================================================================
# NEW Pattern Generators - Comprehensive Market Conditions
# =============================================================================

def _generate_trend_up_clean(
    rng: np.random.Generator,
    n_bars: int,
    base_price: float,
    volatility: float,
    config: PatternConfig | None = None,
) -> np.ndarray:
    """
    Generate clean uptrend with small pullbacks.

    Pattern: Up 70%, small pullback 15%, continue up 15%
    """
    cfg = config or PatternConfig()
    prices = np.zeros(n_bars)
    prices[0] = base_price

    # Phase boundaries
    trend1_end = int(n_bars * 0.7)
    pullback_end = int(n_bars * 0.85)

    # Trend rate per bar
    total_move = base_price * cfg.trend_magnitude
    trend_rate = total_move / trend1_end

    for i in range(1, n_bars):
        noise = rng.normal(0, volatility * base_price * cfg.noise_level)

        if i < trend1_end:
            # Main trend up
            prices[i] = prices[i-1] + trend_rate + noise
        elif i < pullback_end:
            # Pullback (30% of the move)
            pullback_rate = (total_move * cfg.pullback_depth) / (pullback_end - trend1_end)
            prices[i] = prices[i-1] - pullback_rate + noise
        else:
            # Continue trend
            prices[i] = prices[i-1] + trend_rate * 0.8 + noise

    return prices


def _generate_trend_down_clean(
    rng: np.random.Generator,
    n_bars: int,
    base_price: float,
    volatility: float,
    config: PatternConfig | None = None,
) -> np.ndarray:
    """Generate clean downtrend with small rallies."""
    cfg = config or PatternConfig()
    prices = np.zeros(n_bars)
    prices[0] = base_price

    trend1_end = int(n_bars * 0.7)
    rally_end = int(n_bars * 0.85)

    total_move = base_price * cfg.trend_magnitude
    trend_rate = total_move / trend1_end

    for i in range(1, n_bars):
        noise = rng.normal(0, volatility * base_price * cfg.noise_level)

        if i < trend1_end:
            prices[i] = prices[i-1] - trend_rate + noise
        elif i < rally_end:
            rally_rate = (total_move * cfg.pullback_depth) / (rally_end - trend1_end)
            prices[i] = prices[i-1] + rally_rate + noise
        else:
            prices[i] = prices[i-1] - trend_rate * 0.8 + noise

    return prices


def _generate_trend_grinding(
    rng: np.random.Generator,
    n_bars: int,
    base_price: float,
    volatility: float,
    config: PatternConfig | None = None,
) -> np.ndarray:
    """Generate slow, low-volatility grind up."""
    cfg = config or PatternConfig()
    prices = np.zeros(n_bars)
    prices[0] = base_price

    # Very slow trend with minimal noise
    total_move = base_price * cfg.trend_magnitude * 0.5  # Half the normal move
    trend_rate = total_move / n_bars
    low_vol = volatility * 0.3  # 30% of normal volatility

    for i in range(1, n_bars):
        noise = rng.normal(0, low_vol * base_price)
        prices[i] = prices[i-1] + trend_rate + noise

    return prices


def _generate_trend_parabolic(
    rng: np.random.Generator,
    n_bars: int,
    base_price: float,
    volatility: float,
    config: PatternConfig | None = None,
) -> np.ndarray:
    """Generate accelerating parabolic trend (blow-off top)."""
    cfg = config or PatternConfig()
    prices = np.zeros(n_bars)
    prices[0] = base_price

    # Exponential acceleration
    for i in range(1, n_bars):
        # Acceleration factor increases over time
        progress = i / n_bars
        accel = 1 + progress * 3  # 1x to 4x acceleration
        base_move = (base_price * cfg.trend_magnitude) / n_bars
        noise = rng.normal(0, volatility * base_price * cfg.noise_level)
        prices[i] = prices[i-1] + base_move * accel + noise

    return prices


def _generate_trend_exhaustion(
    rng: np.random.Generator,
    n_bars: int,
    base_price: float,
    volatility: float,
    config: PatternConfig | None = None,
) -> np.ndarray:
    """Generate trend that exhausts and reverses."""
    cfg = config or PatternConfig()
    prices = np.zeros(n_bars)
    prices[0] = base_price

    trend_end = int(n_bars * 0.6)
    exhaust_end = int(n_bars * 0.75)

    total_move = base_price * cfg.trend_magnitude
    trend_rate = total_move / trend_end

    for i in range(1, n_bars):
        noise = rng.normal(0, volatility * base_price * cfg.noise_level)

        if i < trend_end:
            # Strong trend up
            prices[i] = prices[i-1] + trend_rate + noise
        elif i < exhaust_end:
            # Exhaustion - slowing, choppy
            prices[i] = prices[i-1] + rng.normal(0, volatility * base_price * 2)
        else:
            # Reversal down
            reversal_rate = total_move * 0.6 / (n_bars - exhaust_end)
            prices[i] = prices[i-1] - reversal_rate + noise

    return prices


def _generate_trend_stairs(
    rng: np.random.Generator,
    n_bars: int,
    base_price: float,
    volatility: float,
    config: PatternConfig | None = None,
) -> np.ndarray:
    """Generate stair-step pattern: trend, pause, trend, pause."""
    cfg = config or PatternConfig()
    prices = np.zeros(n_bars)
    prices[0] = base_price

    steps = cfg.stairs_steps
    bars_per_step = n_bars // steps
    step_move = (base_price * cfg.trend_magnitude) / steps

    for i in range(1, n_bars):
        step_num = i // bars_per_step
        pos_in_step = i % bars_per_step
        step_progress = pos_in_step / bars_per_step

        noise = rng.normal(0, volatility * base_price * cfg.noise_level)

        if step_progress < 0.6:  # 60% trending
            trend_rate = step_move / (bars_per_step * 0.6)
            prices[i] = prices[i-1] + trend_rate + noise
        else:  # 40% consolidation
            # Mean revert to current step level
            target = base_price + (step_num + 1) * step_move
            reversion = 0.1 * (target - prices[i-1])
            prices[i] = prices[i-1] + reversion + noise

    return prices


def _generate_range_tight(
    rng: np.random.Generator,
    n_bars: int,
    base_price: float,
    volatility: float,
    config: PatternConfig | None = None,
) -> np.ndarray:
    """Generate tight range / squeeze pattern."""
    cfg = config or PatternConfig()
    prices = np.zeros(n_bars)
    prices[0] = base_price

    # Very low volatility, strong mean reversion
    squeeze_vol = cfg.volatility_squeeze
    mean_reversion = 0.2

    for i in range(1, n_bars):
        reversion = mean_reversion * (base_price - prices[i-1])
        noise = rng.normal(0, squeeze_vol * base_price)
        prices[i] = prices[i-1] + reversion + noise

    return prices


def _generate_range_wide(
    rng: np.random.Generator,
    n_bars: int,
    base_price: float,
    volatility: float,
    config: PatternConfig | None = None,
) -> np.ndarray:
    """Generate wide range with high volatility but no direction."""
    cfg = config or PatternConfig()
    prices = np.zeros(n_bars)
    prices[0] = base_price

    range_high = base_price * (1 + cfg.range_width / 2)
    range_low = base_price * (1 - cfg.range_width / 2)

    for i in range(1, n_bars):
        # Random walk with boundary reflection
        change = rng.normal(0, volatility * base_price * 1.5)
        new_price = prices[i-1] + change

        # Soft boundaries - mean revert when near edges
        if new_price > range_high:
            new_price = range_high - abs(rng.normal(0, volatility * base_price))
        elif new_price < range_low:
            new_price = range_low + abs(rng.normal(0, volatility * base_price))

        prices[i] = new_price

    return prices


def _generate_range_ascending(
    rng: np.random.Generator,
    n_bars: int,
    base_price: float,
    volatility: float,
    config: PatternConfig | None = None,
) -> np.ndarray:
    """Generate ascending triangle: higher lows, flat resistance."""
    cfg = config or PatternConfig()
    prices = np.zeros(n_bars)
    prices[0] = base_price

    resistance = base_price * (1 + cfg.range_width / 2)

    for i in range(1, n_bars):
        progress = i / n_bars
        # Rising support level
        support = base_price * (1 - cfg.range_width / 2) + progress * base_price * cfg.range_width * 0.8

        noise = rng.normal(0, volatility * base_price * cfg.noise_level)
        mid = (support + resistance) / 2

        # Oscillate between support and resistance
        phase = np.sin(progress * 8 * np.pi)
        prices[i] = mid + phase * (resistance - support) / 2 + noise

        # Enforce boundaries
        prices[i] = max(support, min(resistance, prices[i]))

    return prices


def _generate_range_descending(
    rng: np.random.Generator,
    n_bars: int,
    base_price: float,
    volatility: float,
    config: PatternConfig | None = None,
) -> np.ndarray:
    """Generate descending triangle: flat support, lower highs."""
    cfg = config or PatternConfig()
    prices = np.zeros(n_bars)
    prices[0] = base_price

    support = base_price * (1 - cfg.range_width / 2)

    for i in range(1, n_bars):
        progress = i / n_bars
        # Falling resistance level
        resistance = base_price * (1 + cfg.range_width / 2) - progress * base_price * cfg.range_width * 0.8

        noise = rng.normal(0, volatility * base_price * cfg.noise_level)
        mid = (support + resistance) / 2

        phase = np.sin(progress * 8 * np.pi)
        prices[i] = mid + phase * (resistance - support) / 2 + noise

        prices[i] = max(support, min(resistance, prices[i]))

    return prices


def _generate_reversal_v_bottom(
    rng: np.random.Generator,
    n_bars: int,
    base_price: float,
    volatility: float,
    config: PatternConfig | None = None,
) -> np.ndarray:
    """Generate sharp V-bottom reversal."""
    cfg = config or PatternConfig()
    prices = np.zeros(n_bars)
    prices[0] = base_price

    bottom_bar = n_bars // 2
    drop_magnitude = base_price * cfg.trend_magnitude

    for i in range(1, n_bars):
        noise = rng.normal(0, volatility * base_price * cfg.noise_level)

        if i < bottom_bar:
            # Sharp drop
            drop_rate = drop_magnitude / bottom_bar
            prices[i] = prices[i-1] - drop_rate + noise
        else:
            # Sharp recovery
            recovery_rate = drop_magnitude / (n_bars - bottom_bar)
            prices[i] = prices[i-1] + recovery_rate + noise

    return prices


def _generate_reversal_v_top(
    rng: np.random.Generator,
    n_bars: int,
    base_price: float,
    volatility: float,
    config: PatternConfig | None = None,
) -> np.ndarray:
    """Generate sharp V-top reversal."""
    cfg = config or PatternConfig()
    prices = np.zeros(n_bars)
    prices[0] = base_price

    top_bar = n_bars // 2
    rise_magnitude = base_price * cfg.trend_magnitude

    for i in range(1, n_bars):
        noise = rng.normal(0, volatility * base_price * cfg.noise_level)

        if i < top_bar:
            rise_rate = rise_magnitude / top_bar
            prices[i] = prices[i-1] + rise_rate + noise
        else:
            drop_rate = rise_magnitude / (n_bars - top_bar)
            prices[i] = prices[i-1] - drop_rate + noise

    return prices


def _generate_reversal_double_bottom(
    rng: np.random.Generator,
    n_bars: int,
    base_price: float,
    volatility: float,
    config: PatternConfig | None = None,
) -> np.ndarray:
    """Generate W-pattern double bottom."""
    cfg = config or PatternConfig()
    prices = np.zeros(n_bars)
    prices[0] = base_price

    # W pattern: drop, bounce, drop to same level, rally
    first_bottom = int(n_bars * 0.25)
    middle_peak = int(n_bars * 0.5)
    second_bottom = int(n_bars * 0.75)
    drop_magnitude = base_price * cfg.trend_magnitude

    bottom_price = base_price - drop_magnitude

    for i in range(1, n_bars):
        noise = rng.normal(0, volatility * base_price * cfg.noise_level)

        if i < first_bottom:
            rate = drop_magnitude / first_bottom
            prices[i] = prices[i-1] - rate + noise
        elif i < middle_peak:
            rate = (drop_magnitude * 0.5) / (middle_peak - first_bottom)
            prices[i] = prices[i-1] + rate + noise
        elif i < second_bottom:
            rate = (drop_magnitude * 0.5) / (second_bottom - middle_peak)
            prices[i] = prices[i-1] - rate + noise
        else:
            rate = drop_magnitude / (n_bars - second_bottom)
            prices[i] = prices[i-1] + rate + noise

    return prices


def _generate_reversal_double_top(
    rng: np.random.Generator,
    n_bars: int,
    base_price: float,
    volatility: float,
    config: PatternConfig | None = None,
) -> np.ndarray:
    """Generate M-pattern double top."""
    cfg = config or PatternConfig()
    prices = np.zeros(n_bars)
    prices[0] = base_price

    first_top = int(n_bars * 0.25)
    middle_dip = int(n_bars * 0.5)
    second_top = int(n_bars * 0.75)
    rise_magnitude = base_price * cfg.trend_magnitude

    for i in range(1, n_bars):
        noise = rng.normal(0, volatility * base_price * cfg.noise_level)

        if i < first_top:
            rate = rise_magnitude / first_top
            prices[i] = prices[i-1] + rate + noise
        elif i < middle_dip:
            rate = (rise_magnitude * 0.5) / (middle_dip - first_top)
            prices[i] = prices[i-1] - rate + noise
        elif i < second_top:
            rate = (rise_magnitude * 0.5) / (second_top - middle_dip)
            prices[i] = prices[i-1] + rate + noise
        else:
            rate = rise_magnitude / (n_bars - second_top)
            prices[i] = prices[i-1] - rate + noise

    return prices


def _generate_breakout_clean(
    rng: np.random.Generator,
    n_bars: int,
    base_price: float,
    volatility: float,
    config: PatternConfig | None = None,
) -> np.ndarray:
    """Generate clean breakout with follow-through."""
    cfg = config or PatternConfig()
    prices = np.zeros(n_bars)
    prices[0] = base_price

    range_end = int(n_bars * 0.6)
    breakout_end = int(n_bars * 0.7)

    range_high = base_price * (1 + cfg.range_width / 4)
    range_low = base_price * (1 - cfg.range_width / 4)

    for i in range(1, n_bars):
        noise = rng.normal(0, volatility * base_price * cfg.noise_level)

        if i < range_end:
            # Consolidation
            mid = (range_high + range_low) / 2
            phase = np.sin(i / range_end * 6 * np.pi)
            prices[i] = mid + phase * (range_high - range_low) / 2 + noise
        elif i < breakout_end:
            # Breakout bar(s) - strong move
            rate = (base_price * cfg.trend_magnitude * 0.3) / (breakout_end - range_end)
            prices[i] = prices[i-1] + rate + noise
        else:
            # Follow-through
            rate = (base_price * cfg.trend_magnitude * 0.5) / (n_bars - breakout_end)
            prices[i] = prices[i-1] + rate + noise

    return prices


def _generate_breakout_false(
    rng: np.random.Generator,
    n_bars: int,
    base_price: float,
    volatility: float,
    config: PatternConfig | None = None,
) -> np.ndarray:
    """Generate false breakout (fakeout) that reverses."""
    cfg = config or PatternConfig()
    prices = np.zeros(n_bars)
    prices[0] = base_price

    range_end = int(n_bars * 0.5)
    fakeout_end = int(n_bars * 0.6)
    reversal_end = int(n_bars * 0.8)

    range_high = base_price * (1 + cfg.range_width / 4)
    range_low = base_price * (1 - cfg.range_width / 4)

    for i in range(1, n_bars):
        noise = rng.normal(0, volatility * base_price * cfg.noise_level)

        if i < range_end:
            mid = (range_high + range_low) / 2
            phase = np.sin(i / range_end * 6 * np.pi)
            prices[i] = mid + phase * (range_high - range_low) / 2 + noise
        elif i < fakeout_end:
            # False breakout up
            rate = (base_price * cfg.hunt_depth * 2) / (fakeout_end - range_end)
            prices[i] = prices[i-1] + rate + noise
        elif i < reversal_end:
            # Sharp reversal down through range
            rate = (base_price * cfg.range_width) / (reversal_end - fakeout_end)
            prices[i] = prices[i-1] - rate + noise
        else:
            # Settle at lower level
            target = range_low - base_price * cfg.range_width * 0.2
            reversion = 0.1 * (target - prices[i-1])
            prices[i] = prices[i-1] + reversion + noise

    return prices


def _generate_breakout_retest(
    rng: np.random.Generator,
    n_bars: int,
    base_price: float,
    volatility: float,
    config: PatternConfig | None = None,
) -> np.ndarray:
    """Generate breakout with pullback retest then continuation."""
    cfg = config or PatternConfig()
    prices = np.zeros(n_bars)
    prices[0] = base_price

    range_end = int(n_bars * 0.4)
    breakout_end = int(n_bars * 0.5)
    retest_end = int(n_bars * 0.65)

    range_high = base_price * (1 + cfg.range_width / 4)

    for i in range(1, n_bars):
        noise = rng.normal(0, volatility * base_price * cfg.noise_level)

        if i < range_end:
            mid = base_price
            phase = np.sin(i / range_end * 6 * np.pi) * cfg.range_width / 4
            prices[i] = mid + phase * base_price + noise
        elif i < breakout_end:
            # Breakout
            rate = (range_high * 0.1) / (breakout_end - range_end)
            prices[i] = prices[i-1] + rate + noise
        elif i < retest_end:
            # Pullback to retest breakout level
            target = range_high
            reversion = 0.15 * (target - prices[i-1])
            prices[i] = prices[i-1] + reversion + noise
        else:
            # Continuation up
            rate = (base_price * cfg.trend_magnitude * 0.5) / (n_bars - retest_end)
            prices[i] = prices[i-1] + rate + noise

    return prices


def _generate_vol_squeeze_expand(
    rng: np.random.Generator,
    n_bars: int,
    base_price: float,
    volatility: float,
    config: PatternConfig | None = None,
) -> np.ndarray:
    """Generate volatility squeeze then expansion."""
    cfg = config or PatternConfig()
    prices = np.zeros(n_bars)
    prices[0] = base_price

    squeeze_end = int(n_bars * 0.6)
    expansion_end = int(n_bars * 0.75)

    for i in range(1, n_bars):
        if i < squeeze_end:
            # Decreasing volatility squeeze
            progress = i / squeeze_end
            current_vol = cfg.volatility_base * (1 - progress * 0.8)  # Vol decreases to 20%
            noise = rng.normal(0, current_vol * base_price)
            # Slight drift up
            prices[i] = prices[i-1] + base_price * 0.0001 + noise
        elif i < expansion_end:
            # Volatility expansion with direction
            noise = rng.normal(0, cfg.volatility_spike * base_price)
            rate = (base_price * cfg.trend_magnitude * 0.3) / (expansion_end - squeeze_end)
            prices[i] = prices[i-1] + rate + noise
        else:
            # Continue with elevated volatility
            noise = rng.normal(0, cfg.volatility_base * 1.5 * base_price)
            rate = (base_price * cfg.trend_magnitude * 0.3) / (n_bars - expansion_end)
            prices[i] = prices[i-1] + rate + noise

    return prices


def _generate_vol_spike_recover(
    rng: np.random.Generator,
    n_bars: int,
    base_price: float,
    volatility: float,
    config: PatternConfig | None = None,
) -> np.ndarray:
    """Generate flash crash with V-recovery."""
    cfg = config or PatternConfig()
    prices = np.zeros(n_bars)
    prices[0] = base_price

    normal_end = int(n_bars * 0.4)
    crash_end = int(n_bars * 0.5)
    recovery_end = int(n_bars * 0.7)

    crash_magnitude = base_price * cfg.volatility_spike * 2

    for i in range(1, n_bars):
        noise = rng.normal(0, volatility * base_price * cfg.noise_level)

        if i < normal_end:
            # Normal trading
            prices[i] = prices[i-1] + rng.normal(0, volatility * base_price)
        elif i < crash_end:
            # Flash crash
            rate = crash_magnitude / (crash_end - normal_end)
            prices[i] = prices[i-1] - rate + noise * 0.5
        elif i < recovery_end:
            # V-recovery
            rate = crash_magnitude / (recovery_end - crash_end)
            prices[i] = prices[i-1] + rate + noise * 0.5
        else:
            # Back to normal
            prices[i] = prices[i-1] + rng.normal(0, volatility * base_price)

    return prices


def _generate_vol_spike_continue(
    rng: np.random.Generator,
    n_bars: int,
    base_price: float,
    volatility: float,
    config: PatternConfig | None = None,
) -> np.ndarray:
    """Generate crash that continues (no recovery)."""
    cfg = config or PatternConfig()
    prices = np.zeros(n_bars)
    prices[0] = base_price

    normal_end = int(n_bars * 0.4)
    crash_end = int(n_bars * 0.55)

    crash_magnitude = base_price * cfg.volatility_spike * 2

    for i in range(1, n_bars):
        noise = rng.normal(0, volatility * base_price * cfg.noise_level)

        if i < normal_end:
            prices[i] = prices[i-1] + rng.normal(0, volatility * base_price)
        elif i < crash_end:
            # Sharp crash
            rate = crash_magnitude / (crash_end - normal_end)
            prices[i] = prices[i-1] - rate + noise * 0.5
        else:
            # Continued selling, slower pace
            rate = crash_magnitude * 0.3 / (n_bars - crash_end)
            prices[i] = prices[i-1] - rate + rng.normal(0, volatility * base_price * 1.5)

    return prices


def _generate_vol_decay(
    rng: np.random.Generator,
    n_bars: int,
    base_price: float,
    volatility: float,
    config: PatternConfig | None = None,
) -> np.ndarray:
    """Generate high volatility settling to low volatility."""
    cfg = config or PatternConfig()
    prices = np.zeros(n_bars)
    prices[0] = base_price

    for i in range(1, n_bars):
        progress = i / n_bars
        # Volatility decays from high to low
        current_vol = cfg.volatility_spike * (1 - progress * 0.9) + cfg.volatility_squeeze
        noise = rng.normal(0, current_vol * base_price)
        prices[i] = prices[i-1] + noise

    return prices


def _generate_liquidity_hunt_lows(
    rng: np.random.Generator,
    n_bars: int,
    base_price: float,
    volatility: float,
    config: PatternConfig | None = None,
) -> np.ndarray:
    """Generate stop hunt below support then rally."""
    cfg = config or PatternConfig()
    prices = np.zeros(n_bars)
    prices[0] = base_price

    range_end = int(n_bars * 0.5)
    hunt_end = int(n_bars * 0.6)
    recovery_end = int(n_bars * 0.75)

    support = base_price * (1 - cfg.range_width / 4)
    hunt_low = support * (1 - cfg.hunt_depth)

    for i in range(1, n_bars):
        noise = rng.normal(0, volatility * base_price * cfg.noise_level)

        if i < range_end:
            # Range with defined support
            mid = base_price
            phase = np.sin(i / range_end * 8 * np.pi)
            amplitude = (base_price - support) * 0.8
            prices[i] = support + amplitude + phase * amplitude * 0.3 + noise
        elif i < hunt_end:
            # Sweep below support
            rate = (support - hunt_low) / (hunt_end - range_end)
            prices[i] = prices[i-1] - rate + noise * 0.3
        elif i < recovery_end:
            # Sharp recovery
            rate = (base_price - hunt_low) / (recovery_end - hunt_end)
            prices[i] = prices[i-1] + rate + noise
        else:
            # Continue higher
            rate = (base_price * cfg.trend_magnitude * 0.3) / (n_bars - recovery_end)
            prices[i] = prices[i-1] + rate + noise

    return prices


def _generate_liquidity_hunt_highs(
    rng: np.random.Generator,
    n_bars: int,
    base_price: float,
    volatility: float,
    config: PatternConfig | None = None,
) -> np.ndarray:
    """Generate stop hunt above resistance then drop."""
    cfg = config or PatternConfig()
    prices = np.zeros(n_bars)
    prices[0] = base_price

    range_end = int(n_bars * 0.5)
    hunt_end = int(n_bars * 0.6)
    drop_end = int(n_bars * 0.75)

    resistance = base_price * (1 + cfg.range_width / 4)
    hunt_high = resistance * (1 + cfg.hunt_depth)

    for i in range(1, n_bars):
        noise = rng.normal(0, volatility * base_price * cfg.noise_level)

        if i < range_end:
            mid = base_price
            phase = np.sin(i / range_end * 8 * np.pi)
            amplitude = (resistance - base_price) * 0.8
            prices[i] = base_price + phase * amplitude + noise
        elif i < hunt_end:
            rate = (hunt_high - resistance) / (hunt_end - range_end)
            prices[i] = prices[i-1] + rate + noise * 0.3
        elif i < drop_end:
            rate = (hunt_high - base_price) / (drop_end - hunt_end)
            prices[i] = prices[i-1] - rate + noise
        else:
            rate = (base_price * cfg.trend_magnitude * 0.3) / (n_bars - drop_end)
            prices[i] = prices[i-1] - rate + noise

    return prices


def _generate_choppy_whipsaw(
    rng: np.random.Generator,
    n_bars: int,
    base_price: float,
    volatility: float,
    config: PatternConfig | None = None,
) -> np.ndarray:
    """Generate choppy price action with many false signals."""
    cfg = config or PatternConfig()
    prices = np.zeros(n_bars)
    prices[0] = base_price

    # Multiple small waves with no clear direction
    for i in range(1, n_bars):
        # Random direction changes
        if rng.random() < 0.15:  # 15% chance of direction flip
            direction = rng.choice([-1, 1])
        else:
            direction = 1 if prices[i-1] < base_price else -1

        move = direction * rng.uniform(0.5, 1.5) * volatility * base_price
        noise = rng.normal(0, volatility * base_price * 0.5)

        prices[i] = prices[i-1] + move + noise

        # Keep in general range
        if prices[i] > base_price * 1.05:
            prices[i] = base_price * 1.05 - rng.uniform(0, volatility * base_price)
        elif prices[i] < base_price * 0.95:
            prices[i] = base_price * 0.95 + rng.uniform(0, volatility * base_price)

    return prices


def _generate_accumulation(
    rng: np.random.Generator,
    n_bars: int,
    base_price: float,
    volatility: float,
    config: PatternConfig | None = None,
) -> np.ndarray:
    """Generate accumulation pattern: low vol, slight drift up."""
    cfg = config or PatternConfig()
    prices = np.zeros(n_bars)
    prices[0] = base_price

    # Very subtle upward drift with low volatility
    drift_rate = (base_price * cfg.trend_magnitude * 0.3) / n_bars
    low_vol = volatility * 0.4

    for i in range(1, n_bars):
        noise = rng.normal(0, low_vol * base_price)
        prices[i] = prices[i-1] + drift_rate + noise

    return prices


def _generate_distribution(
    rng: np.random.Generator,
    n_bars: int,
    base_price: float,
    volatility: float,
    config: PatternConfig | None = None,
) -> np.ndarray:
    """Generate distribution pattern: low vol, slight drift down."""
    cfg = config or PatternConfig()
    prices = np.zeros(n_bars)
    prices[0] = base_price

    drift_rate = (base_price * cfg.trend_magnitude * 0.3) / n_bars
    low_vol = volatility * 0.4

    for i in range(1, n_bars):
        noise = rng.normal(0, low_vol * base_price)
        prices[i] = prices[i-1] - drift_rate + noise

    return prices


def _generate_mtf_aligned_bull(
    rng: np.random.Generator,
    n_bars: int,
    base_price: float,
    volatility: float,
    config: PatternConfig | None = None,
) -> np.ndarray:
    """Generate multi-timeframe aligned bullish trend."""
    cfg = config or PatternConfig()

    # Strong uptrend with small pullbacks at different frequencies
    high_tf_wave = np.sin(np.linspace(0, 2 * np.pi, n_bars)) * base_price * 0.03  # Small wave
    med_tf_wave = np.sin(np.linspace(0, 8 * np.pi, n_bars)) * base_price * 0.01
    noise = rng.normal(0, volatility * base_price * cfg.noise_level, n_bars)

    # Strong upward trend component
    trend = np.linspace(0, base_price * cfg.trend_magnitude, n_bars)

    prices = base_price + trend + high_tf_wave + med_tf_wave + noise

    return prices


def _generate_mtf_aligned_bear(
    rng: np.random.Generator,
    n_bars: int,
    base_price: float,
    volatility: float,
    config: PatternConfig | None = None,
) -> np.ndarray:
    """Generate multi-timeframe aligned bearish trend."""
    cfg = config or PatternConfig()

    high_tf_wave = np.sin(np.linspace(0, 2 * np.pi, n_bars)) * base_price * 0.03
    med_tf_wave = np.sin(np.linspace(0, 8 * np.pi, n_bars)) * base_price * 0.01
    noise = rng.normal(0, volatility * base_price * cfg.noise_level, n_bars)

    trend = np.linspace(0, -base_price * cfg.trend_magnitude, n_bars)

    prices = base_price + trend + high_tf_wave + med_tf_wave + noise

    return prices


def _generate_mtf_pullback_bull(
    rng: np.random.Generator,
    n_bars: int,
    base_price: float,
    volatility: float,
    config: PatternConfig | None = None,
) -> np.ndarray:
    """Generate higher TF uptrend with lower TF pullback."""
    cfg = config or PatternConfig()

    # Higher TF uptrend
    trend = np.linspace(0, base_price * cfg.trend_magnitude, n_bars)

    # Lower TF pullback in the middle
    pullback = np.zeros(n_bars)
    pullback_start = int(n_bars * 0.4)
    pullback_end = int(n_bars * 0.6)
    pullback_depth = base_price * cfg.trend_magnitude * cfg.pullback_depth

    for i in range(n_bars):
        if pullback_start <= i < pullback_end:
            progress = (i - pullback_start) / (pullback_end - pullback_start)
            pullback[i] = -np.sin(progress * np.pi) * pullback_depth

    noise = rng.normal(0, volatility * base_price * cfg.noise_level, n_bars)

    prices = base_price + trend + pullback + noise

    return prices


def _generate_mtf_pullback_bear(
    rng: np.random.Generator,
    n_bars: int,
    base_price: float,
    volatility: float,
    config: PatternConfig | None = None,
) -> np.ndarray:
    """Generate higher TF downtrend with lower TF rally."""
    cfg = config or PatternConfig()

    trend = np.linspace(0, -base_price * cfg.trend_magnitude, n_bars)

    rally = np.zeros(n_bars)
    rally_start = int(n_bars * 0.4)
    rally_end = int(n_bars * 0.6)
    rally_height = base_price * cfg.trend_magnitude * cfg.pullback_depth

    for i in range(n_bars):
        if rally_start <= i < rally_end:
            progress = (i - rally_start) / (rally_end - rally_start)
            rally[i] = np.sin(progress * np.pi) * rally_height

    noise = rng.normal(0, volatility * base_price * cfg.noise_level, n_bars)

    prices = base_price + trend + rally + noise

    return prices


# =============================================================================
# Pattern Registry - Maps pattern names to generators
# =============================================================================
PATTERN_GENERATORS = {
    # Legacy patterns (backwards compatible)
    "trending": _generate_trending_prices,
    "ranging": _generate_ranging_prices,
    "volatile": _generate_volatile_prices,
    "multi_tf_aligned": _generate_multi_tf_aligned_prices,
    # Trend patterns
    "trend_up_clean": _generate_trend_up_clean,
    "trend_down_clean": _generate_trend_down_clean,
    "trend_grinding": _generate_trend_grinding,
    "trend_parabolic": _generate_trend_parabolic,
    "trend_exhaustion": _generate_trend_exhaustion,
    "trend_stairs": _generate_trend_stairs,
    # Range patterns
    "range_tight": _generate_range_tight,
    "range_wide": _generate_range_wide,
    "range_ascending": _generate_range_ascending,
    "range_descending": _generate_range_descending,
    # Reversal patterns
    "reversal_v_bottom": _generate_reversal_v_bottom,
    "reversal_v_top": _generate_reversal_v_top,
    "reversal_double_bottom": _generate_reversal_double_bottom,
    "reversal_double_top": _generate_reversal_double_top,
    # Breakout patterns
    "breakout_clean": _generate_breakout_clean,
    "breakout_false": _generate_breakout_false,
    "breakout_retest": _generate_breakout_retest,
    # Volatility patterns
    "vol_squeeze_expand": _generate_vol_squeeze_expand,
    "vol_spike_recover": _generate_vol_spike_recover,
    "vol_spike_continue": _generate_vol_spike_continue,
    "vol_decay": _generate_vol_decay,
    # Liquidity/manipulation patterns
    "liquidity_hunt_lows": _generate_liquidity_hunt_lows,
    "liquidity_hunt_highs": _generate_liquidity_hunt_highs,
    "choppy_whipsaw": _generate_choppy_whipsaw,
    "accumulation": _generate_accumulation,
    "distribution": _generate_distribution,
    # Multi-timeframe patterns
    "mtf_aligned_bull": _generate_mtf_aligned_bull,
    "mtf_aligned_bear": _generate_mtf_aligned_bear,
    "mtf_pullback_bull": _generate_mtf_pullback_bull,
    "mtf_pullback_bear": _generate_mtf_pullback_bear,
}


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
def calculate_warmup_for_play(play_id: str, base_dir: Path | None = None) -> dict[str, int]:
    """
    Calculate warmup bars needed per timeframe for a Play.

    Loads the Play, builds a feature registry, and computes the max warmup
    for each timeframe based on declared indicators and structures.

    Args:
        play_id: Play identifier (e.g., "V_100_blocks_basic")
        base_dir: Optional base directory for Play files

    Returns:
        Dict mapping timeframe -> warmup bars needed

    Example:
        >>> warmup = calculate_warmup_for_play("V_100_blocks_basic")
        >>> print(warmup)  # {"15m": 60}
    """
    from src.backtest import load_play
    from src.backtest.feature_registry import FeatureRegistry

    # Load the play
    play = load_play(play_id, base_dir=base_dir)

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
    base_dir: Path | None = None,
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
        base_dir: Optional base directory for Play files

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
    play = load_play(play_id, base_dir=base_dir)

    # Collect all TFs used by the play from features
    timeframes = set()
    timeframes.add(play.execution_tf)  # exec TF

    # Add TFs from features (Feature objects have a .tf attribute)
    for feature in play.features:
        if feature.tf:
            timeframes.add(feature.tf)

    timeframes_list = sorted(timeframes, key=lambda tf: TF_TO_MINUTES.get(tf, 0))

    # Get warmup requirements
    warmup_by_tf = calculate_warmup_for_play(play_id, base_dir=base_dir)

    # Find slowest TF for alignment
    slowest_tf = max(timeframes_list, key=lambda tf: TF_TO_MINUTES[tf])

    # Calculate bars needed for slowest TF
    slowest_warmup = warmup_by_tf.get(slowest_tf, 50)
    slowest_bars = slowest_warmup + extra_bars

    # Get symbol from play (first in symbol_universe or default)
    symbol = play.symbol_universe[0] if play.symbol_universe else DEFAULT_SYMBOL

    # Generate with multi-TF alignment
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
        align_multi_tf=True,
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
    align_multi_tf: bool = True,
    config: PatternConfig | None = None,
) -> SyntheticCandles:
    """
    Generate synthetic OHLCV data for all timeframes.

    Args:
        symbol: Trading symbol (default: "BTCUSDT")
        timeframes: List of timeframes to generate (default: ["1m", "5m", "15m", "1h", "4h"])
        bars_per_tf: Number of bars for slowest TF (default: 1000). When align_multi_tf=True,
            faster TFs get proportionally more bars to cover the same time range.
        seed: Random seed for reproducibility (default: 42)
        pattern: Price pattern type. Options include:
            Legacy: "trending", "ranging", "volatile", "multi_tf_aligned"
            Trends: "trend_up_clean", "trend_down_clean", "trend_grinding",
                   "trend_parabolic", "trend_exhaustion", "trend_stairs"
            Ranges: "range_tight", "range_wide", "range_ascending", "range_descending"
            Reversals: "reversal_v_bottom", "reversal_v_top",
                      "reversal_double_bottom", "reversal_double_top"
            Breakouts: "breakout_clean", "breakout_false", "breakout_retest"
            Volatility: "vol_squeeze_expand", "vol_spike_recover",
                       "vol_spike_continue", "vol_decay"
            Liquidity: "liquidity_hunt_lows", "liquidity_hunt_highs",
                      "choppy_whipsaw", "accumulation", "distribution"
            Multi-TF: "mtf_aligned_bull", "mtf_aligned_bear",
                     "mtf_pullback_bull", "mtf_pullback_bear"
        base_price: Starting price (default: 50000.0)
        volatility: Daily volatility (default: 0.02 = 2%)
        base_timestamp: Starting timestamp (default: 2025-01-01 00:00 UTC)
        correlate_volume: If True (default), volume correlates with price moves.
        align_multi_tf: If True (default), all timeframes cover the same time range.
        config: Optional PatternConfig for fine-tuning pattern parameters.

    Returns:
        SyntheticCandles with OHLCV DataFrames for each timeframe

    Example:
        >>> # Generate clean uptrend with custom config
        >>> from src.forge.validation import PatternConfig
        >>> config = PatternConfig(trend_magnitude=0.30)  # 30% move
        >>> candles = generate_synthetic_candles(
        ...     pattern="trend_up_clean",
        ...     bars_per_tf=500,
        ...     config=config,
        ... )
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

    # Select pattern generator from registry
    if pattern not in PATTERN_GENERATORS:
        raise ValueError(f"Unknown pattern: {pattern}. Valid: {list(PATTERN_GENERATORS.keys())}")

    generator = PATTERN_GENERATORS[pattern]

    # Check if generator accepts config parameter (new-style generators)
    import inspect
    sig = inspect.signature(generator)
    accepts_config = "config" in sig.parameters

    # Calculate bar counts per timeframe
    bar_counts: dict[str, int] = {}

    if align_multi_tf:
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
        if accepts_config:
            close_prices = generator(
                rng=rng,
                n_bars=n_bars,
                base_price=base_price,
                volatility=tf_volatility,
                config=config,  # Pass config (None uses defaults)
            )
        else:
            # Legacy generators don't accept config
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
        align_multi_tf=align_multi_tf,
        total_minutes=total_minutes,
        base_price=base_price,
        volatility=volatility,
        data_hash=data_hash,
    )


# =============================================================================
# Single-TF DataFrame Generator (for toolkit audits)
# =============================================================================
def generate_synthetic_ohlcv_df(
    n_bars: int = 2000,
    seed: int = DEFAULT_SEED,
    pattern: PatternType = "trending",
    tf_minutes: int = 15,
    base_price: float = 100.0,
    volatility: float = 0.02,
    base_timestamp: datetime | None = None,
) -> pd.DataFrame:
    """
    Generate deterministic synthetic OHLCV DataFrame for toolkit audits.

    This is a single-timeframe generator optimized for indicator validation.
    Uses regime changes (trend → range → spike → mean-revert) to exercise
    indicator behavior across different market conditions.

    Args:
        n_bars: Number of bars (default: 2000)
        seed: Random seed for reproducibility (default: 42)
        pattern: Price pattern type (default: "trending")
        tf_minutes: Timeframe in minutes (default: 15)
        base_price: Starting price level (default: 100.0)
        volatility: Daily volatility (default: 0.02)
        base_timestamp: Starting timestamp (default: 2024-01-01)

    Returns:
        DataFrame with timestamp, open, high, low, close, volume columns

    Example:
        >>> df = generate_synthetic_ohlcv_df(n_bars=1000, seed=42)
        >>> print(df.columns.tolist())
        ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    """
    if base_timestamp is None:
        base_timestamp = datetime(2024, 1, 1, 0, 0, 0)

    rng = np.random.default_rng(seed)

    # Generate base price with regime changes
    # Split into 4 regimes: trend up, range, spike, mean-revert
    regime_size = n_bars // 4

    prices = []
    current_price = base_price

    # Regime 1: Trend up
    for i in range(regime_size):
        current_price += rng.uniform(0.01, 0.05)
        prices.append(current_price + rng.normal(0, 0.5))

    # Regime 2: Range-bound
    range_center = current_price
    for i in range(regime_size):
        prices.append(range_center + rng.normal(0, 2.0))

    # Regime 3: Spike (high volatility)
    for i in range(regime_size):
        spike = rng.choice([-1, 1]) * rng.uniform(0.5, 3.0)
        prices.append(prices[-1] + spike)

    # Regime 4: Mean-revert back to baseline
    target = range_center
    for i in range(n_bars - 3 * regime_size):
        current = prices[-1]
        revert = (target - current) * 0.02
        prices.append(current + revert + rng.normal(0, 0.3))

    prices = np.array(prices)

    # Generate OHLC from close prices
    # Add random intrabar movement while maintaining constraints
    close = prices

    # Open is close shifted by random amount
    open_shift = rng.uniform(-1.0, 1.0, n_bars)
    open_ = close + open_shift

    # High >= max(open, close)
    max_oc = np.maximum(open_, close)
    high = max_oc + np.abs(rng.normal(0, 0.5, n_bars))

    # Low <= min(open, close)
    min_oc = np.minimum(open_, close)
    low = min_oc - np.abs(rng.normal(0, 0.5, n_bars))

    # Non-zero volume with some variation
    volume = rng.uniform(1000, 10000, n_bars) * (1 + np.abs(rng.normal(0, 0.5, n_bars)))

    # Generate timestamps
    timestamps = [base_timestamp + timedelta(minutes=tf_minutes * i) for i in range(n_bars)]

    return pd.DataFrame({
        "timestamp": timestamps,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


# =============================================================================
# QuoteState List Generator (for rollup audits)
# =============================================================================
def generate_synthetic_quotes(
    n_quotes: int = 100,
    seed: int = DEFAULT_SEED,
    base_price: float = 100.0,
    base_ts_ms: int | None = None,
) -> list:
    """
    Generate deterministic synthetic QuoteState data for rollup audits.

    Creates quotes with realistic price movements and volume patterns
    suitable for testing ExecRollupBucket accumulation and snapshot accessors.

    Args:
        n_quotes: Number of quotes to generate (default: 100)
        seed: Random seed for reproducibility (default: 42)
        base_price: Starting price level (default: 100.0)
        base_ts_ms: Starting timestamp in milliseconds (default: 2024-01-01 00:00 UTC)

    Returns:
        List of QuoteState objects

    Example:
        >>> quotes = generate_synthetic_quotes(n_quotes=50, seed=42)
        >>> print(len(quotes))
        50
        >>> print(quotes[0].last)  # First quote price
    """
    # Lazy import to avoid circular dependencies
    from src.backtest.runtime.quote_state import QuoteState

    if base_ts_ms is None:
        base_ts_ms = 1704067200000  # 2024-01-01 00:00:00 UTC

    rng = np.random.default_rng(seed)

    quotes = []
    price = base_price

    for i in range(n_quotes):
        # Random walk for price
        price += rng.normal(0, 0.5)

        # Ensure price stays positive
        price = max(price, 1.0)

        # Generate intrabar high/low
        spread = abs(rng.normal(0, 0.3))
        high = price + spread
        low = price - spread

        # Volume with variation
        volume = 1000 + abs(rng.normal(0, 500))

        # For simplicity in tests, open_1m = close of previous bar or base_price for first
        open_price = price if i == 0 else quotes[-1].last

        quote = QuoteState(
            ts_ms=base_ts_ms + i * 60000,  # 1-minute intervals
            last=price,
            open_1m=open_price,
            high_1m=high,
            low_1m=low,
            mark=price * (1 + rng.normal(0, 0.0001)),  # Tiny mark deviation
            mark_source="approx_from_ohlcv_1m",
            volume_1m=volume,
        )
        quotes.append(quote)

    return quotes


# =============================================================================
# BarData List Generator (for structure audits)
# =============================================================================
def generate_synthetic_bars(
    n_bars: int = 100,
    seed: int = DEFAULT_SEED,
    pattern: PatternType = "trending",
    base_price: float = DEFAULT_BASE_PRICE,
    volatility: float = DEFAULT_VOLATILITY,
    indicators: dict[str, float] | None = None,
) -> list:
    """
    Generate deterministic synthetic BarData for structure detection audits.

    Creates BarData objects suitable for testing incremental structure detectors
    (swing, zone, fibonacci, trend, rolling_window).

    Args:
        n_bars: Number of bars to generate (default: 100)
        seed: Random seed for reproducibility (default: 42)
        pattern: Price pattern type (default: "trending")
        base_price: Starting price (default: 50000.0)
        volatility: Daily volatility (default: 0.02)
        indicators: Optional dict of indicator values to include (default: empty)

    Returns:
        List of BarData objects

    Example:
        >>> bars = generate_synthetic_bars(n_bars=50, pattern="trending")
        >>> print(len(bars))
        50
        >>> print(bars[0].close)  # First bar close price
    """
    # Lazy import to avoid circular dependencies
    from src.structures import BarData

    rng = np.random.default_rng(seed)

    # Select pattern generator
    pattern_generators = {
        "trending": _generate_trending_prices,
        "ranging": _generate_ranging_prices,
        "volatile": _generate_volatile_prices,
        "multi_tf_aligned": _generate_multi_tf_aligned_prices,
    }

    if pattern not in pattern_generators:
        raise ValueError(f"Unknown pattern: {pattern}. Valid: {list(pattern_generators.keys())}")

    generator = pattern_generators[pattern]

    # Generate close prices
    close_prices = generator(
        rng=rng,
        n_bars=n_bars,
        base_price=base_price,
        volatility=volatility,
    )

    # Default indicators if not provided
    if indicators is None:
        indicators = {}

    bars = []
    for i in range(n_bars):
        close = close_prices[i]

        # Generate OHLC from close
        if i > 0:
            open_price = close_prices[i - 1] * (1 + rng.normal(0, 0.001))
        else:
            open_price = close

        # High is max of open/close plus some wick
        base_high = max(open_price, close)
        high = base_high * (1 + abs(rng.normal(0, 0.005)))

        # Low is min of open/close minus some wick
        base_low = min(open_price, close)
        low = base_low * (1 - abs(rng.normal(0, 0.005)))

        # Volume
        volume = rng.lognormal(mean=10, sigma=0.8) * 1000

        bar = BarData(
            idx=i,
            open=open_price,
            high=high,
            low=low,
            close=close,
            volume=volume,
            indicators=indicators.copy(),  # Will be wrapped in MappingProxyType
        )
        bars.append(bar)

    return bars


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
