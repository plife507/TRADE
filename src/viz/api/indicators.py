"""
Indicator Reference API endpoints.

Provides endpoints for browsing the indicator registry with metadata and sample data.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from fastapi import APIRouter
from pydantic import BaseModel

from src.backtest.indicator_registry import (
    INDICATOR_OUTPUT_TYPES,
    SUPPORTED_INDICATORS,
    get_registry,
)


router = APIRouter(prefix="/indicators", tags=["indicators"])


# =============================================================================
# Response Models
# =============================================================================


class IndicatorParam(BaseModel):
    """Parameter definition for an indicator."""

    name: str
    default: Any | None = None


class IndicatorOutput(BaseModel):
    """Output definition for multi-output indicators."""

    key: str
    output_type: str  # FLOAT, INT, BOOL, ENUM


class IndicatorInfo(BaseModel):
    """Full information about an indicator."""

    name: str
    is_multi_output: bool
    input_series: list[str]
    params: list[IndicatorParam]
    output_keys: list[str]  # For multi-output: ["macd", "signal", "histogram"]
    outputs: list[IndicatorOutput]  # With type info
    primary_output: str | None
    warmup_description: str
    category: str  # "momentum", "trend", "volatility", "volume"


class SampleDataPoint(BaseModel):
    """A single point for sample chart data."""

    x: int  # Bar index
    y: float


class SampleChartData(BaseModel):
    """Sample data for visualizing an indicator."""

    indicator_name: str
    series: dict[str, list[SampleDataPoint]]  # output_key -> points
    price_data: list[SampleDataPoint] | None  # For overlay indicators


class IndicatorReferenceResponse(BaseModel):
    """Response containing all indicator reference data."""

    total: int
    indicators: list[IndicatorInfo]
    categories: dict[str, int]  # Category -> count


class IndicatorSampleResponse(BaseModel):
    """Response containing sample chart data for an indicator."""

    indicator: IndicatorInfo
    sample_data: SampleChartData


# =============================================================================
# Indicator Categorization
# =============================================================================

# Map indicators to categories for better organization
INDICATOR_CATEGORIES: dict[str, str] = {
    # Trend / Moving Averages
    "ema": "trend",
    "sma": "trend",
    "kama": "trend",
    "alma": "trend",
    "wma": "trend",
    "dema": "trend",
    "tema": "trend",
    "trima": "trend",
    "zlma": "trend",
    "linreg": "trend",
    "supertrend": "trend",
    "psar": "trend",
    # Momentum
    "rsi": "momentum",
    "stoch": "momentum",
    "stochrsi": "momentum",
    "macd": "momentum",
    "cci": "momentum",
    "willr": "momentum",
    "roc": "momentum",
    "mom": "momentum",
    "cmo": "momentum",
    "trix": "momentum",
    "uo": "momentum",
    "ppo": "momentum",
    "tsi": "momentum",
    "fisher": "momentum",
    "aroon": "momentum",
    "adx": "momentum",
    "dm": "momentum",
    "vortex": "momentum",
    # Volatility
    "atr": "volatility",
    "natr": "volatility",
    "bbands": "volatility",
    "kc": "volatility",
    "donchian": "volatility",
    "squeeze": "volatility",
    # Volume
    "mfi": "volume",
    "obv": "volume",
    "cmf": "volume",
    "kvo": "volume",
    # Other
    "ohlc4": "other",
    "midprice": "other",
}


# =============================================================================
# Warmup Description Generator
# =============================================================================

WARMUP_DESCRIPTIONS: dict[str, str] = {
    "ema": "3 x length (EMA stabilization)",
    "sma": "length bars",
    "rsi": "length + 1 (for first delta)",
    "atr": "length + 1 (needs previous close)",
    "macd": "3 x slow + signal (EMA stabilization)",
    "bbands": "length bars (same as SMA)",
    "stoch": "k + smooth_k + d",
    "stochrsi": "rsi_length + length + max(k, d)",
    "adx": "2 x length (for smoothing)",
    "supertrend": "length + 1 (ATR warmup)",
    "psar": "2 bars (minimal)",
    "squeeze": "max(bb_length, kc_length)",
    "kc": "3 x length + 1 (EMA + ATR)",
    "donchian": "max(lower_length, upper_length)",
    "aroon": "length + 1",
    "fisher": "length bars",
    "tsi": "fast + slow + signal",
    "kvo": "fast + slow + signal",
    "uo": "max(fast, medium, slow)",
    "ppo": "3 x slow + signal (EMA-based)",
    "obv": "1 bar (cumulative)",
    "ohlc4": "1 bar (instant)",
}


def get_warmup_description(name: str) -> str:
    """Get human-readable warmup description for an indicator."""
    if name in WARMUP_DESCRIPTIONS:
        return WARMUP_DESCRIPTIONS[name]

    # Fallback based on indicator type
    spec = SUPPORTED_INDICATORS.get(name, {})
    params = spec.get("params", set())

    if "length" in params:
        return "length bars"
    return "varies by params"


# =============================================================================
# Sample Data Generation
# =============================================================================


def generate_synthetic_price(n_bars: int = 100) -> np.ndarray:
    """Generate synthetic price data that looks realistic."""
    np.random.seed(42)  # Reproducible

    # Start price
    price = 100.0
    prices = [price]

    # Random walk with drift and mean reversion
    for _ in range(n_bars - 1):
        # Slight upward drift
        drift = 0.0002
        # Volatility
        volatility = 0.015
        # Random change
        change = drift + volatility * np.random.randn()
        # Mean reversion toward 100
        mean_reversion = -0.001 * (price - 100) / 100
        price = price * (1 + change + mean_reversion)
        prices.append(price)

    return np.array(prices)


def generate_synthetic_ohlcv(n_bars: int = 100) -> dict[str, np.ndarray]:
    """Generate synthetic OHLCV data."""
    np.random.seed(42)

    close = generate_synthetic_price(n_bars)
    high = close * (1 + np.abs(np.random.randn(n_bars) * 0.005))
    low = close * (1 - np.abs(np.random.randn(n_bars) * 0.005))
    open_ = np.roll(close, 1)
    open_[0] = close[0]

    # Ensure OHLC consistency
    high = np.maximum(high, np.maximum(open_, close))
    low = np.minimum(low, np.minimum(open_, close))

    volume = np.abs(np.random.randn(n_bars) * 1000000 + 5000000)

    return {
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def compute_ema(data: np.ndarray, length: int) -> np.ndarray:
    """Compute EMA."""
    alpha = 2.0 / (length + 1)
    result = np.zeros_like(data, dtype=float)
    result[0] = data[0]
    for i in range(1, len(data)):
        result[i] = alpha * data[i] + (1 - alpha) * result[i - 1]
    return result


def compute_sma(data: np.ndarray, length: int) -> np.ndarray:
    """Compute SMA."""
    result = np.full_like(data, np.nan, dtype=float)
    for i in range(length - 1, len(data)):
        result[i] = np.mean(data[i - length + 1 : i + 1])
    return result


def compute_rsi(data: np.ndarray, length: int = 14) -> np.ndarray:
    """Compute RSI."""
    deltas = np.diff(data)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)

    avg_gain = np.zeros(len(data))
    avg_loss = np.zeros(len(data))

    # First average
    avg_gain[length] = np.mean(gains[:length])
    avg_loss[length] = np.mean(losses[:length])

    # EMA-style smoothing
    for i in range(length + 1, len(data)):
        avg_gain[i] = (avg_gain[i - 1] * (length - 1) + gains[i - 1]) / length
        avg_loss[i] = (avg_loss[i - 1] * (length - 1) + losses[i - 1]) / length

    # Avoid division warnings
    with np.errstate(divide='ignore', invalid='ignore'):
        rs = np.where(avg_loss != 0, avg_gain / avg_loss, 100)
        rsi = 100 - (100 / (1 + rs))
    rsi[:length] = np.nan
    return rsi


def compute_atr(
    high: np.ndarray, low: np.ndarray, close: np.ndarray, length: int = 14
) -> np.ndarray:
    """Compute ATR."""
    tr = np.zeros(len(high))
    tr[0] = high[0] - low[0]
    for i in range(1, len(high)):
        tr[i] = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1]),
        )
    return compute_ema(tr, length)


def compute_macd(
    data: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9
) -> dict[str, np.ndarray]:
    """Compute MACD."""
    ema_fast = compute_ema(data, fast)
    ema_slow = compute_ema(data, slow)
    macd_line = ema_fast - ema_slow
    signal_line = compute_ema(macd_line, signal)
    histogram = macd_line - signal_line
    return {
        "macd": macd_line,
        "signal": signal_line,
        "histogram": histogram,
    }


def compute_bbands(
    data: np.ndarray, length: int = 20, std: float = 2.0
) -> dict[str, np.ndarray]:
    """Compute Bollinger Bands."""
    middle = compute_sma(data, length)
    std_dev = np.zeros_like(data, dtype=float)
    for i in range(length - 1, len(data)):
        std_dev[i] = np.std(data[i - length + 1 : i + 1])

    upper = middle + std * std_dev
    lower = middle - std * std_dev
    bandwidth = (upper - lower) / middle * 100
    percent_b = (data - lower) / (upper - lower)

    return {
        "lower": lower,
        "middle": middle,
        "upper": upper,
        "bandwidth": bandwidth,
        "percent_b": percent_b,
    }


def compute_stoch(
    high: np.ndarray, low: np.ndarray, close: np.ndarray, k: int = 14, d: int = 3
) -> dict[str, np.ndarray]:
    """Compute Stochastic."""
    stoch_k = np.zeros(len(close))
    for i in range(k - 1, len(close)):
        highest = np.max(high[i - k + 1 : i + 1])
        lowest = np.min(low[i - k + 1 : i + 1])
        if highest != lowest:
            stoch_k[i] = 100 * (close[i] - lowest) / (highest - lowest)
    stoch_d = compute_sma(stoch_k, d)
    return {"k": stoch_k, "d": stoch_d}


def compute_adx(
    high: np.ndarray, low: np.ndarray, close: np.ndarray, length: int = 14
) -> dict[str, np.ndarray]:
    """Compute ADX."""
    # True Range
    atr = compute_atr(high, low, close, length)

    # Directional Movement
    dmp = np.zeros(len(high))
    dmn = np.zeros(len(high))
    for i in range(1, len(high)):
        up = high[i] - high[i - 1]
        down = low[i - 1] - low[i]
        if up > down and up > 0:
            dmp[i] = up
        if down > up and down > 0:
            dmn[i] = down

    # Smooth DM
    smooth_dmp = compute_ema(dmp, length)
    smooth_dmn = compute_ema(dmn, length)

    # DI
    di_plus = np.where(atr != 0, 100 * smooth_dmp / atr, 0)
    di_minus = np.where(atr != 0, 100 * smooth_dmn / atr, 0)

    # DX and ADX
    dx = np.where(
        (di_plus + di_minus) != 0,
        100 * np.abs(di_plus - di_minus) / (di_plus + di_minus),
        0,
    )
    adx = compute_ema(dx, length)
    adxr = (adx + np.roll(adx, length)) / 2

    return {"adx": adx, "dmp": di_plus, "dmn": di_minus, "adxr": adxr}


def generate_sample_data(indicator_name: str) -> SampleChartData:
    """Generate sample chart data for a given indicator."""
    n_bars = 100
    ohlcv = generate_synthetic_ohlcv(n_bars)
    close = ohlcv["close"]
    high = ohlcv["high"]
    low = ohlcv["low"]

    price_data = [SampleDataPoint(x=i, y=float(close[i])) for i in range(n_bars)]

    series: dict[str, list[SampleDataPoint]] = {}

    def to_points(arr: np.ndarray) -> list[SampleDataPoint]:
        return [
            SampleDataPoint(x=i, y=float(arr[i]) if not math.isnan(arr[i]) else 0)
            for i in range(len(arr))
        ]

    # Generate indicator-specific data
    match indicator_name:
        case "ema":
            ema = compute_ema(close, 20)
            series["value"] = to_points(ema)
        case "sma":
            sma = compute_sma(close, 20)
            series["value"] = to_points(sma)
        case "rsi":
            rsi = compute_rsi(close, 14)
            series["value"] = to_points(rsi)
        case "atr":
            atr = compute_atr(high, low, close, 14)
            series["value"] = to_points(atr)
        case "macd":
            macd_data = compute_macd(close)
            for key, arr in macd_data.items():
                series[key] = to_points(arr)
        case "bbands":
            bb_data = compute_bbands(close)
            for key, arr in bb_data.items():
                series[key] = to_points(arr)
        case "stoch" | "stochrsi":
            stoch_data = compute_stoch(high, low, close)
            for key, arr in stoch_data.items():
                series[key] = to_points(arr)
        case "adx":
            adx_data = compute_adx(high, low, close)
            for key, arr in adx_data.items():
                series[key] = to_points(arr)
        case _:
            # Default: use EMA as fallback
            ema = compute_ema(close, 20)
            series["value"] = to_points(ema)

    # Include price data for trend/overlay indicators
    include_price = INDICATOR_CATEGORIES.get(indicator_name, "other") == "trend"

    return SampleChartData(
        indicator_name=indicator_name,
        series=series,
        price_data=price_data if include_price else None,
    )


# =============================================================================
# Default Parameter Values
# =============================================================================

DEFAULT_PARAMS: dict[str, dict[str, Any]] = {
    "ema": {"length": 20},
    "sma": {"length": 20},
    "rsi": {"length": 14},
    "atr": {"length": 14},
    "macd": {"fast": 12, "slow": 26, "signal": 9},
    "bbands": {"length": 20, "std": 2.0},
    "stoch": {"k": 14, "d": 3, "smooth_k": 3},
    "stochrsi": {"length": 14, "rsi_length": 14, "k": 3, "d": 3},
    "adx": {"length": 14},
    "supertrend": {"length": 10, "multiplier": 3.0},
    "psar": {"af0": 0.02, "af": 0.02, "max_af": 0.2},
    "kc": {"length": 20, "scalar": 1.5},
    "donchian": {"lower_length": 20, "upper_length": 20},
    "aroon": {"length": 25},
    "squeeze": {"bb_length": 20, "bb_std": 2.0, "kc_length": 20, "kc_scalar": 1.5},
    "cci": {"length": 20},
    "willr": {"length": 14},
    "roc": {"length": 10},
    "mom": {"length": 10},
    "kama": {"length": 10},
    "alma": {"length": 9, "sigma": 6, "offset": 0.85},
    "wma": {"length": 20},
    "dema": {"length": 20},
    "tema": {"length": 20},
    "trima": {"length": 20},
    "zlma": {"length": 20},
    "natr": {"length": 14},
    "mfi": {"length": 14},
    "cmf": {"length": 20},
    "cmo": {"length": 14},
    "linreg": {"length": 14},
    "midprice": {"length": 14},
    "trix": {"length": 18},
    "uo": {"fast": 7, "medium": 14, "slow": 28},
    "ppo": {"fast": 12, "slow": 26, "signal": 9},
    "vortex": {"length": 14},
    "dm": {"length": 14},
    "fisher": {"length": 9},
    "tsi": {"fast": 13, "slow": 25, "signal": 13},
    "kvo": {"fast": 34, "slow": 55, "signal": 13},
}


# =============================================================================
# API Endpoints
# =============================================================================


@router.get("/reference", response_model=IndicatorReferenceResponse)
async def get_indicator_reference() -> IndicatorReferenceResponse:
    """
    Get full indicator registry reference.

    Returns metadata for all 42 supported indicators including:
    - Input series requirements
    - Parameters with defaults
    - Output keys and types
    - Warmup requirements
    - Category classification
    """
    registry = get_registry()
    indicators: list[IndicatorInfo] = []
    categories: dict[str, int] = {}

    for name in registry.list_indicators():
        info = registry.get_indicator_info(name)

        # Build params list with defaults
        params: list[IndicatorParam] = []
        defaults = DEFAULT_PARAMS.get(name, {})
        for param_name in sorted(info.accepted_params):
            # Skip common params for cleaner display
            if param_name in ("offset", "talib", "mamode"):
                continue
            params.append(
                IndicatorParam(
                    name=param_name,
                    default=defaults.get(param_name),
                )
            )

        # Build outputs list with types
        outputs: list[IndicatorOutput] = []
        output_types = INDICATOR_OUTPUT_TYPES.get(name, {})

        if info.is_multi_output:
            for key in info.output_keys:
                output_type = output_types.get(key, "FLOAT")
                outputs.append(
                    IndicatorOutput(
                        key=key,
                        output_type=output_type.name
                        if hasattr(output_type, "name")
                        else str(output_type),
                    )
                )
        else:
            output_type = output_types.get("value", "FLOAT")
            outputs.append(
                IndicatorOutput(
                    key="value",
                    output_type=output_type.name
                    if hasattr(output_type, "name")
                    else str(output_type),
                )
            )

        # Get category
        category = INDICATOR_CATEGORIES.get(name, "other")
        categories[category] = categories.get(category, 0) + 1

        indicators.append(
            IndicatorInfo(
                name=name,
                is_multi_output=info.is_multi_output,
                input_series=sorted(info.input_series),
                params=params,
                output_keys=list(info.output_keys) if info.output_keys else ["value"],
                outputs=outputs,
                primary_output=info.primary_output,
                warmup_description=get_warmup_description(name),
                category=category,
            )
        )

    return IndicatorReferenceResponse(
        total=len(indicators),
        indicators=indicators,
        categories=categories,
    )


@router.get("/reference/{indicator_name}/sample", response_model=IndicatorSampleResponse)
async def get_indicator_sample(indicator_name: str) -> IndicatorSampleResponse:
    """
    Get sample chart data for a specific indicator.

    Returns synthetic data suitable for rendering a preview chart.
    """
    registry = get_registry()

    if not registry.is_supported(indicator_name):
        # Return empty sample for unsupported
        return IndicatorSampleResponse(
            indicator=IndicatorInfo(
                name=indicator_name,
                is_multi_output=False,
                input_series=[],
                params=[],
                output_keys=["value"],
                outputs=[IndicatorOutput(key="value", output_type="FLOAT")],
                primary_output=None,
                warmup_description="Unknown",
                category="other",
            ),
            sample_data=SampleChartData(
                indicator_name=indicator_name,
                series={},
                price_data=None,
            ),
        )

    info = registry.get_indicator_info(indicator_name)

    # Build indicator info
    defaults = DEFAULT_PARAMS.get(indicator_name, {})
    params = [
        IndicatorParam(name=p, default=defaults.get(p))
        for p in sorted(info.accepted_params)
        if p not in ("offset", "talib", "mamode")
    ]

    output_types = INDICATOR_OUTPUT_TYPES.get(indicator_name, {})
    outputs: list[IndicatorOutput] = []
    if info.is_multi_output:
        for key in info.output_keys:
            ot = output_types.get(key, "FLOAT")
            outputs.append(
                IndicatorOutput(
                    key=key, output_type=ot.name if hasattr(ot, "name") else str(ot)
                )
            )
    else:
        ot = output_types.get("value", "FLOAT")
        outputs.append(
            IndicatorOutput(
                key="value", output_type=ot.name if hasattr(ot, "name") else str(ot)
            )
        )

    indicator_info = IndicatorInfo(
        name=indicator_name,
        is_multi_output=info.is_multi_output,
        input_series=sorted(info.input_series),
        params=params,
        output_keys=list(info.output_keys) if info.output_keys else ["value"],
        outputs=outputs,
        primary_output=info.primary_output,
        warmup_description=get_warmup_description(indicator_name),
        category=INDICATOR_CATEGORIES.get(indicator_name, "other"),
    )

    sample_data = generate_sample_data(indicator_name)

    return IndicatorSampleResponse(
        indicator=indicator_info,
        sample_data=sample_data,
    )
