"""
Indicator Renderer Registry.

Maps indicator types to their visualization methods.
Fails loud if an unsupported indicator type is encountered.
"""

from typing import Any
from dataclasses import dataclass


class UnsupportedIndicatorError(Exception):
    """Raised when an indicator type has no supported renderer."""

    def __init__(self, indicator_type: str, supported: list[str]):
        self.indicator_type = indicator_type
        self.supported = supported
        super().__init__(
            f"Visualizer does not support indicator type '{indicator_type}'. "
            f"Supported: {supported}"
        )


@dataclass
class IndicatorRenderSpec:
    """Specification for how to render an indicator."""

    render_method: str  # line, bands, macd_pane, dual_line, etc.
    display: str  # overlay or pane
    pane_type: str | None = None  # For pane indicators: RSI, MACD, etc.
    reference_lines: list[float] | None = None  # e.g., [30, 70] for RSI


# TradingView-style color palette
INDICATOR_COLORS = [
    "#2196F3",  # Blue
    "#FF9800",  # Orange
    "#E91E63",  # Pink
    "#9C27B0",  # Purple
    "#00BCD4",  # Cyan
    "#4CAF50",  # Green
    "#FFC107",  # Amber
    "#795548",  # Brown
    "#607D8B",  # Blue Grey
    "#F44336",  # Red
]


