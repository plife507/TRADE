"""
Block State Container (Stage 7).

BlockState is the unified container for all per-bar state:
- SignalState: Signal lifecycle (NONE -> CONFIRMED -> CONSUMED)
- ActionState: Order lifecycle (IDLE -> ACTIONABLE -> FILLED)
- GateResult: Gate evaluation result

This is the primary interface for state tracking in the engine loop.

RECORD-ONLY MODE:
- BlockState captures decision flow without affecting outcomes
- is_actionable is observational (doesn't trigger trades)
- Deterministic: same inputs -> same BlockState
"""

from dataclasses import dataclass, field

from src.backtest.runtime.state_types import (
    SignalStateValue,
    ActionStateValue,
    GateResult,
    GateCode,
)
from src.backtest.runtime.signal_state import SignalState
from src.backtest.runtime.action_state import ActionState


@dataclass
class BlockState:
    """
    Unified state container for a single bar.

    Combines signal, action, and gate states into a single
    queryable object for engine decision flow.

    Attributes:
        bar_idx: Bar index this state applies to
        signal: Signal state (lifecycle tracking)
        action: Action state (order lifecycle)
        gate: Gate evaluation result
        raw_signal_direction: Raw signal from rule evaluator (before gates)
    """
    bar_idx: int = 0
    signal: SignalState = field(default_factory=SignalState)
    action: ActionState = field(default_factory=ActionState)
    gate: GateResult = field(default_factory=GateResult.pass_)
    raw_signal_direction: int = 0  # 1=long, -1=short, 0=none

    @property
    def is_actionable(self) -> bool:
        """
        Check if conditions allow action.

        True when:
        - Signal is CONFIRMED
        - Gate result is PASS
        - Action is not already in progress

        RECORD-ONLY: This is observational, not a trigger.
        """
        return (
            self.signal.value == SignalStateValue.CONFIRMED
            and self.gate.passed
            and self.action.value == ActionStateValue.IDLE
        )

    @property
    def is_blocked(self) -> bool:
        """Check if action is blocked by gates."""
        return not self.gate.passed

    @property
    def block_reason(self) -> str | None:
        """Get reason for block (if blocked)."""
        if self.gate.passed:
            return None
        return self.gate.reason

    @property
    def block_code(self) -> GateCode:
        """Get gate code (G_PASS if not blocked)."""
        return self.gate.code

    @property
    def signal_detected(self) -> bool:
        """Check if a signal was detected (any state except NONE)."""
        return self.signal.value != SignalStateValue.NONE

    @property
    def signal_confirmed(self) -> bool:
        """Check if signal is confirmed."""
        return self.signal.value == SignalStateValue.CONFIRMED

    @property
    def signal_consumed(self) -> bool:
        """Check if signal was consumed (action taken)."""
        return self.signal.value == SignalStateValue.CONSUMED

    @property
    def action_filled(self) -> bool:
        """Check if action was filled."""
        return self.action.value == ActionStateValue.FILLED

    @property
    def action_rejected(self) -> bool:
        """Check if action was rejected."""
        return self.action.value == ActionStateValue.REJECTED

    def summary(self) -> str:
        """Human-readable summary for debugging."""
        parts = [f"bar={self.bar_idx}"]

        if self.signal.value != SignalStateValue.NONE:
            direction = {1: "LONG", -1: "SHORT", 0: "NONE"}.get(
                self.signal.direction, "?"
            )
            parts.append(f"signal={self.signal.value.name}({direction})")

        if self.action.value != ActionStateValue.IDLE:
            parts.append(f"action={self.action.value.name}")

        if not self.gate.passed:
            parts.append(f"blocked={self.gate.code.name}")

        return " | ".join(parts)


def create_block_state(
    bar_idx: int,
    signal: SignalState,
    action: ActionState,
    gate: GateResult,
    raw_signal_direction: int = 0,
) -> BlockState:
    """
    Factory function for BlockState.

    Args:
        bar_idx: Current bar index
        signal: Signal state
        action: Action state
        gate: Gate evaluation result
        raw_signal_direction: Raw signal from evaluator

    Returns:
        New BlockState instance
    """
    return BlockState(
        bar_idx=bar_idx,
        signal=signal,
        action=action,
        gate=gate,
        raw_signal_direction=raw_signal_direction,
    )


def reset_block_state(bar_idx: int = 0) -> BlockState:
    """Create a fresh BlockState with all states reset."""
    return BlockState(
        bar_idx=bar_idx,
        signal=SignalState(),
        action=ActionState(),
        gate=GateResult.pass_(),
        raw_signal_direction=0,
    )
