"""
Indicator Registry: Single source of truth for supported indicators.

This module provides a registry that defines:
- Which indicators are SUPPORTED by our indicator_vendor (not all of pandas_ta)
- Input series requirements (close, high, low, open, volume) per indicator
- Acceptable keyword parameters per indicator
- Multi-output expansion (registry-owned, canonical API)

Key Design Decisions:
1. Registry validates against SUPPORTED_INDICATORS, NOT all of pandas_ta.
   This prevents agents from generating indicators that exist in pandas_ta
   but aren't wired in our vendor.
   
2. Multi-output expansion is REGISTRY-OWNED. The builder/validation code
   calls registry.get_expanded_keys() - this is the canonical expansion API.
   This prevents drift when outputs are added/renamed.

Usage:
    registry = get_registry()
    
    # Check if indicator is supported
    if registry.is_supported("macd"):
        info = registry.get_indicator_info("macd")
        # info.accepted_params -> {"fast": int, "slow": int, "signal": int}
    
    # Get expanded keys for multi-output (CANONICAL API)
    keys = registry.get_expanded_keys("macd", "my_macd")
    # Returns: ["my_macd_macd", "my_macd_signal", "my_macd_histogram"]
    
    # Validate params from YAML
    registry.validate_params("ema", {"length": 20})  # OK
    registry.validate_params("ema", {"foo": 20})     # Raises ValueError

Agent Rule:
    Agents may only generate Plays through `backtest play-normalize`
    and must refuse to write YAML if normalization fails.
"""

from __future__ import annotations
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from src.backtest.rules.types import FeatureOutputType


# =============================================================================
# Warmup Formula Functions
# =============================================================================
# These functions calculate the minimum bars needed for an indicator to produce
# valid values. They are stored in SUPPORTED_INDICATORS and looked up by the
# registry.

def _warmup_length(p: dict[str, Any]) -> int:
    """Default warmup: just the length parameter."""
    return p.get("length", 0)


def _warmup_ema(p: dict[str, Any]) -> int:
    """EMA needs 3x length for stabilization."""
    return p.get("length", 20) * 3


def _warmup_sma(p: dict[str, Any]) -> int:
    """SMA needs exactly length bars."""
    return p.get("length", 20)


def _warmup_rsi(p: dict[str, Any]) -> int:
    """RSI needs length + 1 for first delta."""
    return p.get("length", 14) + 1


def _warmup_atr(p: dict[str, Any]) -> int:
    """ATR needs length + 1 for previous close."""
    return p.get("length", 14) + 1


def _warmup_macd(p: dict[str, Any]) -> int:
    """MACD needs 3x slow + signal for EMA stabilization."""
    slow = p.get("slow", 26)
    signal = p.get("signal", 9)
    return slow * 3 + signal


def _warmup_bbands(p: dict[str, Any]) -> int:
    """Bollinger Bands needs same as SMA."""
    return p.get("length", 20)


def _warmup_stoch(p: dict[str, Any]) -> int:
    """Stochastic needs k + smooth_k + d."""
    k = p.get("k", 14)
    d = p.get("d", 3)
    smooth_k = p.get("smooth_k", 3)
    return k + smooth_k + d


def _warmup_stochrsi(p: dict[str, Any]) -> int:
    """StochRSI needs rsi_length + length + max(k, d)."""
    length = p.get("length", 14)
    rsi_length = p.get("rsi_length", 14)
    k = p.get("k", 3)
    d = p.get("d", 3)
    return rsi_length + length + max(k, d)


def _warmup_adx(p: dict[str, Any]) -> int:
    """ADX needs 2x length for smoothing."""
    return p.get("length", 14) * 2


def _warmup_supertrend(p: dict[str, Any]) -> int:
    """Supertrend needs ATR warmup."""
    return p.get("length", 10) + 1


def _warmup_psar(p: dict[str, Any]) -> int:
    """PSAR needs minimal warmup (2 bars for trend detection)."""
    return 2


def _warmup_squeeze(p: dict[str, Any]) -> int:
    """Squeeze needs max of BB and KC lengths."""
    bb_length = p.get("bb_length", 20)
    kc_length = p.get("kc_length", 20)
    return max(bb_length, kc_length)


def _warmup_kc(p: dict[str, Any]) -> int:
    """Keltner Channel needs EMA + ATR warmup."""
    length = p.get("length", 20)
    return length * 3 + 1  # EMA stabilization + ATR


def _warmup_donchian(p: dict[str, Any]) -> int:
    """Donchian Channel needs max of lower/upper lengths."""
    lower = p.get("lower_length", 20)
    upper = p.get("upper_length", 20)
    return max(lower, upper)


def _warmup_aroon(p: dict[str, Any]) -> int:
    """Aroon needs length + 1."""
    return p.get("length", 25) + 1