class IndicatorRenderer:
    """
    Registry of supported indicator visualization methods.

    Fail-loud: raises UnsupportedIndicatorError for unknown types.
    """

    # Indicator type -> render specification
    SUPPORTED: dict[str, IndicatorRenderSpec] = {
        # -----------------------------------------------------------------
        # Overlay Indicators (on price chart)
        # -----------------------------------------------------------------
        # Moving Averages - single line
        "ema": IndicatorRenderSpec("line", "overlay"),
        "sma": IndicatorRenderSpec("line", "overlay"),
        "wma": IndicatorRenderSpec("line", "overlay"),
        "dema": IndicatorRenderSpec("line", "overlay"),
        "tema": IndicatorRenderSpec("line", "overlay"),
        "zlma": IndicatorRenderSpec("line", "overlay"),
        "kama": IndicatorRenderSpec("line", "overlay"),
        "alma": IndicatorRenderSpec("line", "overlay"),
        "trima": IndicatorRenderSpec("line", "overlay"),
        "hma": IndicatorRenderSpec("line", "overlay"),
        "vwma": IndicatorRenderSpec("line", "overlay"),

        # Bands - multi-line with fill
        "bbands": IndicatorRenderSpec("bands", "overlay"),
        "kc": IndicatorRenderSpec("bands", "overlay"),
        "donchian": IndicatorRenderSpec("bands", "overlay"),

        # Special overlays
        "supertrend": IndicatorRenderSpec("supertrend", "overlay"),
        "psar": IndicatorRenderSpec("markers", "overlay"),

        # -----------------------------------------------------------------
        # Pane Indicators (separate charts)
        # -----------------------------------------------------------------
        # Momentum - single line with reference lines
        "rsi": IndicatorRenderSpec(
            "line", "pane", pane_type="RSI", reference_lines=[30, 70]
        ),
        "cci": IndicatorRenderSpec(
            "line", "pane", pane_type="CCI", reference_lines=[-100, 100]
        ),
        "willr": IndicatorRenderSpec(
            "line", "pane", pane_type="Williams %R", reference_lines=[-80, -20]
        ),
        "cmo": IndicatorRenderSpec(
            "line", "pane", pane_type="CMO", reference_lines=[-50, 50]
        ),
        "roc": IndicatorRenderSpec("line", "pane", pane_type="ROC"),
        "mom": IndicatorRenderSpec("line", "pane", pane_type="Momentum"),

        # Volatility - single line
        "atr": IndicatorRenderSpec("line", "pane", pane_type="ATR"),
        "natr": IndicatorRenderSpec("line", "pane", pane_type="NATR"),

        # Volume indicators
        "obv": IndicatorRenderSpec("line", "pane", pane_type="OBV"),
        "mfi": IndicatorRenderSpec(
            "line", "pane", pane_type="MFI", reference_lines=[20, 80]
        ),
        "cmf": IndicatorRenderSpec("line", "pane", pane_type="CMF"),

        # Complex multi-output panes
        "macd": IndicatorRenderSpec("macd_pane", "pane", pane_type="MACD"),
        "stoch": IndicatorRenderSpec(
            "dual_line", "pane", pane_type="Stoch", reference_lines=[20, 80]
        ),
        "stochrsi": IndicatorRenderSpec(
            "dual_line", "pane", pane_type="StochRSI", reference_lines=[20, 80]
        ),
        "adx": IndicatorRenderSpec("adx_pane", "pane", pane_type="ADX"),
        "aroon": IndicatorRenderSpec(
            "dual_line", "pane", pane_type="Aroon", reference_lines=[30, 70]
        ),
        "trix": IndicatorRenderSpec("line", "pane", pane_type="TRIX"),
        "ppo": IndicatorRenderSpec("line", "pane", pane_type="PPO"),
    }

    _color_index: int = 0

    @classmethod
    def get_supported_types(cls) -> list[str]:
        """Get list of all supported indicator types."""
        return sorted(cls.SUPPORTED.keys())

    @classmethod
    def is_supported(cls, indicator_type: str) -> bool:
        """Check if an indicator type is supported."""
        return indicator_type in cls.SUPPORTED

    @classmethod
    def get_spec(cls, indicator_type: str) -> IndicatorRenderSpec:
        """
        Get render specification for an indicator type.

        Raises:
            UnsupportedIndicatorError: If type not supported
        """
        if indicator_type not in cls.SUPPORTED:
            raise UnsupportedIndicatorError(
                indicator_type, cls.get_supported_types()
            )
        return cls.SUPPORTED[indicator_type]

    @classmethod
    def is_overlay(cls, indicator_type: str) -> bool:
        """Check if indicator renders as overlay on price chart."""
        spec = cls.get_spec(indicator_type)
        return spec.display == "overlay"

    @classmethod
    def is_pane(cls, indicator_type: str) -> bool:
        """Check if indicator renders in separate pane."""
        spec = cls.get_spec(indicator_type)
        return spec.display == "pane"

    @classmethod
    def next_color(cls) -> str:
        """Get next color from palette (cycles through)."""
        color = INDICATOR_COLORS[cls._color_index % len(INDICATOR_COLORS)]
        cls._color_index += 1
        return color

    @classmethod
    def reset_colors(cls) -> None:
        """Reset color index (call at start of each render session)."""
        cls._color_index = 0

    @classmethod
    def format_label(cls, indicator_type: str, params: dict, tf: str) -> str:
        """
        Format a human-readable label for the indicator.

        Args:
            indicator_type: Type like "ema", "rsi"
            params: Indicator params like {"length": 20}
            tf: Timeframe like "15m", "1h"

        Returns:
            Label like "EMA(20) 15m"
        """
        type_upper = indicator_type.upper()

        # Extract relevant param for label
        length = params.get("length")
        if length:
            return f"{type_upper}({length}) {tf}"

        # For MACD-style
        fast = params.get("fast")
        slow = params.get("slow")
        signal = params.get("signal")
        if fast and slow and signal:
            return f"{type_upper}({fast},{slow},{signal}) {tf}"

        return f"{type_upper} {tf}"

    @classmethod
    def render(
        cls,
        indicator_type: str,
        key: str,
        data: list[dict],
        params: dict,
        tf: str,
    ) -> dict[str, Any]:
        """
        Render indicator data for API response.

        Args:
            indicator_type: Type like "ema", "rsi"
            key: Unique key like "ema_20_close"
            data: List of {"time": unix_ts, "value": float}
            params: Indicator params
            tf: Timeframe

        Returns:
            Dict ready for JSON serialization

        Raises:
            UnsupportedIndicatorError: If type not supported
        """
        spec = cls.get_spec(indicator_type)

        return {
            "key": key,
            "type": indicator_type,
            "render_method": spec.render_method,
            "params": params,
            "tf": tf,
            "label": cls.format_label(indicator_type, params, tf),
            "color": cls.next_color(),
            "data": data,
        }
