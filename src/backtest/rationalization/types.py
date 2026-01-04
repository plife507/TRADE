"""
Rationalization Types - Pure data containers for Layer 2 state.

Architecture Principle: Pure Data
- Immutable dataclasses for transitions and state
- No side effects, no methods that modify state
- Engine orchestrates creation and flow

Transition: Records when a structure detector's state changes.
RationalizedState: Aggregates transitions and derived values per bar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MarketRegime(Enum):
    """Market regime classification.

    Pure enum - classification logic is in DerivedStateComputer.
    """
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    VOLATILE = "volatile"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class Transition:
    """Records a state change in a structure detector.

    Immutable dataclass capturing when a structure value changes.

    Attributes:
        detector: Name of the detector (e.g., "swing", "zone_demand")
        field: Output key that changed (e.g., "high_level", "state")
        old_value: Previous value (None if first observation)
        new_value: Current value after change
        bar_idx: Bar index when transition occurred
        timeframe: Timeframe where this occurred (e.g., "exec", "1h")

    Example:
        >>> t = Transition(
        ...     detector="swing",
        ...     field="high_level",
        ...     old_value=50000.0,
        ...     new_value=50500.0,
        ...     bar_idx=100,
        ...     timeframe="exec",
        ... )
    """
    detector: str
    field: str
    old_value: Any
    new_value: Any
    bar_idx: int
    timeframe: str = "exec"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "detector": self.detector,
            "field": self.field,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "bar_idx": self.bar_idx,
            "timeframe": self.timeframe,
        }


@dataclass(frozen=True, slots=True)
class RationalizedState:
    """Layer 2 state computed after structure updates.

    Aggregates transitions from all detectors and computes derived values.
    Created once per bar after all structure updates complete.

    Attributes:
        bar_idx: Bar index this state represents
        transitions: List of transitions that occurred this bar
        derived_values: Computed derived values (confluence, alignment, etc.)
        regime: Current market regime classification
        transition_count: Total transitions this bar (convenience)

    Example:
        >>> state = RationalizedState(
        ...     bar_idx=100,
        ...     transitions=[t1, t2],
        ...     derived_values={"confluence_score": 0.75},
        ...     regime=MarketRegime.TRENDING_UP,
        ... )
    """
    bar_idx: int
    transitions: tuple[Transition, ...] = field(default_factory=tuple)
    derived_values: dict[str, Any] = field(default_factory=dict)
    regime: MarketRegime = MarketRegime.UNKNOWN

    @property
    def transition_count(self) -> int:
        """Number of transitions this bar."""
        return len(self.transitions)

    @property
    def has_transitions(self) -> bool:
        """Whether any transitions occurred this bar."""
        return len(self.transitions) > 0

    def get_transitions_for(self, detector: str) -> tuple[Transition, ...]:
        """Get transitions for a specific detector."""
        return tuple(t for t in self.transitions if t.detector == detector)

    def get_derived(self, key: str, default: Any = None) -> Any:
        """Get a derived value by key."""
        return self.derived_values.get(key, default)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "bar_idx": self.bar_idx,
            "transitions": [t.to_dict() for t in self.transitions],
            "derived_values": self.derived_values,
            "regime": self.regime.value,
            "transition_count": self.transition_count,
        }


@dataclass(frozen=True, slots=True)
class TransitionFilter:
    """Filter criteria for querying transition history.

    Immutable filter spec - filtering logic is in TransitionManager.

    Attributes:
        detector: Filter by detector name (None = all)
        field: Filter by field name (None = all)
        timeframe: Filter by timeframe (None = all)
        min_bar_idx: Minimum bar index (inclusive)
        max_bar_idx: Maximum bar index (inclusive)
    """
    detector: str | None = None
    field: str | None = None
    timeframe: str | None = None
    min_bar_idx: int | None = None
    max_bar_idx: int | None = None

    def matches(self, transition: Transition) -> bool:
        """Check if a transition matches this filter."""
        if self.detector is not None and transition.detector != self.detector:
            return False
        if self.field is not None and transition.field != self.field:
            return False
        if self.timeframe is not None and transition.timeframe != self.timeframe:
            return False
        if self.min_bar_idx is not None and transition.bar_idx < self.min_bar_idx:
            return False
        if self.max_bar_idx is not None and transition.bar_idx > self.max_bar_idx:
            return False
        return True
