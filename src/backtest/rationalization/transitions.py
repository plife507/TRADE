"""
Transition Manager - Dedicated transition detection and tracking.

Architecture Principle: Pure Math
- Input: Current detector state
- Output: List of transitions
- Tracks previous state for comparison
- No control flow about invocation

The TransitionManager:
1. Caches previous values for each (timeframe, detector, field)
2. Compares current vs previous on each update
3. Emits Transition objects for any changes
4. Maintains bounded history buffer for lookback queries

Engine Integration:
    # Called by StateRationalizer after structure updates
    transitions = transition_manager.detect_transitions(bar_idx, incremental_state)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from collections import deque
from typing import TYPE_CHECKING, Any

from .types import Transition, TransitionFilter

if TYPE_CHECKING:
    from src.backtest.incremental.state import MultiTFIncrementalState, TFIncrementalState
    from src.backtest.incremental.base import BaseIncrementalDetector


# Key fields to track for each detector type
# These are the "interesting" fields that signal state changes
TRACKED_FIELDS: dict[str, list[str]] = {
    "swing": ["high_level", "low_level", "high_idx", "low_idx", "version"],
    "zone": ["state", "upper", "lower", "version"],
    "trend": ["direction", "strength", "bars_in_trend", "version"],
    "fibonacci": ["level_0.382", "level_0.5", "level_0.618"],
    "rolling_window": ["value"],
    "derived_zone": [
        "zone0_state", "zone1_state", "zone2_state",
        "any_active", "active_count", "source_version",
    ],
}


@dataclass
class FieldSnapshot:
    """Snapshot of a single field's value at a point in time."""
    value: Any
    bar_idx: int


