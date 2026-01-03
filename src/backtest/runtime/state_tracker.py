"""
State Tracker (Stage 7) - Engine Integration Layer.

Orchestrates unified state tracking across the engine hot loop.

RECORD-ONLY MODE:
- Captures signal/action/gate state without affecting trade outcomes
- State transitions are deterministic (same input -> same sequence)
- No behavioral changes to existing engine logic
- Optional: controlled by record_state_tracking flag

Integration Points:
1. on_bar_start(bar_idx) - Reset per-bar state
2. on_signal_evaluated(direction) - Record raw signal from evaluator
3. on_gates_checked(warmup_ok, history_ok) - Record gate evaluation
4. on_action_taken(filled) - Record action outcome
5. on_bar_end() - Finalize and store block state

Usage in engine:
    if self._state_tracker:
        self._state_tracker.on_bar_start(i)
        self._state_tracker.on_signal_evaluated(signal_direction)
        self._state_tracker.on_gates_checked(warmup_ok, history_ok)
        ...
        self._state_tracker.on_bar_end()
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from src.backtest.runtime.state_types import (
    SignalStateValue,
    ActionStateValue,
    GateCode,
    GateResult,
)
from src.backtest.runtime.signal_state import (
    SignalState,
    transition_signal_state,
    reset_signal_state,
)
from src.backtest.runtime.action_state import (
    ActionState,
    transition_action_state,
    reset_action_state,
)
from src.backtest.runtime.gate_state import (
    GateContext,
    evaluate_gates,
)
from src.backtest.runtime.block_state import (
    BlockState,
    create_block_state,
    reset_block_state,
)


@dataclass
class StateTrackerConfig:
    """
    Configuration for state tracker.

    Attributes:
        warmup_bars: Required warmup bars
        max_positions: Max allowed positions
        max_drawdown_pct: Max allowed drawdown percentage
        cooldown_bars: Post-trade cooldown bars
        max_history: Max block history entries (0 = unlimited, default 10000)
    """
    warmup_bars: int = 0
    max_positions: int = 100
    max_drawdown_pct: float = 100.0
    cooldown_bars: int = 0
    max_history: int = 10000  # Prevent unbounded memory growth


class StateTracker:
    """
    Unified state tracker for engine integration.

    Maintains state across bars and records block state history.
    All tracking is record-only - does not affect trade decisions.

    Attributes:
        config: Tracker configuration
        block_history: List of BlockState per bar
        signal_counter: Counter for signal IDs
    """

    def __init__(self, config: StateTrackerConfig | None = None):
        """
        Initialize state tracker.

        Args:
            config: Optional configuration (defaults used if None)
        """
        self.config = config or StateTrackerConfig()

        # State across bars
        self._signal_state = reset_signal_state()
        self._action_state = reset_action_state()
        self._signal_counter = 0

        # Per-bar accumulator
        self._current_bar_idx = 0
        self._raw_signal_direction = 0
        self._gate_context = GateContext()
        self._gate_result = GateResult.pass_()
        self._signal_detected = False
        self._action_taken = False
        self._order_filled = False
        self._order_rejected = False
        self._size_computed = False
        self._size_usdt = 0.0

        # History for auditing
        self.block_history: list[BlockState] = []
        self._block_index: dict[int, BlockState] = {}  # O(1) lookup by bar_idx

    def reset(self) -> None:
        """Reset all state for new backtest run."""
        self._signal_state = reset_signal_state()
        self._action_state = reset_action_state()
        self._signal_counter = 0
        self._current_bar_idx = 0
        self._raw_signal_direction = 0
        self._gate_context = GateContext()
        self._gate_result = GateResult.pass_()
        self._signal_detected = False
        self._action_taken = False
        self._order_filled = False
        self._order_rejected = False
        self._size_computed = False
        self._size_usdt = 0.0
        self.block_history = []
        self._block_index = {}

    def on_bar_start(self, bar_idx: int) -> None:
        """
        Called at start of each bar.

        Resets per-bar accumulators.

        Args:
            bar_idx: Current bar index
        """
        self._current_bar_idx = bar_idx
        self._raw_signal_direction = 0
        self._signal_detected = False
        self._action_taken = False
        self._order_filled = False
        self._order_rejected = False
        self._size_computed = False
        self._size_usdt = 0.0
        # Gate context reset with bar_idx
        self._gate_context = GateContext(bar_idx=bar_idx)

    def on_signal_evaluated(self, direction: int) -> None:
        """
        Called after strategy evaluation.

        Records raw signal direction from evaluator.

        Args:
            direction: Signal direction (1=long, -1=short, 0=none)
        """
        self._raw_signal_direction = direction
        self._signal_detected = direction != 0

    def on_warmup_check(self, warmup_ok: bool, warmup_end_idx: int) -> None:
        """
        Called after warmup check.

        Updates gate context with warmup status.

        Args:
            warmup_ok: Whether warmup is complete (current bar >= warmup_end_idx)
            warmup_end_idx: Bar index at which warmup ends (first tradeable bar)
                           This is an INDEX, not a count of warmup bars.
        """
        self._gate_context.warmup_bars = warmup_end_idx
        if not warmup_ok:
            # Bar index is less than warmup_end_idx
            pass  # gate evaluation will catch this

    def on_history_check(self, history_ok: bool, history_bars: int) -> None:
        """
        Called after history check.

        Updates gate context with history status.

        Args:
            history_ok: Whether history is ready
            history_bars: Available history bars
        """
        self._gate_context.history_bars = history_bars
        self._gate_context.cache_ready = history_ok

    def on_risk_check(
        self,
        passed: bool,
        reason: str | None = None,
        drawdown_pct: float = 0.0,
        available_margin: float = float('inf'),
        required_margin: float = 0.0,
    ) -> None:
        """
        Called after risk policy check.

        Updates gate context with risk status.

        Args:
            passed: Whether risk check passed
            reason: Reason if failed
            drawdown_pct: Current drawdown percentage
            available_margin: Available margin
            required_margin: Required margin
        """
        self._gate_context.risk_policy_passed = passed
        self._gate_context.risk_policy_reason = reason
        self._gate_context.current_drawdown_pct = drawdown_pct
        self._gate_context.max_drawdown_limit_pct = self.config.max_drawdown_pct
        self._gate_context.available_margin = available_margin
        self._gate_context.required_margin = required_margin

    def on_position_check(
        self,
        position_count: int,
        exposure_pct: float = 0.0,
    ) -> None:
        """
        Called with position/exposure info.

        Updates gate context.

        Args:
            position_count: Current open positions
            exposure_pct: Current exposure percentage
        """
        self._gate_context.position_count = position_count
        self._gate_context.max_positions = self.config.max_positions
        self._gate_context.current_exposure_pct = exposure_pct
        self._gate_context.max_exposure_pct = 100.0  # TODO: make configurable

    def on_sizing_computed(self, size_usdt: float) -> None:
        """
        Called after position sizing.

        Args:
            size_usdt: Computed position size
        """
        self._size_computed = True
        self._size_usdt = size_usdt

    def on_order_submitted(self) -> None:
        """Called when order is submitted."""
        self._action_taken = True

    def on_order_filled(self) -> None:
        """Called when order is filled."""
        self._order_filled = True

    def on_order_rejected(self, reason: str | None = None) -> None:
        """
        Called when order is rejected.

        Args:
            reason: Rejection reason
        """
        self._order_rejected = True

    def on_bar_end(self) -> BlockState:
        """
        Called at end of each bar.

        Evaluates gates, transitions state machines, and records block state.

        Returns:
            BlockState for this bar
        """
        # Evaluate gates
        self._gate_result = evaluate_gates(self._gate_context)

        # Transition signal state
        if self._signal_detected:
            self._signal_counter += 1

        new_signal_state = transition_signal_state(
            prev_state=self._signal_state,
            bar_idx=self._current_bar_idx,
            signal_detected=self._signal_detected,
            signal_direction=self._raw_signal_direction,
            gate_result=self._gate_result,
            action_taken=self._action_taken,
            next_signal_id=self._signal_counter,
            confirmation_bars=1,  # v1: one-bar confirmation
        )

        # Transition action state
        new_action_state = transition_action_state(
            prev_state=self._action_state,
            bar_idx=self._current_bar_idx,
            signal_confirmed=new_signal_state.value == SignalStateValue.CONFIRMED,
            signal_direction=new_signal_state.direction,
            gate_result=self._gate_result,
            size_computed=self._size_computed,
            size_usdt=self._size_usdt,
            order_submitted=self._action_taken,
            order_filled=self._order_filled,
            order_rejected=self._order_rejected,
        )

        # Create block state
        block_state = create_block_state(
            bar_idx=self._current_bar_idx,
            signal=new_signal_state,
            action=new_action_state,
            gate=self._gate_result,
            raw_signal_direction=self._raw_signal_direction,
        )

        # Update state for next bar
        self._signal_state = new_signal_state
        self._action_state = new_action_state

        # Record in history
        self.block_history.append(block_state)
        self._block_index[self._current_bar_idx] = block_state

        # Prune old history if max_history exceeded (prevents unbounded memory growth)
        # P2-006 FIX: More efficient pruning - only clean up index entries we remove
        max_hist = self.config.max_history
        if max_hist > 0 and len(self.block_history) > max_hist:
            # Calculate how many entries to remove
            excess = len(self.block_history) - max_hist
            # Get bar_idx values to remove from index (O(excess) instead of O(n))
            for i in range(excess):
                old_bar_idx = self.block_history[i].bar_idx
                self._block_index.pop(old_bar_idx, None)
            # Slice the history (creates new list - unavoidable with list)
            self.block_history = self.block_history[excess:]

        return block_state

    def get_current_signal_state(self) -> SignalState:
        """Get current signal state."""
        return self._signal_state

    def get_current_action_state(self) -> ActionState:
        """Get current action state."""
        return self._action_state

    def get_block_at(self, bar_idx: int) -> BlockState | None:
        """
        Get block state at specific bar.

        O(1) lookup via dict index.

        Args:
            bar_idx: Bar index

        Returns:
            BlockState or None if not found (or pruned from history)
        """
        return self._block_index.get(bar_idx)

    def summary_stats(self) -> dict[str, Any]:
        """
        Get summary statistics from block history.

        Returns:
            Dict with signal/action/gate statistics
        """
        if not self.block_history:
            return {}

        signals_detected = sum(1 for b in self.block_history if b.signal_detected)
        signals_confirmed = sum(1 for b in self.block_history if b.signal_confirmed)
        signals_consumed = sum(1 for b in self.block_history if b.signal_consumed)
        actions_filled = sum(1 for b in self.block_history if b.action_filled)
        gates_blocked = sum(1 for b in self.block_history if b.is_blocked)

        # Gate code breakdown
        gate_codes: dict[str, int] = {}
        for b in self.block_history:
            if b.is_blocked:
                code_name = b.block_code.name
                gate_codes[code_name] = gate_codes.get(code_name, 0) + 1

        return {
            "total_bars": len(self.block_history),
            "signals_detected": signals_detected,
            "signals_confirmed": signals_confirmed,
            "signals_consumed": signals_consumed,
            "actions_filled": actions_filled,
            "gates_blocked": gates_blocked,
            "gate_code_breakdown": gate_codes,
        }


def create_state_tracker(
    warmup_bars: int = 0,
    max_positions: int = 100,
    max_drawdown_pct: float = 100.0,
    cooldown_bars: int = 0,
    max_history: int = 10000,
) -> StateTracker:
    """
    Factory function for StateTracker.

    Args:
        warmup_bars: Required warmup bars
        max_positions: Max allowed positions
        max_drawdown_pct: Max allowed drawdown percentage
        cooldown_bars: Post-trade cooldown bars
        max_history: Max block history entries (0 = unlimited)

    Returns:
        Configured StateTracker instance
    """
    config = StateTrackerConfig(
        warmup_bars=warmup_bars,
        max_positions=max_positions,
        max_drawdown_pct=max_drawdown_pct,
        cooldown_bars=cooldown_bars,
        max_history=max_history,
    )
    return StateTracker(config)