def _warmup_fisher(p: dict[str, Any]) -> int:
    """Fisher Transform needs length."""
    return p.get("length", 9)


def _warmup_tsi(p: dict[str, Any]) -> int:
    """TSI needs fast + slow + signal for double smoothing."""
    fast = p.get("fast", 13)
    slow = p.get("slow", 25)
    signal = p.get("signal", 13)
    return fast + slow + signal


def _warmup_kvo(p: dict[str, Any]) -> int:
    """KVO needs fast + slow + signal."""
    fast = p.get("fast", 34)
    slow = p.get("slow", 55)
    signal = p.get("signal", 13)
    return fast + slow + signal


def _warmup_uo(p: dict[str, Any]) -> int:
    """Ultimate Oscillator needs max of all periods."""
    fast = p.get("fast", 7)
    medium = p.get("medium", 14)
    slow = p.get("slow", 28)
    return max(fast, medium, slow)


def _warmup_ppo(p: dict[str, Any]) -> int:
    """PPO needs same as MACD (EMA-based)."""
    slow = p.get("slow", 26)
    signal = p.get("signal", 9)
    return slow * 3 + signal


def _warmup_minimal(p: dict[str, Any]) -> int:
    """Minimal warmup for cumulative/instant indicators (OBV, OHLC4)."""
    return 1


# =============================================================================
# Supported Indicators Definition
# =============================================================================
# This is the CANONICAL list of indicators supported by indicator_vendor.
# If an indicator is not in this set, the registry will reject it even if
# it exists in pandas_ta. This prevents agents from generating unsupported
# indicator types.

