"""
Signal State Machine (Stage 7).

Tracks signal lifecycle from detection through consumption.

State Flow:
    NONE -> CANDIDATE (signal detected)
    CANDIDATE -> CONFIRMING (multi-bar confirmation, reserved)
    CANDIDATE -> CONFIRMED (one-bar confirmation, v1)
    CONFIRMING -> CONFIRMED (confirmation complete)
    CONFIRMING -> EXPIRED (confirmation timeout)
    CONFIRMED -> CONSUMED (action taken)
    CONFIRMED -> EXPIRED (action window timeout)

ONE-BAR CONFIRMATION (v1):
- Signal detected on bar N -> CONFIRMED on bar N
- No multi-bar queuing in this version
- confirmation_bars param reserved for future use

RECORD-ONLY MODE:
- State tracking is observational only
- Does not affect trade decisions
- Deterministic: same inputs -> same state sequence
"""

from dataclasses import dataclass, field

from src.backtest.runtime.state_types import (
    SignalStateValue,
    GateResult,
    GateCode,
)


@dataclass
class SignalState:
    """
    Signal state container with metadata.

    Tracks the lifecycle of a trading signal from detection
    through consumption or expiration.

    Attributes:
        value: Current state (SignalStateValue enum)
        direction: Signal direction (1=long, -1=short, 0=none)
        detected_bar: Bar index when signal was first detected (-1 if none)
        confirmed_bar: Bar index when signal was confirmed (-1 if not confirmed)
        consumed_bar: Bar index when signal was consumed (-1 if not consumed)
        gate_result: Last gate evaluation result (for blocking reason)
        signal_id: Unique identifier for this signal instance
    """
    value: SignalStateValue = SignalStateValue.NONE
    direction: int = 0  # 1=long, -1=short, 0=none
    detected_bar: int = -1
    confirmed_bar: int = -1
    consumed_bar: int = -1
    gate_result: GateResult | None = None
    signal_id: int = 0  # Incremented per new signal

    def is_none(self) -> bool:
        """Check if no signal is active."""
        return self.value == SignalStateValue.NONE

    def is_candidate(self) -> bool:
        """Check if signal is awaiting confirmation."""
        return self.value == SignalStateValue.CANDIDATE

    def is_confirmed(self) -> bool:
        """Check if signal is confirmed and actionable."""
        return self.value == SignalStateValue.CONFIRMED

    def is_consumed(self) -> bool:
        """Check if signal has been acted upon."""
        return self.value == SignalStateValue.CONSUMED

    def is_terminal(self) -> bool:
        """Check if signal is in a terminal state."""
        return self.value in (SignalStateValue.EXPIRED, SignalStateValue.CONSUMED)

    def can_transition_to(self, target: SignalStateValue) -> bool:
        """Check if transition to target state is valid."""
        valid_transitions = SIGNAL_TRANSITIONS.get(self.value, set())
        return target in valid_transitions

    def bars_since_detected(self, current_bar: int) -> int:
        """Get bars elapsed since signal detection."""
        if self.detected_bar < 0:
            return -1
        return current_bar - self.detected_bar

    def bars_since_confirmed(self, current_bar: int) -> int:
        """Get bars elapsed since signal confirmation."""
        if self.confirmed_bar < 0:
            return -1
        return current_bar - self.confirmed_bar


# Valid state transitions
SIGNAL_TRANSITIONS: dict[SignalStateValue, set[SignalStateValue]] = {
    SignalStateValue.NONE: {SignalStateValue.CANDIDATE},
    SignalStateValue.CANDIDATE: {
        SignalStateValue.CONFIRMING,
        SignalStateValue.CONFIRMED,
        SignalStateValue.EXPIRED,
        SignalStateValue.NONE,  # Cancel/reset
    },
    SignalStateValue.CONFIRMING: {
        SignalStateValue.CONFIRMED,
        SignalStateValue.EXPIRED,
        SignalStateValue.NONE,  # Cancel/reset
    },
    SignalStateValue.CONFIRMED: {
        SignalStateValue.CONSUMED,
        SignalStateValue.EXPIRED,
        SignalStateValue.NONE,  # Cancel/reset
    },
    SignalStateValue.EXPIRED: {SignalStateValue.NONE},  # Reset only
    SignalStateValue.CONSUMED: {SignalStateValue.NONE},  # Reset only
}


