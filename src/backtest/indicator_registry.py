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
        print(info.accepted_params)
    
    # Get expanded keys for multi-output (CANONICAL API)
    keys = registry.get_expanded_keys("macd", "my_macd")
    # Returns: ["my_macd_macd", "my_macd_signal", "my_macd_histogram"]
    
    # Validate params from YAML
    registry.validate_params("ema", {"length": 20})  # OK
    registry.validate_params("ema", {"foo": 20})     # Raises ValueError

Agent Rule:
    Agents may only generate IdeaCards through `backtest idea-card-normalize`
    and must refuse to write YAML if normalization fails.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Set, Tuple, Any
from functools import lru_cache


# =============================================================================
# Supported Indicators Definition
# =============================================================================
# This is the CANONICAL list of indicators supported by indicator_vendor.
# If an indicator is not in this set, the registry will reject it even if
# it exists in pandas_ta. This prevents agents from generating unsupported
# indicator types.

SUPPORTED_INDICATORS: Dict[str, Dict[str, Any]] = {
    # -------------------------------------------------------------------------
    # Single-Output Indicators
    # -------------------------------------------------------------------------
    "ema": {
        "inputs": {"close"},
        "params": {"length"},
        "multi_output": False,
    },
    "sma": {
        "inputs": {"close"},
        "params": {"length"},
        "multi_output": False,
    },
    "rsi": {
        "inputs": {"close"},
        "params": {"length"},
        "multi_output": False,
    },
    "atr": {
        "inputs": {"high", "low", "close"},
        "params": {"length"},
        "multi_output": False,
    },
    "cci": {
        "inputs": {"high", "low", "close"},
        "params": {"length"},
        "multi_output": False,
    },
    "willr": {
        "inputs": {"high", "low", "close"},
        "params": {"length"},
        "multi_output": False,
    },
    "roc": {
        "inputs": {"close"},
        "params": {"length"},
        "multi_output": False,
    },
    "mom": {
        "inputs": {"close"},
        "params": {"length"},
        "multi_output": False,
    },
    "kama": {
        "inputs": {"close"},
        "params": {"length"},
        "multi_output": False,
    },
    "alma": {
        "inputs": {"close"},
        "params": {"length", "sigma", "offset"},
        "multi_output": False,
    },
    "wma": {
        "inputs": {"close"},
        "params": {"length"},
        "multi_output": False,
    },
    "dema": {
        "inputs": {"close"},
        "params": {"length"},
        "multi_output": False,
    },
    "tema": {
        "inputs": {"close"},
        "params": {"length"},
        "multi_output": False,
    },
    "trima": {
        "inputs": {"close"},
        "params": {"length"},
        "multi_output": False,
    },
    "zlma": {
        "inputs": {"close"},
        "params": {"length"},
        "multi_output": False,
    },
    "natr": {
        "inputs": {"high", "low", "close"},
        "params": {"length"},
        "multi_output": False,
    },
    "mfi": {
        "inputs": {"high", "low", "close", "volume"},
        "params": {"length"},
        "multi_output": False,
    },
    "obv": {
        "inputs": {"close", "volume"},
        "params": set(),
        "multi_output": False,
    },
    "cmf": {
        "inputs": {"high", "low", "close", "volume"},
        "params": {"length"},
        "multi_output": False,
    },
    "cmo": {
        "inputs": {"close"},
        "params": {"length"},
        "multi_output": False,
    },
    "linreg": {
        "inputs": {"close"},
        "params": {"length"},
        "multi_output": False,
    },
    "midprice": {
        "inputs": {"high", "low"},
        "params": {"length"},
        "multi_output": False,
    },
    "ohlc4": {
        "inputs": {"open", "high", "low", "close"},
        "params": set(),
        "multi_output": False,
    },
    "trix": {
        "inputs": {"close"},
        "params": {"length"},
        "multi_output": False,
    },
    "uo": {
        "inputs": {"high", "low", "close"},
        "params": {"fast", "medium", "slow"},
        "multi_output": False,
    },
    "ppo": {
        "inputs": {"close"},
        "params": {"fast", "slow", "signal"},
        "multi_output": False,
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
    },
    "bbands": {
        "inputs": {"close"},
        "params": {"length", "std"},
        "multi_output": True,
        "output_keys": ("lower", "mid", "upper", "bandwidth", "percent_b"),
        "primary_output": "mid",
    },
    "stoch": {
        "inputs": {"high", "low", "close"},
        "params": {"k", "d", "smooth_k"},
        "multi_output": True,
        "output_keys": ("k", "d"),
        "primary_output": "k",
    },
    "stochrsi": {
        "inputs": {"close"},
        "params": {"length", "rsi_length", "k", "d"},
        "multi_output": True,
        "output_keys": ("k", "d"),
        "primary_output": "k",
    },
    "adx": {
        "inputs": {"high", "low", "close"},
        "params": {"length"},
        "multi_output": True,
        "output_keys": ("adx", "dmp", "dmn"),
        "primary_output": "adx",
    },
    "aroon": {
        "inputs": {"high", "low"},
        "params": {"length"},
        "multi_output": True,
        "output_keys": ("up", "down", "osc"),
        "primary_output": "osc",
    },
    "kc": {
        "inputs": {"high", "low", "close"},
        "params": {"length", "scalar"},
        "multi_output": True,
        "output_keys": ("lower", "basis", "upper"),
        "primary_output": "basis",
    },
    "donchian": {
        "inputs": {"high", "low"},
        "params": {"lower_length", "upper_length"},
        "multi_output": True,
        "output_keys": ("lower", "mid", "upper"),
        "primary_output": "mid",
    },
    "supertrend": {
        "inputs": {"high", "low", "close"},
        "params": {"length", "multiplier"},
        "multi_output": True,
        "output_keys": ("trend", "direction", "long", "short"),
        "primary_output": "trend",
    },
    "psar": {
        "inputs": {"high", "low", "close"},
        "params": {"af0", "af", "max_af"},
        "multi_output": True,
        "output_keys": ("long", "short", "af", "reversal"),
        "primary_output": "long",
    },
    "squeeze": {
        "inputs": {"high", "low", "close"},
        "params": {"bb_length", "bb_std", "kc_length", "kc_scalar"},
        "multi_output": True,
        "output_keys": ("sqz", "sqz_on", "sqz_off", "no_sqz"),
        "primary_output": "sqz",
    },
    "vortex": {
        "inputs": {"high", "low", "close"},
        "params": {"length"},
        "multi_output": True,
        "output_keys": ("vip", "vim"),
        "primary_output": "vip",
    },
    "dm": {
        "inputs": {"high", "low"},
        "params": {"length"},
        "multi_output": True,
        "output_keys": ("dmp", "dmn"),
        "primary_output": "dmp",
    },
    "fisher": {
        "inputs": {"high", "low"},
        "params": {"length"},
        "multi_output": True,
        "output_keys": ("fisher", "signal"),
        "primary_output": "fisher",
    },
    "tsi": {
        "inputs": {"close"},
        "params": {"fast", "slow", "signal"},
        "multi_output": True,
        "output_keys": ("tsi", "signal"),
        "primary_output": "tsi",
    },
    "kvo": {
        "inputs": {"high", "low", "close", "volume"},
        "params": {"fast", "slow", "signal"},
        "multi_output": True,
        "output_keys": ("kvo", "signal"),
        "primary_output": "kvo",
    },
}