SUPPORTED_INDICATORS: dict[str, dict[str, Any]] = {
    # -------------------------------------------------------------------------
    # Single-Output Indicators
    # -------------------------------------------------------------------------
    "ema": {
        "inputs": {"close"},
        "params": {"length"},
        "multi_output": False,
        "warmup_formula": _warmup_ema,
    },
    "sma": {
        "inputs": {"close"},
        "params": {"length"},
        "multi_output": False,
        "warmup_formula": _warmup_sma,
    },
    "rsi": {
        "inputs": {"close"},
        "params": {"length"},
        "multi_output": False,
        "warmup_formula": _warmup_rsi,
    },
    "atr": {
        "inputs": {"high", "low", "close"},
        "params": {"length"},
        "multi_output": False,
        "warmup_formula": _warmup_atr,
    },
    "cci": {
        "inputs": {"high", "low", "close"},
        "params": {"length"},
        "multi_output": False,
        "warmup_formula": _warmup_length,
    },
    "willr": {
        "inputs": {"high", "low", "close"},
        "params": {"length"},
        "multi_output": False,
        "warmup_formula": _warmup_length,
    },
    "roc": {
        "inputs": {"close"},
        "params": {"length"},
        "multi_output": False,
        "warmup_formula": _warmup_length,
    },
    "mom": {
        "inputs": {"close"},
        "params": {"length"},
        "multi_output": False,
        "warmup_formula": _warmup_length,
    },
    "kama": {
        "inputs": {"close"},
        "params": {"length"},
        "multi_output": False,
        "warmup_formula": _warmup_ema,  # Adaptive MA, use EMA warmup
    },
    "alma": {
        "inputs": {"close"},
        "params": {"length", "sigma", "offset"},
        "multi_output": False,
        "warmup_formula": _warmup_length,
    },
    "wma": {
        "inputs": {"close"},
        "params": {"length"},
        "multi_output": False,
        "warmup_formula": _warmup_length,
    },
    "dema": {
        "inputs": {"close"},
        "params": {"length"},
        "multi_output": False,
        "warmup_formula": _warmup_ema,  # Double EMA
    },
    "tema": {
        "inputs": {"close"},
        "params": {"length"},
        "multi_output": False,
        "warmup_formula": _warmup_ema,  # Triple EMA
    },
    "trima": {
        "inputs": {"close"},
        "params": {"length"},
        "multi_output": False,
        "warmup_formula": _warmup_sma,
    },
    "zlma": {
        "inputs": {"close"},
        "params": {"length"},
        "multi_output": False,
        "warmup_formula": _warmup_ema,  # Zero-lag uses EMA
    },
    "natr": {
        "inputs": {"high", "low", "close"},
        "params": {"length"},
        "multi_output": False,
        "warmup_formula": _warmup_atr,  # Normalized ATR
    },
    "mfi": {
        "inputs": {"high", "low", "close", "volume"},
        "params": {"length"},
        "multi_output": False,
        "warmup_formula": _warmup_length,
    },
    "obv": {
        "inputs": {"close", "volume"},
        "params": set(),
        "multi_output": False,
        "warmup_formula": _warmup_minimal,
    },
    "cmf": {
        "inputs": {"high", "low", "close", "volume"},
        "params": {"length"},
        "multi_output": False,
        "warmup_formula": _warmup_length,
    },
    "cmo": {
        "inputs": {"close"},
        "params": {"length"},
        "multi_output": False,
        "warmup_formula": _warmup_length,
    },
    "linreg": {
        "inputs": {"close"},
        "params": {"length"},
        "multi_output": False,
        "warmup_formula": _warmup_length,
    },
    "midprice": {
        "inputs": {"high", "low"},
        "params": {"length"},
        "multi_output": False,
        "warmup_formula": _warmup_length,
    },
    "ohlc4": {
        "inputs": {"open", "high", "low", "close"},
        "params": set(),
        "multi_output": False,
        "warmup_formula": _warmup_minimal,
    },
    "trix": {
        "inputs": {"close"},
        "params": {"length"},
        "multi_output": False,
        "warmup_formula": _warmup_ema,  # Triple EMA-based
    },
    "uo": {
        "inputs": {"high", "low", "close"},
        "params": {"fast", "medium", "slow"},
        "multi_output": False,
        "warmup_formula": _warmup_uo,
    },
    "ppo": {
        "inputs": {"close"},
        "params": {"fast", "slow", "signal"},
        "multi_output": False,
        "warmup_formula": _warmup_ppo,
    },

    # -------------------------------------------------------------------------
    # Multi-Output Indicators
    # -------------------------------------------------------------------------
    "macd": {
        "inputs": {"close"},
        "params": {"fast", "slow", "signal"},
        "multi_output": True,
        "output_keys": ("macd", "signal", "histogram"),
        "primary_output": "macd",
        "warmup_formula": _warmup_macd,
    },
    "bbands": {
        "inputs": {"close"},
        "params": {"length", "std"},
        "multi_output": True,
        "output_keys": ("lower", "middle", "upper", "bandwidth", "percent_b"),
        "primary_output": "middle",
        "warmup_formula": _warmup_bbands,
    },
    "stoch": {
        "inputs": {"high", "low", "close"},
        "params": {"k", "d", "smooth_k"},
        "multi_output": True,
        "output_keys": ("k", "d"),
        "primary_output": "k",
        "warmup_formula": _warmup_stoch,
    },
    "stochrsi": {
        "inputs": {"close"},
        "params": {"length", "rsi_length", "k", "d"},
        "multi_output": True,
        "output_keys": ("k", "d"),
        "primary_output": "k",
        "warmup_formula": _warmup_stochrsi,
    },
    "adx": {
        "inputs": {"high", "low", "close"},
        "params": {"length"},
        "multi_output": True,
        "output_keys": ("adx", "dmp", "dmn", "adxr"),
        "primary_output": "adx",
        "warmup_formula": _warmup_adx,
    },
    "aroon": {
        "inputs": {"high", "low"},
        "params": {"length"},
        "multi_output": True,
        "output_keys": ("up", "down", "osc"),
        "primary_output": "osc",
        "warmup_formula": _warmup_aroon,
    },
    "kc": {
        "inputs": {"high", "low", "close"},
        "params": {"length", "scalar"},
        "multi_output": True,
        "output_keys": ("lower", "basis", "upper"),
        "primary_output": "basis",
        "warmup_formula": _warmup_kc,
    },
    "donchian": {
        "inputs": {"high", "low"},
        "params": {"lower_length", "upper_length"},
        "multi_output": True,
        "output_keys": ("lower", "middle", "upper"),
        "primary_output": "middle",
        "warmup_formula": _warmup_donchian,
    },
    "supertrend": {
        "inputs": {"high", "low", "close"},
        "params": {"length", "multiplier"},
        "multi_output": True,
        "output_keys": ("trend", "direction", "long", "short"),
        "primary_output": "trend",
        "warmup_formula": _warmup_supertrend,
        # long/short are mutually exclusive - only one is valid at a time
        # (long when uptrend, short when downtrend)
        "mutually_exclusive_outputs": (("long", "short"),),
    },
    "psar": {
        "inputs": {"high", "low", "close"},
        "params": {"af0", "af", "max_af"},
        "multi_output": True,
        "output_keys": ("long", "short", "af", "reversal"),
        "primary_output": "long",
        "warmup_formula": _warmup_psar,
        # long/short are mutually exclusive - only one is valid at a time
        # (long when SAR is below price, short when SAR is above price)
        "mutually_exclusive_outputs": (("long", "short"),),
    },
    "squeeze": {
        "inputs": {"high", "low", "close"},
        "params": {"bb_length", "bb_std", "kc_length", "kc_scalar"},
        "multi_output": True,
        "output_keys": ("sqz", "on", "off", "no_sqz"),
        "primary_output": "sqz",
        "warmup_formula": _warmup_squeeze,
    },
    "vortex": {
        "inputs": {"high", "low", "close"},
        "params": {"length"},
        "multi_output": True,
        "output_keys": ("vip", "vim"),
        "primary_output": "vip",
        "warmup_formula": _warmup_length,
    },
    "dm": {
        "inputs": {"high", "low"},
        "params": {"length"},
        "multi_output": True,
        "output_keys": ("dmp", "dmn"),
        "primary_output": "dmp",
        "warmup_formula": _warmup_length,
    },
    "fisher": {
        "inputs": {"high", "low"},
        "params": {"length"},
        "multi_output": True,
        "output_keys": ("fisher", "signal"),
        "primary_output": "fisher",
        "warmup_formula": _warmup_fisher,
    },
    "tsi": {
        "inputs": {"close"},
        "params": {"fast", "slow", "signal"},
        "multi_output": True,
        "output_keys": ("tsi", "signal"),
        "primary_output": "tsi",
        "warmup_formula": _warmup_tsi,
    },
    "kvo": {
        "inputs": {"high", "low", "close", "volume"},
        "params": {"fast", "slow", "signal"},
        "multi_output": True,
        "output_keys": ("kvo", "signal"),
        "primary_output": "kvo",
        "warmup_formula": _warmup_kvo,
    },
}

