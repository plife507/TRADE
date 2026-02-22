"""
Factory function and registry integration for incremental indicators.

Provides create_incremental_indicator() to instantiate any incremental
indicator from a type string and parameter dict, plus registry query functions.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .base import IncrementalIndicator
from .core import (
    IncrementalEMA,
    IncrementalSMA,
    IncrementalRSI,
    IncrementalATR,
    IncrementalMACD,
    IncrementalBBands,
    IncrementalWilliamsR,
    IncrementalCCI,
    IncrementalStochastic,
    IncrementalStochRSI,
    IncrementalADX,
    IncrementalSuperTrend,
)
from .trivial import (
    IncrementalOHLC4,
    IncrementalMidprice,
    IncrementalROC,
    IncrementalMOM,
    IncrementalOBV,
    IncrementalNATR,
)
from .ema_composable import (
    IncrementalDEMA,
    IncrementalTEMA,
    IncrementalPPO,
    IncrementalTRIX,
    IncrementalTSI,
)
from .buffer_based import (
    IncrementalWMA,
    IncrementalTRIMA,
    IncrementalLINREG,
    IncrementalCMF,
    IncrementalCMO,
    IncrementalMFI,
)
from .lookback import (
    IncrementalAROON,
    IncrementalDonchian,
    IncrementalKC,
    IncrementalDM,
    IncrementalVortex,
)
from .adaptive import (
    IncrementalKAMA,
    IncrementalALMA,
    IncrementalZLMA,
    IncrementalUO,
)
from .stateful import (
    IncrementalPSAR,
    IncrementalSqueeze,
    IncrementalFisher,
)
from .volume import (
    IncrementalKVO,
    IncrementalVWAP,
    IncrementalAnchoredVWAP,
)


# =============================================================================
# Factory for creating incremental indicators from FeatureSpec
# =============================================================================


_VALID_PARAMS: dict[str, frozenset[str]] = {
    "ema": frozenset({"length"}),
    "sma": frozenset({"length"}),
    "rsi": frozenset({"length"}),
    "atr": frozenset({"length"}),
    "macd": frozenset({"fast", "slow", "signal"}),
    "bbands": frozenset({"length", "std"}),
    "willr": frozenset({"length"}),
    "cci": frozenset({"length"}),
    "stoch": frozenset({"k", "smooth_k", "d"}),
    "stochrsi": frozenset({"length", "rsi_length", "k", "d"}),
    "adx": frozenset({"length"}),
    "supertrend": frozenset({"length", "multiplier"}),
    "ohlc4": frozenset(),
    "midprice": frozenset({"length"}),
    "roc": frozenset({"length"}),
    "mom": frozenset({"length"}),
    "obv": frozenset(),
    "natr": frozenset({"length"}),
    "dema": frozenset({"length"}),
    "tema": frozenset({"length"}),
    "ppo": frozenset({"fast", "slow", "signal"}),
    "trix": frozenset({"length", "signal"}),
    "tsi": frozenset({"fast", "slow", "signal"}),
    "wma": frozenset({"length"}),
    "trima": frozenset({"length"}),
    "linreg": frozenset({"length"}),
    "cmf": frozenset({"length"}),
    "cmo": frozenset({"length"}),
    "mfi": frozenset({"length"}),
    "aroon": frozenset({"length"}),
    "donchian": frozenset({"lower_length", "upper_length"}),
    "kc": frozenset({"length", "scalar"}),
    "dm": frozenset({"length"}),
    "vortex": frozenset({"length"}),
    "kama": frozenset({"length", "fast", "slow"}),
    "alma": frozenset({"length", "sigma", "offset"}),
    "zlma": frozenset({"length"}),
    "uo": frozenset({"fast", "medium", "slow"}),
    "psar": frozenset({"af0", "af", "max_af"}),
    "squeeze": frozenset({"bb_length", "bb_std", "kc_length", "kc_scalar", "mom_length", "mom_smooth"}),
    "fisher": frozenset({"length", "signal"}),
    "kvo": frozenset({"fast", "slow", "signal"}),
    "vwap": frozenset({"anchor"}),
    "anchored_vwap": frozenset({"anchor_source"}),
}


def _validate_params(indicator_type: str, params: dict[str, Any]) -> None:
    """Raise ValueError if params contains unknown keys for this indicator."""
    valid = _VALID_PARAMS.get(indicator_type)
    if valid is None:
        return
    unknown = set(params.keys()) - valid
    if unknown:
        raise ValueError(
            f"Unknown params for '{indicator_type}': {sorted(unknown)}. "
            f"Valid: {sorted(valid)}"
        )


# L-I1: Dict-based factory — O(1) lookup replaces 44-branch if/elif chain.
# Each entry maps indicator type string to a callable(params) -> IncrementalIndicator.
_FACTORY: dict[str, Callable[[dict[str, Any]], IncrementalIndicator]] = {
    # Core indicators
    "ema": lambda p: IncrementalEMA(length=p.get("length", 20)),
    "sma": lambda p: IncrementalSMA(length=p.get("length", 20)),
    "rsi": lambda p: IncrementalRSI(length=p.get("length", 14)),
    "atr": lambda p: IncrementalATR(length=p.get("length", 14)),
    "macd": lambda p: IncrementalMACD(fast=p.get("fast", 12), slow=p.get("slow", 26), signal=p.get("signal", 9)),
    "bbands": lambda p: IncrementalBBands(length=p.get("length", 20), std_dev=p.get("std", 2.0)),
    "willr": lambda p: IncrementalWilliamsR(length=p.get("length", 14)),
    "cci": lambda p: IncrementalCCI(length=p.get("length", 14)),
    "stoch": lambda p: IncrementalStochastic(k_period=p.get("k", 14), smooth_k=p.get("smooth_k", 3), d_period=p.get("d", 3)),
    "stochrsi": lambda p: IncrementalStochRSI(length=p.get("length", 14), rsi_length=p.get("rsi_length", 14), k=p.get("k", 3), d=p.get("d", 3)),
    "adx": lambda p: IncrementalADX(length=p.get("length", 14)),
    "supertrend": lambda p: IncrementalSuperTrend(length=p.get("length", 10), multiplier=p.get("multiplier", 3.0)),
    # Trivial indicators
    "ohlc4": lambda _: IncrementalOHLC4(),
    "midprice": lambda p: IncrementalMidprice(length=p.get("length", 14)),
    "roc": lambda p: IncrementalROC(length=p.get("length", 10)),
    "mom": lambda p: IncrementalMOM(length=p.get("length", 10)),
    "obv": lambda _: IncrementalOBV(),
    "natr": lambda p: IncrementalNATR(length=p.get("length", 14)),
    # EMA-composable indicators
    "dema": lambda p: IncrementalDEMA(length=p.get("length", 20)),
    "tema": lambda p: IncrementalTEMA(length=p.get("length", 20)),
    "ppo": lambda p: IncrementalPPO(fast=p.get("fast", 12), slow=p.get("slow", 26), signal=p.get("signal", 9)),
    "trix": lambda p: IncrementalTRIX(length=p.get("length", 18), signal=p.get("signal", 9)),
    "tsi": lambda p: IncrementalTSI(fast=p.get("fast", 13), slow=p.get("slow", 25), signal=p.get("signal", 13)),
    # Buffer-based indicators
    "wma": lambda p: IncrementalWMA(length=p.get("length", 20)),
    "trima": lambda p: IncrementalTRIMA(length=p.get("length", 20)),
    "linreg": lambda p: IncrementalLINREG(length=p.get("length", 14)),
    "cmf": lambda p: IncrementalCMF(length=p.get("length", 20)),
    "cmo": lambda p: IncrementalCMO(length=p.get("length", 14)),
    "mfi": lambda p: IncrementalMFI(length=p.get("length", 14)),
    # Lookback-based indicators
    "aroon": lambda p: IncrementalAROON(length=p.get("length", 25)),
    "donchian": lambda p: IncrementalDonchian(lower_length=p.get("lower_length", 20), upper_length=p.get("upper_length", 20)),
    "kc": lambda p: IncrementalKC(length=p.get("length", 20), scalar=p.get("scalar", 2.0)),
    "dm": lambda p: IncrementalDM(length=p.get("length", 14)),
    "vortex": lambda p: IncrementalVortex(length=p.get("length", 14)),
    # Adaptive indicators
    "kama": lambda p: IncrementalKAMA(length=p.get("length", 10), fast=p.get("fast", 2), slow=p.get("slow", 30)),
    "alma": lambda p: IncrementalALMA(length=p.get("length", 10), sigma=p.get("sigma", 6.0), offset=p.get("offset", 0.85)),
    "zlma": lambda p: IncrementalZLMA(length=p.get("length", 20)),
    "uo": lambda p: IncrementalUO(fast=p.get("fast", 7), medium=p.get("medium", 14), slow=p.get("slow", 28)),
    # Stateful multi-output indicators
    "psar": lambda p: IncrementalPSAR(af0=p.get("af0", 0.02), af=p.get("af", 0.02), max_af=p.get("max_af", 0.2)),
    "squeeze": lambda p: IncrementalSqueeze(bb_length=p.get("bb_length", 20), bb_std=p.get("bb_std", 2.0), kc_length=p.get("kc_length", 20), kc_scalar=p.get("kc_scalar", 1.5), mom_length=p.get("mom_length", 12), mom_smooth=p.get("mom_smooth", 6)),
    "fisher": lambda p: IncrementalFisher(length=p.get("length", 9), signal=p.get("signal", 1)),
    # Volume indicators
    "kvo": lambda p: IncrementalKVO(fast=p.get("fast", 34), slow=p.get("slow", 55), signal=p.get("signal", 13)),
    "vwap": lambda p: IncrementalVWAP(anchor=p.get("anchor", "D")),
    "anchored_vwap": lambda p: IncrementalAnchoredVWAP(anchor_source=p.get("anchor_source", "swing_any")),
}


def create_incremental_indicator(
    indicator_type: str,
    params: dict[str, Any],
) -> IncrementalIndicator | None:
    """
    Create an incremental indicator from type and params.

    Returns None if the indicator type is not supported incrementally.
    Raises ValueError if params contains unknown keys.
    """
    indicator_type = indicator_type.lower()
    _validate_params(indicator_type, params)

    factory_fn = _FACTORY.get(indicator_type)
    if factory_fn is None:
        return None
    return factory_fn(params)


# =============================================================================
# Registry Integration
# =============================================================================
# The canonical source of truth for incremental support is indicator_registry.py.
# These functions delegate to the registry to maintain a single source of truth.


def supports_incremental(indicator_type: str) -> bool:
    """
    Check if indicator type supports incremental computation.

    Delegates to indicator_registry for single source of truth.
    """
    from src.backtest.indicator_registry import supports_incremental as registry_supports
    return registry_supports(indicator_type)


def list_incremental_indicators() -> list[str]:
    """
    Get list of all indicators that support incremental computation.

    Delegates to indicator_registry for single source of truth.
    """
    from src.backtest.indicator_registry import list_incremental_indicators as registry_list
    return registry_list()


