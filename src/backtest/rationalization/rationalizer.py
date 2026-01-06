"""
StateRationalizer - Layer 2 state computation.

Architecture Principle: Pure Math
- Input: MultiTFIncrementalState, bar_idx, bar
- Output: RationalizedState
- No side effects, engine orchestrates invocation
- Delegates to specialized components (TransitionManager, DerivedStateComputer)

The StateRationalizer:
1. Delegates transition detection to TransitionManager
2. Computes derived values (confluence, regime, alignment)
3. Returns a RationalizedState for the current bar

Engine Integration:
    # In engine hot loop, after structure updates:
    rationalized = rationalizer.rationalize(bar_idx, incremental_state, bar)
    snapshot.attach_rationalized_state(rationalized)

See: docs/specs/PLAY_VISION.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .types import Transition, RationalizedState, MarketRegime, TransitionFilter
from .transitions import TransitionManager
from .derived import DerivedStateComputer

if TYPE_CHECKING:
    from src.backtest.incremental.state import MultiTFIncrementalState
    from src.backtest.incremental.base import BarData


class StateRationalizer:
    """
    Layer 2 rationalization: transitions, derived state, regime detection.

    Pure computation class. Engine calls rationalize() after structure updates.
    Delegates to specialized components for modularity:
    - TransitionManager: Transition detection and history
    - DerivedStateComputer: Derived values (W2-P3)
    - ConflictResolver: Conflict resolution (W2-P4)

    Architecture:
        - rationalize() is pure: (state, bar) -> RationalizedState
        - No control flow about when to run - engine decides
        - Components maintain internal state for their computations

    Example:
        >>> rationalizer = StateRationalizer()
        >>> rationalized = rationalizer.rationalize(bar_idx, incremental_state, bar)
        >>> print(rationalized.transitions)
        [Transition(detector='swing', field='high_level', ...)]

    Attributes:
        _transition_manager: Handles transition detection and history
        _history_depth: Max transitions to keep in history
    """

    def __init__(self, history_depth: int = 1000) -> None:
        """Initialize the rationalizer.

        Args:
            history_depth: Maximum transitions to keep in history buffer
        """
        self._transition_manager = TransitionManager(history_depth=history_depth)
        self._derived_computer = DerivedStateComputer()
        self._history_depth = history_depth

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
        # Detect transitions (delegated to TransitionManager)
        transitions = self._transition_manager.detect_transitions(
            bar_idx=bar_idx,
            incremental_state=incremental_state,
        )

        # Compute derived values
        derived = self._compute_derived_values(incremental_state, bar)

        # Classify regime
        regime = self._classify_regime(incremental_state, bar)

        return RationalizedState(
            bar_idx=bar_idx,
            transitions=tuple(transitions),
            derived_values=derived,
            regime=regime,
        )

    def _compute_derived_values(
        self,
        incremental_state: "MultiTFIncrementalState",
        bar: "BarData",
    ) -> dict[str, Any]:
        """Compute derived values from current state.

        Delegates to DerivedStateComputer.

        Computes:
        - confluence_score: Signal alignment (0.0-1.0)
        - alignment: HTF/MTF/LTF agreement
        - momentum: Aggregate momentum signal
        - structure_stability: Recent change frequency
        """
        return self._derived_computer.compute(incremental_state, bar)

    def _classify_regime(
        self,
        incremental_state: "MultiTFIncrementalState",
        bar: "BarData",
    ) -> MarketRegime:
        """Classify current market regime.

        Delegates to DerivedStateComputer.

        Returns:
        - TRENDING_UP: Strong uptrend
        - TRENDING_DOWN: Strong downtrend
        - RANGING: Low volatility, no trend
        - VOLATILE: High volatility, no clear trend
        """
        return self._derived_computer.classify_regime(incremental_state, bar)

    def get_recent_transitions(
        self,
        count: int | None = None,
        detector: str | None = None,
        field: str | None = None,
    ) -> list[Transition]:
        """Query recent transitions from history.

        Delegates to TransitionManager.

        Args:
            count: Max transitions to return (None = all)
            detector: Filter by detector name
            field: Filter by field name

        Returns:
            List of matching transitions (most recent last)
        """
        filter_spec = TransitionFilter(detector=detector, field=field)
        return self._transition_manager.get_history(
            filter_spec=filter_spec,
            count=count,
        )

    def get_transitions_since(
        self,
        bar_idx: int,
        detector: str | None = None,
    ) -> list[Transition]:
        """Get all transitions since a given bar index.

        Delegates to TransitionManager.

        Args:
            bar_idx: Starting bar index (inclusive)
            detector: Filter by detector name (None = all)

        Returns:
            List of transitions since bar_idx
        """
        return self._transition_manager.get_transitions_since(
            bar_idx=bar_idx,
            detector=detector,
        )

    def reset(self) -> None:
        """Reset all state.

        Call when starting a new backtest run.
        """
        self._transition_manager.reset()

    @property
    def transition_history_size(self) -> int:
        """Current size of transition history."""
        return self._transition_manager.history_size

    @property
    def transition_manager(self) -> TransitionManager:
        """Access to the TransitionManager for advanced queries."""
        return self._transition_manager