# Common params accepted by most indicators (added to each indicator's params)
COMMON_PARAMS = {
    "offset",       # Shift result by N periods
    "talib",        # Use TA-Lib backend if available
    "mamode",       # Moving average mode
}


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
    """
    name: str
    input_series: FrozenSet[str] = field(default_factory=frozenset)
    accepted_params: FrozenSet[str] = field(default_factory=frozenset)
    is_multi_output: bool = False
    output_keys: Tuple[str, ...] = field(default_factory=tuple)
    primary_output: Optional[str] = None
    
    @property
    def requires_hlc(self) -> bool:
        """Check if indicator requires high/low/close."""
        return {"high", "low", "close"}.issubset(self.input_series)
    
    @property
    def requires_volume(self) -> bool:
        """Check if indicator requires volume."""
        return "volume" in self.input_series


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
    
    _instance: Optional["IndicatorRegistry"] = None
    
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
        
        self._indicators: Dict[str, IndicatorInfo] = {}
        self._build_registry()
        self._initialized = True
    
    def _build_registry(self) -> None:
        """Build the indicator registry from SUPPORTED_INDICATORS."""
        for name, spec in SUPPORTED_INDICATORS.items():
            # Build accepted params (indicator-specific + common)
            accepted_params = set(spec.get("params", set()))
            accepted_params.update(COMMON_PARAMS)
            
            # Build IndicatorInfo
            info = IndicatorInfo(
                name=name,
                input_series=frozenset(spec.get("inputs", set())),
                accepted_params=frozenset(accepted_params),
                is_multi_output=spec.get("multi_output", False),
                output_keys=tuple(spec.get("output_keys", ())),
                primary_output=spec.get("primary_output"),
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
    
    def validate_params(self, name: str, params: Dict[str, Any]) -> None:
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
    
    def list_indicators(self) -> List[str]:
        """Get sorted list of all supported indicator names."""
        return sorted(self._indicators.keys())
    
    def is_multi_output(self, name: str) -> bool:
        """Check if indicator produces multiple outputs."""
        try:
            info = self.get_indicator_info(name)
            return info.is_multi_output
        except ValueError:
            return False
    
    def get_output_suffixes(self, name: str) -> Tuple[str, ...]:
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
    
    def get_primary_output(self, name: str) -> Optional[str]:
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
    
    def get_expanded_keys(self, indicator_type: str, output_key: str) -> List[str]:
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
    
    def get_input_series(self, name: str) -> Set[str]:
        """
        Get the set of input series names an indicator needs.
        
        Args:
            name: Indicator name
            
        Returns:
            Set of series names: {"close"}, {"high", "low", "close"}, etc.
        """
        info = self.get_indicator_info(name)
        return set(info.input_series)


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


def validate_indicator_params(indicator_type: str, params: Dict[str, Any]) -> None:
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


def get_expanded_keys(indicator_type: str, output_key: str) -> List[str]:
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
