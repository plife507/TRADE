"""
FeatureSpec: Declarative indicator specification.

Provides a declarative way to specify indicators that strategies need.
Each FeatureSpec defines:
- indicator_type: What indicator to compute (EMA, RSI, ATR, MACD, etc.)
- input_source: What data to use as input (close, high, low, or another indicator)
- params: Parameters for the indicator (length, etc.)
- output_key: Name prefix for outputs (multi-output indicators append suffixes)
- outputs: For multi-output indicators, mapping of output names to keys

Design principles:
- Immutable specs (frozen dataclasses)
- Vectorized computation via FeatureFrameBuilder
- Compatible with FeedStore arrays (float32 preferred)
- Decoupled from strategy logic
- Proper warmup calculations per indicator type

Registry Consolidation (2025-12-31):
- indicator_type is a STRING validated against IndicatorRegistry
- Warmup calculation uses registry.get_warmup_bars()
- Multi-output keys use registry.get_output_suffixes()
- IndicatorType enum has been REMOVED (deprecated code deleted)
- All metadata now lives in SUPPORTED_INDICATORS dict in registry.py
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


def is_multi_output(indicator_type: str) -> bool:
    """
    Check if indicator type produces multiple outputs.

    Uses IndicatorRegistry as single source of truth.

    Args:
        indicator_type: Indicator type string (e.g., "ema", "macd")

    Returns:
        True if indicator produces multiple outputs
    """
    from .registry import get_registry
    return get_registry().is_multi_output(indicator_type.lower())


def get_output_names(indicator_type: str) -> tuple[str, ...]:
    """
    Get output names for an indicator type.

    Uses IndicatorRegistry as single source of truth.

    Args:
        indicator_type: Indicator type string (e.g., "macd", "bbands")

    Returns:
        Tuple of output suffixes, empty tuple for single-output indicators
    """
    from .registry import get_registry
    return get_registry().get_output_suffixes(indicator_type.lower())


class InputSource(str, Enum):
    """
    Data sources for indicator computation.

    OHLCV: Use the named price column directly
    INDICATOR: Use another indicator's output as input (for chained indicators)
    """
    OPEN = "open"
    HIGH = "high"
    LOW = "low"
    CLOSE = "close"
    VOLUME = "volume"
    # HLC3, OHLC4 computed from multiple columns
    HLC3 = "hlc3"      # (high + low + close) / 3
    OHLC4 = "ohlc4"    # (open + high + low + close) / 4
    # Reference another indicator output
    INDICATOR = "indicator"


@dataclass(frozen=True)
class FeatureSpec:
    """
    Specification for a single indicator/feature.

    Attributes:
        indicator_type: Type of indicator to compute (string, e.g., "ema", "macd")
        output_key: Name of the output in FeedStore (for single-output) or prefix (for multi-output)
        params: Parameters for the indicator (e.g., {"length": 20})
        input_source: Data source for the indicator (default: close)
        input_indicator_key: If input_source=INDICATOR, the key of that indicator
        outputs: For multi-output indicators, mapping of standard name -> custom key
                 e.g., {"macd": "macd_12_26_9", "signal": "macd_signal"}
        description: Optional human-readable description

    Examples:
        # EMA 20 on close (single output)
        FeatureSpec(
            indicator_type="ema",
            output_key="ema_20",
            params={"length": 20},
            input_source=InputSource.CLOSE,
        )

        # MACD with custom output keys (multi-output)
        FeatureSpec(
            indicator_type="macd",
            output_key="macd",  # prefix
            params={"fast": 12, "slow": 26, "signal": 9},
            outputs={"macd": "macd_line", "signal": "macd_signal", "histogram": "macd_hist"},
        )

        # Bollinger Bands (multi-output with default keys)
        FeatureSpec(
            indicator_type="bbands",
            output_key="bb",  # will generate bb_upper, bb_middle, bb_lower, etc.
            params={"length": 20, "std": 2.0},
        )
    """
    indicator_type: str
    output_key: str
    params: dict[str, Any] = field(default_factory=dict)
    input_source: InputSource = InputSource.CLOSE
    input_indicator_key: str | None = None
    outputs: dict[str, str] | None = None
    description: str | None = None

    def __post_init__(self):
        """Validate spec."""
        if not self.output_key:
            raise ValueError("output_key is required")

        # Normalize indicator type to lowercase string
        ind_type_str = self.indicator_type.lower()

        # Validate against registry (fail-fast for unsupported types)
        from .registry import get_registry
        registry = get_registry()
        if not registry.is_supported(ind_type_str):
            raise ValueError(
                f"Unsupported indicator type: '{ind_type_str}'. "
                f"Supported: {registry.list_indicators()}"
            )

        # Validate indicator-specific requirements
        if ind_type_str == "atr":
            # ATR always uses HLC internally, input_source is ignored
            pass
        elif ind_type_str in ("stoch", "bbands"):
            # These always use HLC/HLCV internally
            pass
        elif self.input_source == InputSource.INDICATOR:
            if not self.input_indicator_key:
                raise ValueError(
                    "input_indicator_key required when input_source=INDICATOR"
                )

        # Validate multi-output mapping if provided
        if self.outputs is not None and is_multi_output(ind_type_str):
            valid_outputs = set(get_output_names(ind_type_str))
            for key in self.outputs.keys():
                if key not in valid_outputs:
                    raise ValueError(
                        f"Invalid output '{key}' for {ind_type_str}. "
                        f"Valid outputs: {valid_outputs}"
                    )

    @property
    def is_multi_output(self) -> bool:
        """Check if this spec produces multiple outputs."""
        return is_multi_output(self.indicator_type)

    @property
    def output_keys_list(self) -> list[str]:
        """
        Get all output keys this spec will produce.

        For single-output indicators, returns [output_key].
        For multi-output indicators, returns all output keys.
        """
        if not self.is_multi_output:
            return [self.output_key]

        output_names = get_output_names(self.indicator_type)
        if self.outputs:
            # Use custom mapping
            return [self.outputs.get(name, f"{self.output_key}_{name}") for name in output_names]
        else:
            # Use prefix_suffix pattern
            return [f"{self.output_key}_{name}" for name in output_names]

    def get_output_key(self, output_name: str) -> str:
        """
        Get the output key for a specific output name.

        Args:
            output_name: Standard output name (e.g., "macd", "signal")

        Returns:
            The key to use in FeedStore
        """
        if not self.is_multi_output:
            return self.output_key

        if self.outputs and output_name in self.outputs:
            return self.outputs[output_name]
        return f"{self.output_key}_{output_name}"

    @property
    def length(self) -> int:
        """Get the length/period parameter (most indicators use this)."""
        return self.params.get("length", 0)

    @property
    def warmup_bars(self) -> int:
        """
        Minimum bars needed for this indicator to produce valid values.

        Uses IndicatorRegistry as single source of truth for warmup formulas.
        Each indicator's warmup_formula is a function that takes params dict
        and returns the required warmup bars.

        Examples:
        - EMA: 3x length for stabilization
        - SMA: length
        - RSI: length + 1
        - ATR: length + 1
        - MACD: 3x slow + signal
        - BBANDS: length
        - STOCH: k + smooth_k + d
        - STOCHRSI: rsi_length + length + max(k, d)
        """
        from .registry import get_registry

        # Use registry as single source of truth for warmup calculation
        registry = get_registry()
        return registry.get_warmup_bars(self.indicator_type.lower(), self.params)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "indicator_type": self.indicator_type.lower(),
            "output_key": self.output_key,
            "params": self.params,
            "input_source": self.input_source.value,
            "input_indicator_key": self.input_indicator_key,
            "outputs": self.outputs,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "FeatureSpec":
        """
        Create from dict.

        Accepts indicator_type as string. Validation happens in __post_init__.
        """
        return cls(
            indicator_type=d["indicator_type"],
            output_key=d["output_key"],
            params=d.get("params", {}),
            input_source=InputSource(d.get("input_source", "close")),
            input_indicator_key=d.get("input_indicator_key"),
            outputs=d.get("outputs"),
            description=d.get("description"),
        )


@dataclass
class FeatureSpecSet:
    """
    Collection of FeatureSpecs for a single (symbol, tf) pair.

    Manages dependency ordering for chained indicators and provides
    validation that all required inputs are available.

    Attributes:
        symbol: Trading symbol
        tf: Timeframe string
        specs: List of FeatureSpecs (order matters for dependencies)
    """
    symbol: str
    tf: str
    specs: list[FeatureSpec] = field(default_factory=list)

    def __post_init__(self):
        """Validate specs."""
        self._validate_unique_keys()
        self._validate_dependencies()

    def _validate_unique_keys(self):
        """Ensure all output_keys are unique (including multi-output expansion)."""
        all_keys = []
        for spec in self.specs:
            all_keys.extend(spec.output_keys_list)

        if len(all_keys) != len(set(all_keys)):
            duplicates = [k for k in all_keys if all_keys.count(k) > 1]
            raise ValueError(f"Duplicate output_keys: {set(duplicates)}")

    def _validate_dependencies(self):
        """
        Ensure indicator dependencies are satisfied.

        An indicator with input_source=INDICATOR must reference
        an output_key that appears earlier in the specs list.
        """
        available_keys = set()
        for spec in self.specs:
            if spec.input_source == InputSource.INDICATOR:
                if spec.input_indicator_key not in available_keys:
                    raise ValueError(
                        f"Indicator '{spec.output_key}' depends on "
                        f"'{spec.input_indicator_key}' which is not defined earlier"
                    )
            # Add all output keys from this spec
            available_keys.update(spec.output_keys_list)

    def add(self, spec: FeatureSpec):
        """Add a spec to the set (validates dependencies)."""
        # Check for duplicate keys (including multi-output)
        existing_keys = set()
        for s in self.specs:
            existing_keys.update(s.output_keys_list)

        for key in spec.output_keys_list:
            if key in existing_keys:
                raise ValueError(f"Duplicate output_key: {key}")

        # Check dependency
        if spec.input_source == InputSource.INDICATOR:
            if spec.input_indicator_key not in existing_keys:
                raise ValueError(
                    f"Indicator '{spec.output_key}' depends on "
                    f"'{spec.input_indicator_key}' which is not defined"
                )

        self.specs.append(spec)

    @property
    def output_keys(self) -> list[str]:
        """Get all output keys (including multi-output expansion)."""
        keys = []
        for spec in self.specs:
            keys.extend(spec.output_keys_list)
        return keys

    @property
    def max_warmup_bars(self) -> int:
        """Get maximum warmup bars needed across all specs."""
        if not self.specs:
            return 0
        return max(s.warmup_bars for s in self.specs)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "symbol": self.symbol,
            "tf": self.tf,
            "specs": [s.to_dict() for s in self.specs],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "FeatureSpecSet":
        """Create from dict."""
        specs = [FeatureSpec.from_dict(s) for s in d.get("specs", [])]
        return cls(
            symbol=d["symbol"],
            tf=d["tf"],
            specs=specs,
        )


# ============================================================================
# Factory functions for common indicator specs
# ============================================================================

def ema_spec(output_key: str, length: int, source: InputSource = InputSource.CLOSE) -> FeatureSpec:
    """Create EMA spec with common defaults."""
    return FeatureSpec(
        indicator_type="ema",
        output_key=output_key,
        params={"length": length},
        input_source=source,
    )


def sma_spec(output_key: str, length: int, source: InputSource = InputSource.CLOSE) -> FeatureSpec:
    """Create SMA spec with common defaults."""
    return FeatureSpec(
        indicator_type="sma",
        output_key=output_key,
        params={"length": length},
        input_source=source,
    )


def rsi_spec(output_key: str, length: int = 14) -> FeatureSpec:
    """Create RSI spec with common defaults."""
    return FeatureSpec(
        indicator_type="rsi",
        output_key=output_key,
        params={"length": length},
        input_source=InputSource.CLOSE,
    )


def atr_spec(output_key: str, length: int = 14) -> FeatureSpec:
    """Create ATR spec with common defaults."""
    return FeatureSpec(
        indicator_type="atr",
        output_key=output_key,
        params={"length": length},
    )


def macd_spec(
    output_key: str,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
    outputs: dict[str, str] | None = None,
) -> FeatureSpec:
    """
    Create MACD spec.

    Outputs: macd, signal, histogram
    Default keys: {output_key}_macd, {output_key}_signal, {output_key}_histogram

    Args:
        output_key: Prefix for output keys
        fast: Fast EMA period (default: 12)
        slow: Slow EMA period (default: 26)
        signal: Signal EMA period (default: 9)
        outputs: Optional custom output key mapping
    """
    return FeatureSpec(
        indicator_type="macd",
        output_key=output_key,
        params={"fast": fast, "slow": slow, "signal": signal},
        outputs=outputs,
    )


def bbands_spec(
    output_key: str,
    length: int = 20,
    std: float = 2.0,
    outputs: dict[str, str] | None = None,
) -> FeatureSpec:
    """
    Create Bollinger Bands spec.

    Outputs: upper, middle, lower, bandwidth, percent_b
    Default keys: {output_key}_upper, {output_key}_middle, etc.

    Args:
        output_key: Prefix for output keys
        length: SMA period (default: 20)
        std: Standard deviation multiplier (default: 2.0)
        outputs: Optional custom output key mapping
    """
    return FeatureSpec(
        indicator_type="bbands",
        output_key=output_key,
        params={"length": length, "std": std},
        outputs=outputs,
    )


def stoch_spec(
    output_key: str,
    k: int = 14,
    d: int = 3,
    smooth_k: int = 3,
    outputs: dict[str, str] | None = None,
) -> FeatureSpec:
    """
    Create Stochastic Oscillator spec.

    Outputs: k, d
    Default keys: {output_key}_k, {output_key}_d

    Args:
        output_key: Prefix for output keys
        k: %K lookback period (default: 14)
        d: %D smoothing period (default: 3)
        smooth_k: %K smoothing period (default: 3)
        outputs: Optional custom output key mapping
    """
    return FeatureSpec(
        indicator_type="stoch",
        output_key=output_key,
        params={"k": k, "d": d, "smooth_k": smooth_k},
        outputs=outputs,
    )


def stochrsi_spec(
    output_key: str,
    length: int = 14,
    rsi_length: int = 14,
    k: int = 3,
    d: int = 3,
    outputs: dict[str, str] | None = None,
) -> FeatureSpec:
    """
    Create Stochastic RSI spec.

    Outputs: k, d
    Default keys: {output_key}_k, {output_key}_d

    Args:
        output_key: Prefix for output keys
        length: Stochastic lookback on RSI (default: 14)
        rsi_length: RSI period (default: 14)
        k: %K smoothing period (default: 3)
        d: %D smoothing period (default: 3)
        outputs: Optional custom output key mapping
    """
    return FeatureSpec(
        indicator_type="stochrsi",
        output_key=output_key,
        params={"length": length, "rsi_length": rsi_length, "k": k, "d": d},
        outputs=outputs,
    )