# Common params accepted by most indicators (added to each indicator's params)
COMMON_PARAMS = {
    "offset",       # Shift result by N periods
    "talib",        # Use TA-Lib backend if available
    "mamode",       # Moving average mode
}


# =============================================================================
# Indicator Output Types
# =============================================================================
# Maps each indicator to its output types for compile-time type validation.
# Used by DSL to validate operator compatibility (eq only for discrete types,
# near_* only for numeric types).
#
# Single-output indicators: {"value": FeatureOutputType}
# Multi-output indicators: {suffix: FeatureOutputType for each output}

INDICATOR_OUTPUT_TYPES: dict[str, dict[str, FeatureOutputType]] = {
    # -------------------------------------------------------------------------
    # Single-Output Indicators (all FLOAT)
    # -------------------------------------------------------------------------
    "ema": {"value": FeatureOutputType.FLOAT},
    "sma": {"value": FeatureOutputType.FLOAT},
    "rsi": {"value": FeatureOutputType.FLOAT},
    "atr": {"value": FeatureOutputType.FLOAT},
    "cci": {"value": FeatureOutputType.FLOAT},
    "willr": {"value": FeatureOutputType.FLOAT},
    "roc": {"value": FeatureOutputType.FLOAT},
    "mom": {"value": FeatureOutputType.FLOAT},
    "kama": {"value": FeatureOutputType.FLOAT},
    "alma": {"value": FeatureOutputType.FLOAT},
    "wma": {"value": FeatureOutputType.FLOAT},
    "dema": {"value": FeatureOutputType.FLOAT},
    "tema": {"value": FeatureOutputType.FLOAT},
    "trima": {"value": FeatureOutputType.FLOAT},
    "zlma": {"value": FeatureOutputType.FLOAT},
    "natr": {"value": FeatureOutputType.FLOAT},
    "mfi": {"value": FeatureOutputType.FLOAT},
    "obv": {"value": FeatureOutputType.FLOAT},
    "cmf": {"value": FeatureOutputType.FLOAT},
    "cmo": {"value": FeatureOutputType.FLOAT},
    "linreg": {"value": FeatureOutputType.FLOAT},
    "midprice": {"value": FeatureOutputType.FLOAT},
    "ohlc4": {"value": FeatureOutputType.FLOAT},
    "trix": {"value": FeatureOutputType.FLOAT},
    "uo": {"value": FeatureOutputType.FLOAT},
    "ppo": {"value": FeatureOutputType.FLOAT},

    # -------------------------------------------------------------------------
    # Multi-Output Indicators
    # -------------------------------------------------------------------------
    "macd": {
        "macd": FeatureOutputType.FLOAT,
        "signal": FeatureOutputType.FLOAT,
        "histogram": FeatureOutputType.FLOAT,
    },
    "bbands": {
        "lower": FeatureOutputType.FLOAT,
        "middle": FeatureOutputType.FLOAT,
        "upper": FeatureOutputType.FLOAT,
        "bandwidth": FeatureOutputType.FLOAT,
        "percent_b": FeatureOutputType.FLOAT,
    },
    "stoch": {
        "k": FeatureOutputType.FLOAT,
        "d": FeatureOutputType.FLOAT,
    },
    "stochrsi": {
        "k": FeatureOutputType.FLOAT,
        "d": FeatureOutputType.FLOAT,
    },
    "adx": {
        "adx": FeatureOutputType.FLOAT,
        "dmp": FeatureOutputType.FLOAT,
        "dmn": FeatureOutputType.FLOAT,
        "adxr": FeatureOutputType.FLOAT,
    },
    "aroon": {
        "up": FeatureOutputType.FLOAT,
        "down": FeatureOutputType.FLOAT,
        "osc": FeatureOutputType.FLOAT,
    },
    "kc": {
        "lower": FeatureOutputType.FLOAT,
        "basis": FeatureOutputType.FLOAT,
        "upper": FeatureOutputType.FLOAT,
    },
    "donchian": {
        "lower": FeatureOutputType.FLOAT,
        "middle": FeatureOutputType.FLOAT,
        "upper": FeatureOutputType.FLOAT,
    },
    "supertrend": {
        "trend": FeatureOutputType.FLOAT,      # Price level
        "direction": FeatureOutputType.INT,     # 1 (up) or -1 (down)
        "long": FeatureOutputType.FLOAT,        # Long stop level (NaN when short)
        "short": FeatureOutputType.FLOAT,       # Short stop level (NaN when long)
    },
    "psar": {
        "long": FeatureOutputType.FLOAT,        # Long SAR level (NaN when short)
        "short": FeatureOutputType.FLOAT,       # Short SAR level (NaN when long)
        "af": FeatureOutputType.FLOAT,          # Acceleration factor
        "reversal": FeatureOutputType.INT,      # 1 when reversal occurs, 0 otherwise
    },
    "squeeze": {
        "sqz": FeatureOutputType.FLOAT,         # Momentum value
        "on": FeatureOutputType.BOOL,           # Squeeze is on (inside KC)
        "off": FeatureOutputType.BOOL,          # Squeeze is off (outside KC)
        "no_sqz": FeatureOutputType.BOOL,       # No squeeze (neutral)
    },
    "vortex": {
        "vip": FeatureOutputType.FLOAT,         # VI+
        "vim": FeatureOutputType.FLOAT,         # VI-
    },
    "dm": {
        "dmp": FeatureOutputType.FLOAT,         # DM+
        "dmn": FeatureOutputType.FLOAT,         # DM-
    },
    "fisher": {
        "fisher": FeatureOutputType.FLOAT,
        "signal": FeatureOutputType.FLOAT,
    },
    "tsi": {
        "tsi": FeatureOutputType.FLOAT,
        "signal": FeatureOutputType.FLOAT,
    },
    "kvo": {
        "kvo": FeatureOutputType.FLOAT,
        "signal": FeatureOutputType.FLOAT,
    },
}


