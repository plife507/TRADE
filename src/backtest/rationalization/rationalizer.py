"""
StateRationalizer - Layer 2 state computation.

Architecture Principle: Pure Math
- Input: MultiTFIncrementalState, bar_idx, bar
- Output: RationalizedState
- No side effects, engine orchestrates invocation
- Maintains only the state needed to detect transitions

The StateRationalizer:
1. Tracks previous values of structure outputs
2. Detects when values change (transitions)
3. Computes derived values (confluence, regime, alignment)
4. Returns a RationalizedState for the current bar

Engine Integration:
    # In engine hot loop, after structure updates:
    rationalized = rationalizer.rationalize(bar_idx, incremental_state, bar)
    snapshot.attach_rationalized_state(rationalized)

See: docs/architecture/IDEACARD_VISION.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .types import Transition, RationalizedState, MarketRegime

if TYPE_CHECKING:
    from src.backtest.incremental.state import MultiTFIncrementalState
    from src.backtest.incremental.base import BarData


@dataclass
class DetectorSnapshot:
    """Snapshot of a detector's output values.

    Used to track previous state for transition detection.
    """
    detector_key: str
    timeframe: str
    values: dict[str, Any] = field(default_factory=dict)

    def copy(self) -> "DetectorSnapshot":
        """Create a copy of this snapshot."""
        return DetectorSnapshot(
            detector_key=self.detector_key,
            timeframe=self.timeframe,
            values=dict(self.values),
        )


class StateRationalizer:
    """
    Layer 2 rationalization: transitions, derived state, regime detection.

    Pure computation class. Engine calls rationalize() after structure updates.
    This class maintains previous state only to detect changes.

    Architecture:
        - rationalize() is pure: (state, bar) -> RationalizedState
        - Previous values are cached for transition detection
        - No control flow about when to run - engine decides

    Example:
        >>> rationalizer = StateRationalizer()
        >>> rationalized = rationalizer.rationalize(bar_idx, incremental_state, bar)
        >>> print(rationalized.transitions)
        [Transition(detector='swing', field='high_level', ...)]

    Attributes:
        _previous: Previous detector snapshots by (timeframe, key)
        _transition_history: Recent transitions for lookback queries
        _history_depth: Max transitions to keep in history
    """

    def __init__(self, history_depth: int = 1000) -> None:
        """Initialize the rationalizer.

        Args:
            history_depth: Maximum transitions to keep in history buffer
        """
        self._previous: dict[tuple[str, str], DetectorSnapshot] = {}
        self._transition_history: list[Transition] = []
        self._history_depth = history_depth
        self._initialized = False

    def rationalize(
        self,
        bar_idx: int,
        incremental_state: "MultiTFIncrementalState",
        bar: "BarData",
    ) -> RationalizedState:
        """
        Compute rationalized state for current bar.

        Pure function: (bar_idx, state, bar) -> RationalizedState

        This is the main entry point called by the engine after all
        structure updates complete for the current bar.

        Args:
            bar_idx: Current bar index
            incremental_state: Current MultiTFIncrementalState with all TF states
            bar: Current BarData (for derived computations)

        Returns:
            RationalizedState with transitions and derived values
        """
        # Detect transitions from all timeframes
        transitions = self._detect_all_transitions(bar_idx, incremental_state)

        # Compute derived values
        derived = self._compute_derived_values(incremental_state, bar)

        # Classify regime
        regime = self._classify_regime(incremental_state, bar)

        # Update history
        self._update_history(transitions)

        return RationalizedState(
            bar_idx=bar_idx,
            transitions=tuple(transitions),
            derived_values=derived,
            regime=regime,
        )

    def _detect_all_transitions(
        self,
        bar_idx: int,
        incremental_state: "MultiTFIncrementalState",
    ) -> list[Transition]:
        """Detect transitions across all timeframes."""
        transitions: list[Transition] = []

        # Process exec timeframe
        exec_state = incremental_state.exec
        for detector_key in exec_state.list_detectors():
            detector = exec_state.get_detector(detector_key)
            tf_transitions = self._detect_detector_transitions(
                bar_idx=bar_idx,
                timeframe="exec",
                detector_key=detector_key,
                detector=detector,
            )
            transitions.extend(tf_transitions)

        # Process HTF timeframes
        for tf_name, tf_state in incremental_state.htf_states.items():
            for detector_key in tf_state.list_detectors():
                detector = tf_state.get_detector(detector_key)
                tf_transitions = self._detect_detector_transitions(
                    bar_idx=bar_idx,
                    timeframe=tf_name,
                    detector_key=detector_key,
                    detector=detector,
                )
                transitions.extend(tf_transitions)

        return transitions

    def _detect_detector_transitions(
        self,
        bar_idx: int,
        timeframe: str,
        detector_key: str,
        detector: Any,  # BaseIncrementalDetector
    ) -> list[Transition]:
        """Detect transitions for a single detector."""
        transitions: list[Transition] = []
        cache_key = (timeframe, detector_key)

        # Get current values
        current_values: dict[str, Any] = {}
        for output_key in detector.get_output_keys():
            current_values[output_key] = detector.get_value(output_key)

        # Get previous snapshot
        previous = self._previous.get(cache_key)

        if previous is not None:
            # Compare current vs previous
            for key, current_val in current_values.items():
                prev_val = previous.values.get(key)
                if prev_val != current_val:
                    transitions.append(Transition(
                        detector=detector_key,
                        field=key,
                        old_value=prev_val,
                        new_value=current_val,
                        bar_idx=bar_idx,
                        timeframe=timeframe,
                    ))
        else:
            # First observation - record initial values
            # Only emit transitions for non-None values on first bar
            for key, current_val in current_values.items():
                if current_val is not None:
                    transitions.append(Transition(
                        detector=detector_key,
                        field=key,
                        old_value=None,
                        new_value=current_val,
                        bar_idx=bar_idx,
                        timeframe=timeframe,
                    ))

        # Update previous snapshot
        self._previous[cache_key] = DetectorSnapshot(
            detector_key=detector_key,
            timeframe=timeframe,
            values=current_values,
        )

        return transitions

    def _compute_derived_values(
        self,
        incremental_state: "MultiTFIncrementalState",
        bar: "BarData",
    ) -> dict[str, Any]:
        """Compute derived values from current state.

        Placeholder for W2-P3 implementation.
        Will compute:
        - confluence_score: Signal alignment (0.0-1.0)
        - alignment: HTF/MTF/LTF agreement
        - momentum: Aggregate momentum signal
        """
        # W2-P3: Full implementation
        return {
            "confluence_score": 0.0,
            "alignment": 0.0,
        }

    def _classify_regime(
        self,
        incremental_state: "MultiTFIncrementalState",
        bar: "BarData",
    ) -> MarketRegime:
        """Classify current market regime.

        Placeholder for W2-P3 implementation.
        Will use trend direction, volatility, range detection.
        """
        # W2-P3: Full implementation using trend detector + volatility
        return MarketRegime.UNKNOWN

    def _update_history(self, transitions: list[Transition]) -> None:
        """Update transition history buffer."""
        self._transition_history.extend(transitions)

        # Trim to max depth
        if len(self._transition_history) > self._history_depth:
            trim_count = len(self._transition_history) - self._history_depth
            self._transition_history = self._transition_history[trim_count:]

    def get_recent_transitions(
        self,
        count: int | None = None,
        detector: str | None = None,
        field: str | None = None,
    ) -> list[Transition]:
        """Query recent transitions from history.

        Args:
            count: Max transitions to return (None = all)
            detector: Filter by detector name
            field: Filter by field name

        Returns:
            List of matching transitions (most recent last)
        """
        filtered = self._transition_history

        if detector is not None:
            filtered = [t for t in filtered if t.detector == detector]

        if field is not None:
            filtered = [t for t in filtered if t.field == field]

        if count is not None:
            filtered = filtered[-count:]

        return filtered

    def reset(self) -> None:
        """Reset all state.

        Call when starting a new backtest run.
        """
        self._previous.clear()
        self._transition_history.clear()
        self._initialized = False
