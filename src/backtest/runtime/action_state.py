"""
Action State Machine (Stage 7).

Tracks order/action lifecycle from signal confirmation through execution.

State Flow:
    IDLE -> ACTIONABLE (signal confirmed + gates passed)
    ACTIONABLE -> SIZING (computing position size)
    SIZING -> SUBMITTED (order sent to exchange)
    SUBMITTED -> FILLED (order executed)
    SUBMITTED -> REJECTED (order rejected)
    SUBMITTED -> CANCELED (order canceled)

RECORD-ONLY MODE:
- State tracking is observational only
- Maps to existing engine order flow without changing it
- Deterministic: same inputs -> same state sequence
"""

from dataclasses import dataclass
from typing import Optional

from src.backtest.runtime.state_types import (
    ActionStateValue,
    GateResult,
)


@dataclass
class ActionState:
    """
    Action state container with metadata.

    Tracks the lifecycle of an order/action from signal confirmation
    through execution or rejection.

    Attributes:
        value: Current state (ActionStateValue enum)
        direction: Action direction (1=long, -1=short, 0=none)
        signal_id: ID of the signal that triggered this action
        size_usdt: Computed position size (0 if not sized)
        submitted_bar: Bar index when order was submitted (-1 if not submitted)
        filled_bar: Bar index when order was filled (-1 if not filled)
        reject_reason: Reason for rejection (if rejected)
    """
    value: ActionStateValue = ActionStateValue.IDLE
    direction: int = 0
    signal_id: int = 0
    size_usdt: float = 0.0
    submitted_bar: int = -1
    filled_bar: int = -1
    reject_reason: Optional[str] = None

    def is_idle(self) -> bool:
        """Check if no action is pending."""
        return self.value == ActionStateValue.IDLE

    def is_actionable(self) -> bool:
        """Check if ready to act."""
        return self.value == ActionStateValue.ACTIONABLE

    def is_submitted(self) -> bool:
        """Check if order has been submitted."""
        return self.value == ActionStateValue.SUBMITTED

    def is_terminal(self) -> bool:
        """Check if action is in a terminal state."""
        return self.value in (
            ActionStateValue.FILLED,
            ActionStateValue.REJECTED,
            ActionStateValue.CANCELED,
        )

    def can_transition_to(self, target: ActionStateValue) -> bool:
        """Check if transition to target state is valid."""
        valid_transitions = ACTION_TRANSITIONS.get(self.value, set())
        return target in valid_transitions


# Valid state transitions
ACTION_TRANSITIONS: dict[ActionStateValue, set[ActionStateValue]] = {
    ActionStateValue.IDLE: {ActionStateValue.ACTIONABLE},
    ActionStateValue.ACTIONABLE: {
        ActionStateValue.SIZING,
        ActionStateValue.IDLE,  # Gate blocked
    },
    ActionStateValue.SIZING: {
        ActionStateValue.SUBMITTED,
        ActionStateValue.REJECTED,  # Size validation failed
        ActionStateValue.IDLE,  # Canceled
    },
    ActionStateValue.SUBMITTED: {
        ActionStateValue.FILLED,
        ActionStateValue.REJECTED,
        ActionStateValue.CANCELED,
    },
    ActionStateValue.FILLED: {ActionStateValue.IDLE},  # Reset for next action
    ActionStateValue.REJECTED: {ActionStateValue.IDLE},  # Reset for next action
    ActionStateValue.CANCELED: {ActionStateValue.IDLE},  # Reset for next action
}