def transition_signal_state(
    prev_state: SignalState,
    bar_idx: int,
    signal_detected: bool,
    signal_direction: int,
    gate_result: GateResult,
    action_taken: bool,
    next_signal_id: int,
    confirmation_bars: int = 1,  # v1: always 1
) -> SignalState:
    """
    Pure transition function for signal state.

    Computes next state based on current state and bar inputs.
    This is a pure function with no side effects.

    Args:
        prev_state: Previous signal state
        bar_idx: Current bar index
        signal_detected: Whether a new signal was detected this bar
        signal_direction: Signal direction (1=long, -1=short)
        gate_result: Result of gate evaluation
        action_taken: Whether an action was taken this bar
        next_signal_id: ID for new signals (caller manages counter)
        confirmation_bars: Bars required for confirmation (v1: always 1)

    Returns:
        New SignalState (never mutates prev_state)
    """
    current_value = prev_state.value

    # Terminal states reset to NONE
    if current_value in (SignalStateValue.EXPIRED, SignalStateValue.CONSUMED):
        if signal_detected:
            # New signal detected, start fresh
            return SignalState(
                value=SignalStateValue.CANDIDATE,
                direction=signal_direction,
                detected_bar=bar_idx,
                confirmed_bar=-1,
                consumed_bar=-1,
                gate_result=gate_result,
                signal_id=next_signal_id,
            )
        # Stay in terminal state until new signal
        return SignalState(
            value=SignalStateValue.NONE,
            direction=0,
            detected_bar=-1,
            confirmed_bar=-1,
            consumed_bar=-1,
            gate_result=None,
            signal_id=0,
        )

    # NONE: Check for new signal
    if current_value == SignalStateValue.NONE:
        if signal_detected:
            # v1: One-bar confirmation -> immediately CONFIRMED
            if confirmation_bars <= 1:
                return SignalState(
                    value=SignalStateValue.CONFIRMED,
                    direction=signal_direction,
                    detected_bar=bar_idx,
                    confirmed_bar=bar_idx,
                    consumed_bar=-1,
                    gate_result=gate_result,
                    signal_id=next_signal_id,
                )
            # Multi-bar confirmation (reserved for v2)
            return SignalState(
                value=SignalStateValue.CANDIDATE,
                direction=signal_direction,
                detected_bar=bar_idx,
                confirmed_bar=-1,
                consumed_bar=-1,
                gate_result=gate_result,
                signal_id=next_signal_id,
            )
        # No signal, stay NONE
        return prev_state

    # CANDIDATE: Check confirmation (reserved for multi-bar v2)
    if current_value == SignalStateValue.CANDIDATE:
        # v1: Should not reach here with confirmation_bars=1
        # But handle gracefully: promote to CONFIRMED
        return SignalState(
            value=SignalStateValue.CONFIRMED,
            direction=prev_state.direction,
            detected_bar=prev_state.detected_bar,
            confirmed_bar=bar_idx,
            consumed_bar=-1,
            gate_result=gate_result,
            signal_id=prev_state.signal_id,
        )

    # CONFIRMING: Reserved for multi-bar confirmation (v2)
    if current_value == SignalStateValue.CONFIRMING:
        # Promote to CONFIRMED (v1 fallback)
        return SignalState(
            value=SignalStateValue.CONFIRMED,
            direction=prev_state.direction,
            detected_bar=prev_state.detected_bar,
            confirmed_bar=bar_idx,
            consumed_bar=-1,
            gate_result=gate_result,
            signal_id=prev_state.signal_id,
        )

    # CONFIRMED: Check for action or expiration
    if current_value == SignalStateValue.CONFIRMED:
        if action_taken:
            return SignalState(
                value=SignalStateValue.CONSUMED,
                direction=prev_state.direction,
                detected_bar=prev_state.detected_bar,
                confirmed_bar=prev_state.confirmed_bar,
                consumed_bar=bar_idx,
                gate_result=gate_result,
                signal_id=prev_state.signal_id,
            )
        # Gate blocked - stay CONFIRMED (v1: no timeout)
        return SignalState(
            value=SignalStateValue.CONFIRMED,
            direction=prev_state.direction,
            detected_bar=prev_state.detected_bar,
            confirmed_bar=prev_state.confirmed_bar,
            consumed_bar=-1,
            gate_result=gate_result,
            signal_id=prev_state.signal_id,
        )

    # Fallback: return unchanged
    return prev_state


def reset_signal_state() -> SignalState:
    """Create a fresh NONE signal state."""
    return SignalState()