# =============================================================================
# Indicator Entry Schema
# =============================================================================
# Each indicator in SUPPORTED_INDICATORS may have the following fields:
#
# Required:
#   - inputs: Set[str]          - Required input series (close, high, low, volume, etc.)
#   - params: Set[str]          - Accepted keyword parameters
#   - multi_output: bool        - Whether indicator produces multiple outputs
#
# Optional (for multi-output):
#   - output_keys: Tuple[str]   - Output suffix names (required if multi_output=True)
#   - primary_output: str       - Default output suffix for references
#
# Optional (Phase 0 additions):
#   - warmup_formula: Callable[[Dict], int]  - Function to calculate warmup bars from params
#                                               Default: _warmup_length
#   - sparse: bool              - Whether outputs are sparse (need forward-fill)
#                                 Default: False
#   - compute_fn: str | None    - Custom compute function name for non-pandas_ta indicators
#                                 Default: None (uses pandas_ta)
#
# NOTE: Current indicators all use pandas_ta and are not sparse.
# The sparse and compute_fn fields enable future market structure indicators.


# =============================================================================
# Data Structures
# =============================================================================

@dataclass(frozen=True)
class IndicatorInfo:
    """
    Metadata about a supported indicator.

    Attributes:
        name: Indicator function name (e.g., "ema", "macd")
        input_series: Set of required input series names
        accepted_params: Set of keyword parameter names the function accepts
        is_multi_output: Whether this indicator returns multiple outputs
        output_keys: For multi-output, the canonical output suffixes
        primary_output: For multi-output, the default/primary output suffix
        warmup_formula: Function to calculate warmup bars from params dict
        sparse: Whether outputs are sparse and need forward-fill
        compute_fn: Custom compute function name (None = use pandas_ta)
        mutually_exclusive_outputs: Groups of outputs where only one can be valid
            at a time. E.g., SuperTrend's (("long", "short"),) means st_long and
            st_short are mutually exclusive - when one has a value, the other is NaN.
    """
    name: str
    input_series: frozenset[str] = field(default_factory=frozenset)
    accepted_params: frozenset[str] = field(default_factory=frozenset)
    is_multi_output: bool = False
    output_keys: tuple[str, ...] = field(default_factory=tuple)
    primary_output: str | None = None
    # Phase 0 additions for registry consolidation
    warmup_formula: Callable[[dict[str, Any]], int] | None = None
    sparse: bool = False
    compute_fn: str | None = None
    # Mutually exclusive output groups - tuple of tuples of suffix names
    # E.g., (("long", "short"),) means long and short are mutually exclusive
    mutually_exclusive_outputs: tuple[tuple[str, ...], ...] = field(default_factory=tuple)

    @property
    def requires_hlc(self) -> bool:
        """Check if indicator requires high/low/close."""
        return {"high", "low", "close"}.issubset(self.input_series)

    @property
    def requires_volume(self) -> bool:
        """Check if indicator requires volume."""
        return "volume" in self.input_series

    def is_output_in_exclusive_group(self, suffix: str) -> bool:
        """Check if an output suffix is part of a mutually exclusive group."""
        for group in self.mutually_exclusive_outputs:
            if suffix in group:
                return True
        return False

    def get_exclusive_group_for_output(self, suffix: str) -> tuple[str, ...] | None:
        """Get the mutually exclusive group containing this output suffix."""
        for group in self.mutually_exclusive_outputs:
            if suffix in group:
                return group
        return None


