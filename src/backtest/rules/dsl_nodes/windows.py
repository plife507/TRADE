"""
DSL Window Operator Nodes for Play Expression Language.

This module defines window operators for time-series conditions:
- HoldsFor: Expression must be true for N consecutive bars
- OccurredWithin: Expression was true at least once in last N bars
- CountTrue: Expression was true at least M times in last N bars
- Duration-based variants (HoldsForDuration, OccurredWithinDuration, CountTrueDuration)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .constants import (
    WINDOW_BARS_CEILING,
    WINDOW_DURATION_CEILING_MINUTES,
    ACTION_TF_MINUTES,
    DURATION_PATTERN,
)

if TYPE_CHECKING:
    from .types import Expr


def parse_duration_to_minutes(duration: str) -> int:
    """
    Parse a duration string to minutes.

    Supported formats:
        - "Nm" for N minutes (e.g., "5m", "30m")
        - "Nh" for N hours (e.g., "1h", "4h")
        - "Nd" for N days (e.g., "1d", "7d")

    Args:
        duration: Duration string like "30m", "2h", or "1d"

    Returns:
        Duration in minutes

    Raises:
        ValueError: If format is invalid or exceeds ceiling
    """
    match = DURATION_PATTERN.match(duration.lower().strip())
    if not match:
        raise ValueError(
            f"Invalid duration format: '{duration}'. "
            f"Expected format: '<number>m', '<number>h', or '<number>d' (e.g., '30m', '2h', '1d')"
        )

    value = int(match.group(1))
    unit = match.group(2)

    if unit == "m":
        minutes = value
    elif unit == "h":
        minutes = value * 60
    else:  # unit == "d"
        minutes = value * 1440  # 24 hours * 60 minutes

    if minutes < 1:
        raise ValueError(f"Duration must be at least 1 minute, got {minutes}")

    if minutes > WINDOW_DURATION_CEILING_MINUTES:
        raise ValueError(
            f"Duration '{duration}' ({minutes}m) exceeds ceiling "
            f"({WINDOW_DURATION_CEILING_MINUTES}m = 24h)"
        )

    return minutes


def duration_to_bars(duration: str, anchor_tf_minutes: int = ACTION_TF_MINUTES) -> int:
    """
    Convert a duration string to bar count at anchor_tf granularity.

    Args:
        duration: Duration string like "30m" or "2h"
        anchor_tf_minutes: Minutes per bar at anchor TF (default: 1m)

    Returns:
        Number of bars

    Raises:
        ValueError: If duration is shorter than anchor_tf or bar count exceeds ceiling

    Examples:
        >>> duration_to_bars("30m", 1)   # 30 bars at 1m
        30
        >>> duration_to_bars("1h", 1)    # 60 bars at 1m
        60
        >>> duration_to_bars("30m", 15)  # 2 bars at 15m
        2
    """
    minutes = parse_duration_to_minutes(duration)
    bars = minutes // anchor_tf_minutes

    if bars < 1:
        raise ValueError(
            f"Duration '{duration}' ({minutes}m) is shorter than anchor_tf "
            f"({anchor_tf_minutes}m) - would be 0 bars"
        )

    if bars > WINDOW_BARS_CEILING:
        raise ValueError(
            f"Duration '{duration}' at {anchor_tf_minutes}m anchor_tf = {bars} bars, "
            f"exceeds ceiling ({WINDOW_BARS_CEILING})"
        )

    return bars


# =============================================================================
# Window Operator Nodes (Bar-Based)
# =============================================================================

@dataclass(frozen=True)
class HoldsFor:
    """
    Window operator: Expression must be true for N consecutive bars.

    Checks that expr was true at offset 0, 1, 2, ..., bars-1.

    With anchor_tf, all features are sampled at anchor_tf rate:
    - Features slower than anchor_tf forward-fill
    - Features faster than anchor_tf are sampled at anchor_tf boundaries

    Attributes:
        bars: Number of consecutive bars (must be > 0, <= ceiling)
        expr: The expression to check
        anchor_tf: Timeframe at which to sample bars (default: action_tf = 1m)

    Examples:
        # RSI > 50 for last 5 bars at 1m (default)
        HoldsFor(
            bars=5,
            expr=Cond(
                lhs=FeatureRef(feature_id="rsi_14"),
                op="gt",
                rhs=ScalarValue(50.0)
            )
        )

        # RSI > 50 for last 5 bars at 15m
        HoldsFor(
            bars=5,
            anchor_tf="15m",
            expr=Cond(...)
        )
    """
    bars: int
    expr: "Expr"
    anchor_tf: str | None = None  # Default: action_tf (1m)

    def __post_init__(self):
        """Validate bars parameter."""
        if self.bars < 1:
            raise ValueError(f"HoldsFor: bars must be >= 1, got {self.bars}")
        if self.bars > WINDOW_BARS_CEILING:
            raise ValueError(
                f"HoldsFor: bars must be <= {WINDOW_BARS_CEILING}, got {self.bars}"
            )

    def __repr__(self) -> str:
        if self.anchor_tf:
            return f"HoldsFor({self.bars}, anchor_tf={self.anchor_tf!r}, {self.expr!r})"
        return f"HoldsFor({self.bars}, {self.expr!r})"


@dataclass(frozen=True)
class OccurredWithin:
    """
    Window operator: Expression was true at least once in last N bars.

    Checks offsets 0, 1, 2, ..., bars-1 for at least one true.

    With anchor_tf, all features are sampled at anchor_tf rate.

    Attributes:
        bars: Window size (must be > 0, <= ceiling)
        expr: The expression to check
        anchor_tf: Timeframe at which to sample bars (default: action_tf = 1m)

    Examples:
        # EMA crossover occurred in last 3 bars at 1m (default)
        OccurredWithin(
            bars=3,
            expr=Cond(
                lhs=FeatureRef(feature_id="ema_fast"),
                op="cross_above",
                rhs=FeatureRef(feature_id="ema_slow")
            )
        )

        # EMA crossover occurred in last 3 bars at 15m
        OccurredWithin(
            bars=3,
            anchor_tf="15m",
            expr=Cond(...)
        )
    """
    bars: int
    expr: "Expr"
    anchor_tf: str | None = None  # Default: action_tf (1m)

    def __post_init__(self):
        """Validate bars parameter."""
        if self.bars < 1:
            raise ValueError(
                f"OccurredWithin: bars must be >= 1, got {self.bars}"
            )
        if self.bars > WINDOW_BARS_CEILING:
            raise ValueError(
                f"OccurredWithin: bars must be <= {WINDOW_BARS_CEILING}, "
                f"got {self.bars}"
            )

    def __repr__(self) -> str:
        if self.anchor_tf:
            return f"OccurredWithin({self.bars}, anchor_tf={self.anchor_tf!r}, {self.expr!r})"
        return f"OccurredWithin({self.bars}, {self.expr!r})"


@dataclass(frozen=True)
class CountTrue:
    """
    Window operator: Expression must be true at least N times in last M bars.

    Counts how many times expr was true across offsets 0..bars-1.

    With anchor_tf, all features are sampled at anchor_tf rate.

    Attributes:
        bars: Window size (must be > 0, <= ceiling)
        min_true: Minimum true count required
        expr: The expression to check
        anchor_tf: Timeframe at which to sample bars (default: action_tf = 1m)

    Examples:
        # RSI was overbought at least 3 times in last 10 bars at 1m (default)
        CountTrue(
            bars=10,
            min_true=3,
            expr=Cond(
                lhs=FeatureRef(feature_id="rsi_14"),
                op="gt",
                rhs=ScalarValue(70.0)
            )
        )

        # RSI was overbought at least 3 times in last 10 bars at 15m
        CountTrue(
            bars=10,
            min_true=3,
            anchor_tf="15m",
            expr=Cond(...)
        )
    """
    bars: int
    min_true: int
    expr: "Expr"
    anchor_tf: str | None = None  # Default: action_tf (1m)

    def __post_init__(self):
        """Validate parameters."""
        if self.bars < 1:
            raise ValueError(f"CountTrue: bars must be >= 1, got {self.bars}")
        if self.bars > WINDOW_BARS_CEILING:
            raise ValueError(
                f"CountTrue: bars must be <= {WINDOW_BARS_CEILING}, "
                f"got {self.bars}"
            )
        if self.min_true < 1:
            raise ValueError(
                f"CountTrue: min_true must be >= 1, got {self.min_true}"
            )
        if self.min_true > self.bars:
            raise ValueError(
                f"CountTrue: min_true ({self.min_true}) cannot exceed "
                f"bars ({self.bars})"
            )

    def __repr__(self) -> str:
        if self.anchor_tf:
            return f"CountTrue({self.bars}, min={self.min_true}, anchor_tf={self.anchor_tf!r}, {self.expr!r})"
        return f"CountTrue({self.bars}, min={self.min_true}, {self.expr!r})"


# =============================================================================
# Duration-Based Window Operator Nodes
# =============================================================================
# These operators use explicit time durations instead of bar counts.
# Duration is always converted to bars at action_tf (1m) for evaluation.

@dataclass(frozen=True)
class HoldsForDuration:
    """
    Duration-based window operator: Expression must be true for specified duration.

    Unlike HoldsFor (bar-based), this uses an explicit time duration.
    Duration is converted to bars at action_tf (1m) for consistent cross-TF behavior.

    Attributes:
        duration: Duration string (e.g., "5m", "30m", "1h", "4h")
        expr: The expression to check

    Semantics:
        - Duration is converted to 1m bars (e.g., "30m" = 30 bars at 1m)
        - All features are sampled at 1m rate
        - Features slower than 1m forward-fill their last closed value
        - Maximum duration: 24 hours (1440 minutes)

    Examples:
        # RSI > 50 for at least 30 minutes
        HoldsForDuration(
            duration="30m",
            expr=Cond(
                lhs=FeatureRef(feature_id="rsi_14"),
                op="gt",
                rhs=ScalarValue(50.0)
            )
        )

        # Price above EMA for 1 hour
        HoldsForDuration(
            duration="1h",
            expr=Cond(
                lhs=FeatureRef(feature_id="last_price"),
                op="gt",
                rhs=FeatureRef(feature_id="ema_50_1h")
            )
        )
    """
    duration: str
    expr: "Expr"

    def __post_init__(self):
        """Validate duration parameter."""
        # Validate duration format and ceiling
        parse_duration_to_minutes(self.duration)

    def to_bars(self, anchor_tf_minutes: int = ACTION_TF_MINUTES) -> int:
        """Convert duration to bar count at anchor_tf."""
        return duration_to_bars(self.duration, anchor_tf_minutes)

    def __repr__(self) -> str:
        return f"HoldsForDuration({self.duration!r}, {self.expr!r})"


@dataclass(frozen=True)
class OccurredWithinDuration:
    """
    Duration-based window operator: Expression was true at least once within duration.

    Unlike OccurredWithin (bar-based), this uses an explicit time duration.
    Duration is converted to bars at action_tf (1m) for consistent cross-TF behavior.

    Attributes:
        duration: Duration string (e.g., "5m", "30m", "1h", "4h")
        expr: The expression to check

    Semantics:
        - Duration is converted to 1m bars
        - Checks if expr was true at least once in the window
        - Maximum duration: 24 hours (1440 minutes)

    Examples:
        # EMA crossover occurred within last 15 minutes
        OccurredWithinDuration(
            duration="15m",
            expr=Cond(
                lhs=FeatureRef(feature_id="ema_9"),
                op="cross_above",
                rhs=FeatureRef(feature_id="ema_21")
            )
        )
    """
    duration: str
    expr: "Expr"

    def __post_init__(self):
        """Validate duration parameter."""
        parse_duration_to_minutes(self.duration)

    def to_bars(self, anchor_tf_minutes: int = ACTION_TF_MINUTES) -> int:
        """Convert duration to bar count at anchor_tf."""
        return duration_to_bars(self.duration, anchor_tf_minutes)

    def __repr__(self) -> str:
        return f"OccurredWithinDuration({self.duration!r}, {self.expr!r})"


@dataclass(frozen=True)
class CountTrueDuration:
    """
    Duration-based window operator: Expression must be true at least N times within duration.

    Unlike CountTrue (bar-based), this uses an explicit time duration.
    Duration is converted to bars at action_tf (1m) for consistent cross-TF behavior.

    Attributes:
        duration: Duration string (e.g., "5m", "30m", "1h", "4h")
        min_true: Minimum true count required
        expr: The expression to check

    Semantics:
        - Duration is converted to 1m bars
        - Counts true occurrences across the window
        - Maximum duration: 24 hours (1440 minutes)

    Examples:
        # RSI was overbought at least 5 times in last hour
        CountTrueDuration(
            duration="1h",
            min_true=5,
            expr=Cond(
                lhs=FeatureRef(feature_id="rsi_14"),
                op="gt",
                rhs=ScalarValue(70.0)
            )
        )
    """
    duration: str
    min_true: int
    expr: "Expr"

    def __post_init__(self):
        """Validate parameters."""
        minutes = parse_duration_to_minutes(self.duration)
        bars = minutes // ACTION_TF_MINUTES

        if self.min_true < 1:
            raise ValueError(
                f"CountTrueDuration: min_true must be >= 1, got {self.min_true}"
            )
        if self.min_true > bars:
            raise ValueError(
                f"CountTrueDuration: min_true ({self.min_true}) cannot exceed "
                f"bars in duration ({bars})"
            )

    def to_bars(self, anchor_tf_minutes: int = ACTION_TF_MINUTES) -> int:
        """Convert duration to bar count at anchor_tf."""
        return duration_to_bars(self.duration, anchor_tf_minutes)

    def __repr__(self) -> str:
        return f"CountTrueDuration({self.duration!r}, min={self.min_true}, {self.expr!r})"


# Type aliases for window operators
BarWindowExpr = HoldsFor | OccurredWithin | CountTrue
DurationWindowExpr = HoldsForDuration | OccurredWithinDuration | CountTrueDuration
WindowExpr = BarWindowExpr | DurationWindowExpr


__all__ = [
    # Duration utilities
    "parse_duration_to_minutes",
    "duration_to_bars",
    # Bar-based window operators
    "HoldsFor",
    "OccurredWithin",
    "CountTrue",
    # Duration-based window operators
    "HoldsForDuration",
    "OccurredWithinDuration",
    "CountTrueDuration",
    # Type aliases
    "BarWindowExpr",
    "DurationWindowExpr",
    "WindowExpr",
]
