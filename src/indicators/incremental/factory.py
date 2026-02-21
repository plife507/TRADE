"""
Factory function and registry integration for incremental indicators.

Provides create_incremental_indicator() to instantiate any incremental
indicator from a type string and parameter dict, plus registry query functions.
"""

from __future__ import annotations

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

    # =============================================================================
    # Core indicators
    # =============================================================================
    if indicator_type == "ema":
        return IncrementalEMA(length=params.get("length", 20))
    elif indicator_type == "sma":
        return IncrementalSMA(length=params.get("length", 20))
    elif indicator_type == "rsi":
        return IncrementalRSI(length=params.get("length", 14))
    elif indicator_type == "atr":
        return IncrementalATR(length=params.get("length", 14))
    elif indicator_type == "macd":
        return IncrementalMACD(
            fast=params.get("fast", 12),
            slow=params.get("slow", 26),
            signal=params.get("signal", 9),
        )
    elif indicator_type == "bbands":
        return IncrementalBBands(
            length=params.get("length", 20),
            std_dev=params.get("std", 2.0),
        )
    elif indicator_type == "willr":
        return IncrementalWilliamsR(length=params.get("length", 14))
    elif indicator_type == "cci":
        return IncrementalCCI(length=params.get("length", 14))
    elif indicator_type == "stoch":
        return IncrementalStochastic(
            k_period=params.get("k", 14),
            smooth_k=params.get("smooth_k", 3),
            d_period=params.get("d", 3),
        )
    elif indicator_type == "stochrsi":
        return IncrementalStochRSI(
            length=params.get("length", 14),
            rsi_length=params.get("rsi_length", 14),
            k=params.get("k", 3),
            d=params.get("d", 3),
        )
    elif indicator_type == "adx":
        return IncrementalADX(length=params.get("length", 14))
    elif indicator_type == "supertrend":
        return IncrementalSuperTrend(
            length=params.get("length", 10),
            multiplier=params.get("multiplier", 3.0),
        )
    # =============================================================================
    # Trivial indicators
    # =============================================================================
    elif indicator_type == "ohlc4":
        return IncrementalOHLC4()
    elif indicator_type == "midprice":
        return IncrementalMidprice(length=params.get("length", 14))
    elif indicator_type == "roc":
        return IncrementalROC(length=params.get("length", 10))
    elif indicator_type == "mom":
        return IncrementalMOM(length=params.get("length", 10))
    elif indicator_type == "obv":
        return IncrementalOBV()
    elif indicator_type == "natr":
        return IncrementalNATR(length=params.get("length", 14))
    # =============================================================================
    # EMA-composable indicators
    # =============================================================================
    elif indicator_type == "dema":
        return IncrementalDEMA(length=params.get("length", 20))
    elif indicator_type == "tema":
        return IncrementalTEMA(length=params.get("length", 20))
    elif indicator_type == "ppo":
        return IncrementalPPO(
            fast=params.get("fast", 12),
            slow=params.get("slow", 26),
            signal=params.get("signal", 9),
        )
    elif indicator_type == "trix":
        return IncrementalTRIX(
            length=params.get("length", 18),
            signal=params.get("signal", 9),
        )
    elif indicator_type == "tsi":
        return IncrementalTSI(
            fast=params.get("fast", 13),
            slow=params.get("slow", 25),
            signal=params.get("signal", 13),
        )
    # =============================================================================
    # SMA/Buffer-based indicators
    # =============================================================================
    elif indicator_type == "wma":
        return IncrementalWMA(length=params.get("length", 20))
    elif indicator_type == "trima":
        return IncrementalTRIMA(length=params.get("length", 20))
    elif indicator_type == "linreg":
        return IncrementalLINREG(length=params.get("length", 14))
    elif indicator_type == "cmf":
        return IncrementalCMF(length=params.get("length", 20))
    elif indicator_type == "cmo":
        return IncrementalCMO(length=params.get("length", 14))
    elif indicator_type == "mfi":
        return IncrementalMFI(length=params.get("length", 14))
    # =============================================================================
    # Lookback-based indicators
    # =============================================================================
    elif indicator_type == "aroon":
        return IncrementalAROON(length=params.get("length", 25))
    elif indicator_type == "donchian":
        return IncrementalDonchian(
            lower_length=params.get("lower_length", 20),
            upper_length=params.get("upper_length", 20),
        )
    elif indicator_type == "kc":
        return IncrementalKC(
            length=params.get("length", 20),
            scalar=params.get("scalar", 2.0),
        )
    elif indicator_type == "dm":
        return IncrementalDM(length=params.get("length", 14))
    elif indicator_type == "vortex":
        return IncrementalVortex(length=params.get("length", 14))
    # =============================================================================
    # Complex adaptive indicators
    # =============================================================================
    elif indicator_type == "kama":
        return IncrementalKAMA(
            length=params.get("length", 10),
            fast=params.get("fast", 2),
            slow=params.get("slow", 30),
        )
    elif indicator_type == "alma":
        return IncrementalALMA(
            length=params.get("length", 10),
            sigma=params.get("sigma", 6.0),
            offset=params.get("offset", 0.85),
        )
    elif indicator_type == "zlma":
        return IncrementalZLMA(length=params.get("length", 20))
    elif indicator_type == "uo":
        return IncrementalUO(
            fast=params.get("fast", 7),
            medium=params.get("medium", 14),
            slow=params.get("slow", 28),
        )
    # =============================================================================
    # Stateful multi-output indicators
    # =============================================================================
    elif indicator_type == "psar":
        return IncrementalPSAR(
            af0=params.get("af0", 0.02),
            af=params.get("af", 0.02),
            max_af=params.get("max_af", 0.2),
        )
    elif indicator_type == "squeeze":
        return IncrementalSqueeze(
            bb_length=params.get("bb_length", 20),
            bb_std=params.get("bb_std", 2.0),
            kc_length=params.get("kc_length", 20),
            kc_scalar=params.get("kc_scalar", 1.5),
            mom_length=params.get("mom_length", 12),
            mom_smooth=params.get("mom_smooth", 6),
        )
    elif indicator_type == "fisher":
        return IncrementalFisher(
            length=params.get("length", 9),
            signal=params.get("signal", 1),
        )
    # =============================================================================
    # Volume complex indicators
    # =============================================================================
    elif indicator_type == "kvo":
        return IncrementalKVO(
            fast=params.get("fast", 34),
            slow=params.get("slow", 55),
            signal=params.get("signal", 13),
        )
    elif indicator_type == "vwap":
        return IncrementalVWAP(anchor=params.get("anchor", "D"))
    elif indicator_type == "anchored_vwap":
        return IncrementalAnchoredVWAP(
            anchor_source=params.get("anchor_source", "swing_any"),
        )
    else:
        # Not supported incrementally - will fall back to vectorized
        return None


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