def transition_action_state(
    prev_state: ActionState,
    bar_idx: int,
    signal_confirmed: bool,
    signal_direction: int,
    signal_id: int,
    gate_result: GateResult,
    size_computed: bool,
    size_usdt: float,
    order_submitted: bool,
    order_filled: bool,
    order_rejected: bool,
    reject_reason: Optional[str] = None,
) -> ActionState:
    """
    Pure transition function for action state.

    Computes next state based on current state and bar inputs.
    This is a pure function with no side effects.

    Args:
        prev_state: Previous action state
        bar_idx: Current bar index
        signal_confirmed: Whether a confirmed signal exists
        signal_direction: Signal direction (1=long, -1=short)
        signal_id: ID of the triggering signal
        gate_result: Result of gate evaluation
        size_computed: Whether position size was computed
        size_usdt: Computed position size
        order_submitted: Whether order was submitted this bar
        order_filled: Whether order was filled this bar
        order_rejected: Whether order was rejected this bar
        reject_reason: Reason for rejection (if any)

    Returns:
        New ActionState (never mutates prev_state)
    """
    current_value = prev_state.value

    # Terminal states reset to IDLE
    if current_value in (
        ActionStateValue.FILLED,
        ActionStateValue.REJECTED,
        ActionStateValue.CANCELED,
    ):
        if signal_confirmed and gate_result.passed:
            # New actionable signal
            return ActionState(
                value=ActionStateValue.ACTIONABLE,
                direction=signal_direction,
                signal_id=signal_id,
                size_usdt=0.0,
                submitted_bar=-1,
                filled_bar=-1,
                reject_reason=None,
            )
        # Reset to IDLE
        return ActionState()

    # IDLE: Check for actionable signal
    if current_value == ActionStateValue.IDLE:
        if signal_confirmed and gate_result.passed:
            return ActionState(
                value=ActionStateValue.ACTIONABLE,
                direction=signal_direction,
                signal_id=signal_id,
                size_usdt=0.0,
                submitted_bar=-1,
                filled_bar=-1,
                reject_reason=None,
            )
        # Stay IDLE
        return prev_state

    # ACTIONABLE: Check for sizing
    if current_value == ActionStateValue.ACTIONABLE:
        if not gate_result.passed:
            # Gate blocked, back to IDLE
            return ActionState(
                value=ActionStateValue.IDLE,
                direction=0,
                signal_id=0,
                size_usdt=0.0,
                submitted_bar=-1,
                filled_bar=-1,
                reject_reason=gate_result.reason,
            )
        if size_computed:
            return ActionState(
                value=ActionStateValue.SIZING,
                direction=prev_state.direction,
                signal_id=prev_state.signal_id,
                size_usdt=size_usdt,
                submitted_bar=-1,
                filled_bar=-1,
                reject_reason=None,
            )
        # Stay ACTIONABLE (sizing pending)
        return prev_state

    # SIZING: Check for submission
    if current_value == ActionStateValue.SIZING:
        if order_rejected:
            return ActionState(
                value=ActionStateValue.REJECTED,
                direction=prev_state.direction,
                signal_id=prev_state.signal_id,
                size_usdt=prev_state.size_usdt,
                submitted_bar=-1,
                filled_bar=-1,
                reject_reason=reject_reason or "Size validation failed",
            )
        if order_submitted:
            return ActionState(
                value=ActionStateValue.SUBMITTED,
                direction=prev_state.direction,
                signal_id=prev_state.signal_id,
                size_usdt=prev_state.size_usdt,
                submitted_bar=bar_idx,
                filled_bar=-1,
                reject_reason=None,
            )
        # Stay SIZING
        return prev_state

    # SUBMITTED: Check for fill/reject
    if current_value == ActionStateValue.SUBMITTED:
        if order_filled:
            return ActionState(
                value=ActionStateValue.FILLED,
                direction=prev_state.direction,
                signal_id=prev_state.signal_id,
                size_usdt=prev_state.size_usdt,
                submitted_bar=prev_state.submitted_bar,
                filled_bar=bar_idx,
                reject_reason=None,
            )
        if order_rejected:
            return ActionState(
                value=ActionStateValue.REJECTED,
                direction=prev_state.direction,
                signal_id=prev_state.signal_id,
                size_usdt=prev_state.size_usdt,
                submitted_bar=prev_state.submitted_bar,
                filled_bar=-1,
                reject_reason=reject_reason or "Order rejected",
            )
        # Stay SUBMITTED (order pending)
        return prev_state

    # Fallback: return unchanged
    return prev_state


def reset_action_state() -> ActionState:
    """Create a fresh IDLE action state."""
    return ActionState()