# =============================================================================
# Registry Implementation
# =============================================================================

class IndicatorRegistry:
    """
    Registry for supported indicators.
    
    The registry is the SINGLE SOURCE OF TRUTH for:
    - Which indicators are supported (defined in SUPPORTED_INDICATORS)
    - What inputs/params each indicator accepts
    - Multi-output expansion (get_expanded_keys is the canonical API)
    
    Design: We do NOT validate against all of pandas_ta. We only support
    indicators explicitly defined in SUPPORTED_INDICATORS. This prevents
    agents from generating indicators that exist in pandas_ta but aren't
    wired in our vendor.
    """
    
    _instance: "IndicatorRegistry | None" = None
    
    def __new__(cls) -> "IndicatorRegistry":
        """Singleton pattern for registry."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize registry (only once due to singleton)."""
        if self._initialized:
            return
        
        self._indicators: dict[str, IndicatorInfo] = {}
        self._build_registry()
        self._initialized = True
    
    def _build_registry(self) -> None:
        """Build the indicator registry from SUPPORTED_INDICATORS."""
        for name, spec in SUPPORTED_INDICATORS.items():
            # Build accepted params (indicator-specific + common)
            accepted_params = set(spec.get("params", set()))
            accepted_params.update(COMMON_PARAMS)

            # Build IndicatorInfo with all fields including Phase 0 additions
            # Convert mutually_exclusive_outputs to tuple of tuples
            exclusive_outputs = spec.get("mutually_exclusive_outputs", ())
            if exclusive_outputs:
                exclusive_outputs = tuple(tuple(g) for g in exclusive_outputs)

            info = IndicatorInfo(
                name=name,
                input_series=frozenset(spec.get("inputs", set())),
                accepted_params=frozenset(accepted_params),
                is_multi_output=spec.get("multi_output", False),
                output_keys=tuple(spec.get("output_keys", ())),
                primary_output=spec.get("primary_output"),
                # Phase 0 additions
                warmup_formula=spec.get("warmup_formula", _warmup_length),
                sparse=spec.get("sparse", False),
                compute_fn=spec.get("compute_fn"),
                # Mutually exclusive outputs (e.g., SuperTrend long/short)
                mutually_exclusive_outputs=exclusive_outputs,
            )
            self._indicators[name] = info
    
    # =========================================================================
    # Public API
    # =========================================================================
    
    def is_supported(self, name: str) -> bool:
        """Check if an indicator is supported."""
        return name.lower() in self._indicators
    
    def get_indicator_info(self, name: str) -> IndicatorInfo:
        """
        Get metadata for an indicator.
        
        Args:
            name: Indicator name (case-insensitive)
            
        Returns:
            IndicatorInfo with metadata
            
        Raises:
            ValueError: If indicator not supported
        """
        name_lower = name.lower()
        if name_lower not in self._indicators:
            available = self.list_indicators()
            raise ValueError(
                f"Unsupported indicator: '{name}'. "
                f"Supported indicators: {available}"
            )
        return self._indicators[name_lower]
    
    def validate_params(self, name: str, params: dict[str, Any]) -> None:
        """
        Validate that all params are accepted by the indicator.
        
        Args:
            name: Indicator name
            params: Dict of parameter name -> value
            
        Raises:
            ValueError: If indicator not supported or param not accepted
        """
        info = self.get_indicator_info(name)
        
        for param_name in params.keys():
            if param_name not in info.accepted_params:
                raise ValueError(
                    f"Indicator '{name}' does not accept parameter '{param_name}'. "
                    f"Accepted parameters: {sorted(info.accepted_params)}"
                )
    
    def list_indicators(self) -> list[str]:
        """Get sorted list of all supported indicator names."""
        return sorted(self._indicators.keys())
    
    def is_multi_output(self, name: str) -> bool:
        """Check if indicator produces multiple outputs."""
        try:
            info = self.get_indicator_info(name)
            return info.is_multi_output
        except ValueError:
            return False
    
    def get_output_suffixes(self, name: str) -> tuple[str, ...]:
        """
        Get canonical output suffixes for a multi-output indicator.
        
        Args:
            name: Indicator name
            
        Returns:
            Tuple of output suffixes (empty for single-output)
        """
        try:
            info = self.get_indicator_info(name)
            return info.output_keys
        except ValueError:
            return ()
    
    def get_primary_output(self, name: str) -> str | None:
        """
        Get the primary output suffix for a multi-output indicator.
        
        Used when someone references a base key (e.g., "macd") to suggest
        the primary expanded key (e.g., "macd_macd").
        
        Args:
            name: Indicator name
            
        Returns:
            Primary output suffix, or None for single-output
        """
        try:
            info = self.get_indicator_info(name)
            return info.primary_output
        except ValueError:
            return None
    
    def get_expanded_keys(self, indicator_type: str, output_key: str) -> list[str]:
        """
        Get the expanded output keys for an indicator.
        
        This is the CANONICAL API for multi-output expansion. All code that
        needs to know what keys a feature_spec will produce should call this.
        
        For single-output indicators: returns [output_key]
        For multi-output indicators: returns [output_key + "_" + suffix for each suffix]
        
        Args:
            indicator_type: Indicator type name (e.g., "macd")
            output_key: The base output_key from FeatureSpec
            
        Returns:
            List of all output keys this indicator will produce
            
        Raises:
            ValueError: If indicator not supported
        """
        info = self.get_indicator_info(indicator_type)
        
        if not info.is_multi_output:
            # Single output - just the output_key
            return [output_key]
        
        # Multi-output - expand with suffixes
        return [f"{output_key}_{suffix}" for suffix in info.output_keys]
    
    def get_input_series(self, name: str) -> set[str]:
        """
        Get the set of input series names an indicator needs.

        Args:
            name: Indicator name

        Returns:
            Set of series names: {"close"}, {"high", "low", "close"}, etc.
        """
        info = self.get_indicator_info(name)
        return set(info.input_series)

    # =========================================================================
    # Phase 0 Additions: Warmup and Sparse Support
    # =========================================================================

    def get_warmup_bars(self, indicator_type: str, params: dict[str, Any]) -> int:
        """
        Calculate warmup bars needed for an indicator with given params.

        This is the CANONICAL API for warmup calculation. Uses the warmup_formula
        stored in the registry to compute the minimum bars needed.

        Args:
            indicator_type: Indicator type name (e.g., "ema", "macd")
            params: Dict of parameter values (e.g., {"length": 20})

        Returns:
            Number of warmup bars needed

        Raises:
            ValueError: If indicator not supported
        """
        info = self.get_indicator_info(indicator_type)
        if info.warmup_formula:
            return info.warmup_formula(params)
        # Fallback: use length param if no formula defined
        return params.get("length", 0)

    def is_sparse(self, name: str) -> bool:
        """
        Check if indicator outputs are sparse (need forward-fill).

        Sparse indicators produce values only at certain bars (e.g., swing
        detection produces values only when a swing is confirmed). Between
        output bars, the values need to be forward-filled.

        Args:
            name: Indicator name

        Returns:
            True if indicator outputs are sparse
        """
        try:
            info = self.get_indicator_info(name)
            return info.sparse
        except ValueError:
            return False

    def get_compute_fn(self, name: str) -> str | None:
        """
        Get the custom compute function name for an indicator.

        For pandas_ta indicators, returns None.
        For custom indicators (e.g., market structure), returns the function name.

        Args:
            name: Indicator name

        Returns:
            Function name string, or None for pandas_ta indicators
        """
        try:
            info = self.get_indicator_info(name)
            return info.compute_fn
        except ValueError:
            return None

    def get_output_type(
        self, indicator_type: str, field: str = "value"
    ) -> FeatureOutputType:
        """
        Get the output type for an indicator field.

        Used by DSL to validate operator compatibility at Play load time:
        - eq operator only allowed on discrete types (INT, BOOL, ENUM)
        - near_abs/near_pct only allowed on numeric types (FLOAT, INT)

        Args:
            indicator_type: Indicator type name (e.g., "ema", "macd")
            field: Output field name. For single-output indicators, use "value".
                   For multi-output indicators, use the suffix (e.g., "macd", "signal").

        Returns:
            FeatureOutputType for the field

        Raises:
            ValueError: If indicator not supported or field not found
        """
        name_lower = indicator_type.lower()
        if name_lower not in INDICATOR_OUTPUT_TYPES:
            raise ValueError(
                f"No output types defined for indicator: '{indicator_type}'"
            )

        type_map = INDICATOR_OUTPUT_TYPES[name_lower]
        if field not in type_map:
            raise ValueError(
                f"Unknown field '{field}' for indicator '{indicator_type}'. "
                f"Available fields: {list(type_map.keys())}"
            )

        return type_map[field]

    def get_mutually_exclusive_groups(
        self, column_names: list[str]
    ) -> list[set[str]]:
        """
        Identify mutually exclusive column groups from a list of column names.

        For indicators like SuperTrend (st_long, st_short) or PSAR (psar_long, psar_short),
        the long/short outputs are mutually exclusive - only one has a value at any bar.
        This method finds such groups in a list of column names.

        Args:
            column_names: List of indicator column names (e.g., ["st_long", "st_short", "ema_21"])

        Returns:
            List of sets, where each set contains column names that are mutually exclusive.
            E.g., [{"st_long", "st_short"}, {"psar_long", "psar_short"}]
        """
        groups: list[set[str]] = []
        processed: set[str] = set()

        for col in column_names:
            if col in processed:
                continue

            # Try to match column to an indicator with mutually exclusive outputs
            # Column format is usually: {output_key}_{suffix} for multi-output
            for indicator_name, info in self._indicators.items():
                if not info.mutually_exclusive_outputs:
                    continue

                # Check each exclusive group in this indicator
                for exclusive_group in info.mutually_exclusive_outputs:
                    # Try to find the base output_key by matching suffixes
                    # E.g., if col="st_long" and suffix="long", base="st"
                    for suffix in exclusive_group:
                        if col.endswith(f"_{suffix}"):
                            base_key = col[: -(len(suffix) + 1)]  # Remove _suffix

                            # Build the full set of exclusive columns with this base
                            exclusive_cols = set()
                            for s in exclusive_group:
                                full_col = f"{base_key}_{s}"
                                if full_col in column_names:
                                    exclusive_cols.add(full_col)

                            # Only add if we found more than one column
                            if len(exclusive_cols) > 1:
                                groups.append(exclusive_cols)
                                processed.update(exclusive_cols)
                            break
                    if col in processed:
                        break
                if col in processed:
                    break

        return groups