class TransitionManager:
    """
    Manages transition detection across all structure detectors.

    Pure computation class. Maintains previous state for comparison
    and bounded history buffer for lookback queries.

    Attributes:
        _previous: Previous field values by (timeframe, detector_key, field)
        _history: Bounded transition history (most recent at end)
        _history_depth: Maximum transitions to keep
        _version_only_types: Detector types that only track version changes
    """

    def __init__(
        self,
        history_depth: int = 1000,
        version_only: bool = False,
    ) -> None:
        """Initialize the transition manager.

        Args:
            history_depth: Maximum transitions to keep in history
            version_only: If True, only track 'version' field changes
        """
        self._previous: dict[tuple[str, str, str], FieldSnapshot] = {}
        self._history: deque[Transition] = deque(maxlen=history_depth)
        self._history_depth = history_depth
        self._version_only = version_only

    def detect_transitions(
        self,
        bar_idx: int,
        incremental_state: "MultiTFIncrementalState",
    ) -> list[Transition]:
        """
        Detect all transitions from current state.

        Pure function: (bar_idx, state) -> list[Transition]

        Compares current detector values against previous snapshots
        and emits Transition objects for any changes.

        Args:
            bar_idx: Current bar index
            incremental_state: Current MultiTFIncrementalState

        Returns:
            List of transitions that occurred this bar
        """
        transitions: list[Transition] = []

        # Process exec timeframe
        exec_transitions = self._detect_tf_transitions(
            bar_idx=bar_idx,
            timeframe="exec",
            tf_state=incremental_state.exec,
        )
        transitions.extend(exec_transitions)

        # Process HTF timeframes
        for tf_name, tf_state in incremental_state.htf.items():
            htf_transitions = self._detect_tf_transitions(
                bar_idx=bar_idx,
                timeframe=tf_name,
                tf_state=tf_state,
            )
            transitions.extend(htf_transitions)

        # Update history
        self._history.extend(transitions)

        return transitions

    def _detect_tf_transitions(
        self,
        bar_idx: int,
        timeframe: str,
        tf_state: "TFIncrementalState",
    ) -> list[Transition]:
        """Detect transitions for a single timeframe."""
        transitions: list[Transition] = []

        for detector_key in tf_state.list_structures():
            detector = tf_state.structures[detector_key]
            detector_transitions = self._detect_detector_transitions(
                bar_idx=bar_idx,
                timeframe=timeframe,
                detector_key=detector_key,
                detector=detector,
            )
            transitions.extend(detector_transitions)

        return transitions

    def _detect_detector_transitions(
        self,
        bar_idx: int,
        timeframe: str,
        detector_key: str,
        detector: "BaseIncrementalDetector",
    ) -> list[Transition]:
        """Detect transitions for a single detector."""
        transitions: list[Transition] = []

        # Determine which fields to track
        detector_type = self._get_detector_type(detector)
        fields_to_track = self._get_tracked_fields(detector_type, detector)

        for field_name in fields_to_track:
            try:
                current_value = detector.get_value(field_name)
            except KeyError:
                # Field doesn't exist for this detector
                continue

            cache_key = (timeframe, detector_key, field_name)
            previous = self._previous.get(cache_key)

            if previous is not None:
                # Compare with previous
                if previous.value != current_value:
                    transitions.append(Transition(
                        detector=detector_key,
                        field=field_name,
                        old_value=previous.value,
                        new_value=current_value,
                        bar_idx=bar_idx,
                        timeframe=timeframe,
                    ))
            else:
                # First observation - emit transition from None
                if current_value is not None:
                    transitions.append(Transition(
                        detector=detector_key,
                        field=field_name,
                        old_value=None,
                        new_value=current_value,
                        bar_idx=bar_idx,
                        timeframe=timeframe,
                    ))

            # Update previous snapshot
            self._previous[cache_key] = FieldSnapshot(
                value=current_value,
                bar_idx=bar_idx,
            )

        return transitions

    def _get_detector_type(self, detector: "BaseIncrementalDetector") -> str:
        """Get the type name of a detector."""
        # Extract from class name or registry name
        cls_name = type(detector).__name__
        # Common pattern: SwingDetector -> swing
        if cls_name.endswith("Detector"):
            return cls_name[:-8].lower()
        return cls_name.lower()

    def _get_tracked_fields(
        self,
        detector_type: str,
        detector: "BaseIncrementalDetector",
    ) -> list[str]:
        """Get list of fields to track for a detector type."""
        if self._version_only:
            return ["version"]

        # Use configured tracked fields if available
        if detector_type in TRACKED_FIELDS:
            return TRACKED_FIELDS[detector_type]

        # Fallback: track all output keys
        return detector.get_output_keys()

    def get_history(
        self,
        filter_spec: TransitionFilter | None = None,
        count: int | None = None,
    ) -> list[Transition]:
        """
        Query transition history with optional filtering.

        Args:
            filter_spec: Filter criteria (None = no filter)
            count: Max transitions to return (None = all matching)

        Returns:
            List of matching transitions (most recent last)
        """
        result: list[Transition] = []

        for transition in self._history:
            if filter_spec is None or filter_spec.matches(transition):
                result.append(transition)

        if count is not None:
            result = result[-count:]

        return result

    def get_transitions_since(
        self,
        bar_idx: int,
        detector: str | None = None,
    ) -> list[Transition]:
        """
        Get all transitions since a given bar index.

        Args:
            bar_idx: Starting bar index (inclusive)
            detector: Filter by detector name (None = all)

        Returns:
            List of transitions since bar_idx
        """
        filter_spec = TransitionFilter(
            detector=detector,
            min_bar_idx=bar_idx,
        )
        return self.get_history(filter_spec)

    def get_last_transition(
        self,
        detector: str,
        field: str,
    ) -> Transition | None:
        """
        Get the most recent transition for a specific detector/field.

        Args:
            detector: Detector name
            field: Field name

        Returns:
            Most recent Transition or None if no history
        """
        for transition in reversed(self._history):
            if transition.detector == detector and transition.field == field:
                return transition
        return None

    def count_transitions(
        self,
        detector: str | None = None,
        since_bar_idx: int | None = None,
    ) -> int:
        """
        Count transitions matching criteria.

        Args:
            detector: Filter by detector name
            since_bar_idx: Only count transitions after this bar

        Returns:
            Number of matching transitions
        """
        count = 0
        for transition in self._history:
            if detector is not None and transition.detector != detector:
                continue
            if since_bar_idx is not None and transition.bar_idx < since_bar_idx:
                continue
            count += 1
        return count

    def reset(self) -> None:
        """Reset all state. Call when starting a new backtest run."""
        self._previous.clear()
        self._history.clear()

    @property
    def history_size(self) -> int:
        """Current size of transition history."""
        return len(self._history)

    @property
    def tracked_fields_count(self) -> int:
        """Number of fields currently being tracked."""
        return len(self._previous)