# =============================================================================
# Module-Level Convenience Functions
# =============================================================================

@lru_cache(maxsize=1)
def get_registry() -> IndicatorRegistry:
    """Get the singleton indicator registry."""
    return IndicatorRegistry()


def validate_indicator_type(indicator_type: str) -> bool:
    """
    Validate that an indicator type is supported.
    
    Args:
        indicator_type: Indicator name (e.g., "ema", "macd")
        
    Returns:
        True if valid
        
    Raises:
        ValueError: If indicator not supported
    """
    registry = get_registry()
    if not registry.is_supported(indicator_type):
        raise ValueError(
            f"Unsupported indicator type: '{indicator_type}'. "
            f"Supported indicators: {registry.list_indicators()}"
        )
    return True


def validate_indicator_params(indicator_type: str, params: dict[str, Any]) -> None:
    """
    Validate that params are accepted by the indicator.
    
    Args:
        indicator_type: Indicator name
        params: Dict of parameter name -> value
        
    Raises:
        ValueError: If indicator not supported or param not accepted
    """
    registry = get_registry()
    registry.validate_params(indicator_type, params)


def get_expanded_keys(indicator_type: str, output_key: str) -> list[str]:
    """
    Get the expanded output keys for an indicator (canonical API).

    Args:
        indicator_type: Indicator type name (e.g., "macd")
        output_key: The base output_key from FeatureSpec

    Returns:
        List of all output keys this indicator will produce
    """
    registry = get_registry()
    return registry.get_expanded_keys(indicator_type, output_key)


def get_warmup_bars(indicator_type: str, params: dict[str, Any]) -> int:
    """
    Calculate warmup bars needed for an indicator with given params.

    Args:
        indicator_type: Indicator type name (e.g., "ema", "macd")
        params: Dict of parameter values (e.g., {"length": 20})

    Returns:
        Number of warmup bars needed
    """
    registry = get_registry()
    return registry.get_warmup_bars(indicator_type, params)


def get_indicator_output_type(
    indicator_type: str, field: str = "value"
) -> FeatureOutputType:
    """
    Get the output type for an indicator field.

    Used by DSL to validate operator compatibility at Play load time.

    Args:
        indicator_type: Indicator type name (e.g., "ema", "macd")
        field: Output field name. For single-output indicators, use "value".
               For multi-output indicators, use the suffix (e.g., "macd", "signal").

    Returns:
        FeatureOutputType for the field
    """
    registry = get_registry()
    return registry.get_output_type(indicator_type, field)
