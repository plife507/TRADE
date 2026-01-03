"""
State Type Primitives for Unified State Tracking (Stage 7).

This module defines the core enums and data structures for tracking
signal/action/gate state throughout the backtest engine loop.

RECORD-ONLY MODE (v1):
- State tracking captures decision flow without affecting trade outcomes
- All state transitions are deterministic (same input -> same state)
- No behavioral changes to existing engine logic

Design Principles:
- Enums use explicit int values for array storage and determinism
- GateResult is immutable after creation
- All types are serialization-friendly (no complex objects)
"""

from dataclasses import dataclass, field
from enum import IntEnum


class SignalStateValue(IntEnum):
    """
    Signal lifecycle states.

    Flow: NONE -> CANDIDATE -> CONFIRMING -> CONFIRMED -> CONSUMED
                                         |-> EXPIRED (timeout)

    Stage 7 uses ONE-BAR CONFIRMATION (v1):
    - CANDIDATE + confirmation_bars=1 -> CONFIRMED on same bar
    - No multi-bar confirmation queue yet
    """
    NONE = 0           # No signal detected
    CANDIDATE = 1      # Signal detected, awaiting confirmation
    CONFIRMING = 2     # In confirmation window (reserved for multi-bar)
    CONFIRMED = 3      # Signal confirmed, ready for action
    EXPIRED = 4        # Confirmation window elapsed without confirm
    CONSUMED = 5       # Signal acted upon (order submitted)


class ActionStateValue(IntEnum):
    """
    Order/action lifecycle states.

    Flow: IDLE -> ACTIONABLE -> SIZING -> SUBMITTED -> FILLED
                                                   |-> REJECTED
                                                   |-> CANCELED

    Maps to existing engine flow:
    - IDLE: No pending action
    - ACTIONABLE: Confirmed signal + gates passed
    - SIZING: Position sizing computed
    - SUBMITTED: Order sent to exchange
    - FILLED/REJECTED/CANCELED: Terminal states
    """
    IDLE = 0           # No pending action
    ACTIONABLE = 1     # Ready to act (signal confirmed + gates passed)
    SIZING = 2         # Computing position size
    SUBMITTED = 3      # Order submitted to exchange
    FILLED = 4         # Order filled (terminal)
    REJECTED = 5       # Order rejected (terminal)
    CANCELED = 6       # Order canceled (terminal)


class GateCode(IntEnum):
    """
    Gate evaluation result codes.

    G_PASS (0) = all gates passed, action allowed.
    Non-zero codes indicate why action was blocked.

    Codes are additive-only (never renumber existing codes).

    Each code has a human-readable description accessible via the
    `description` property or `get_description()` class method.
    """
    G_PASS = 0                  # All gates passed
    G_WARMUP_REMAINING = 1      # Still in warmup period
    G_HISTORY_NOT_READY = 2     # Insufficient history for indicators
    G_CACHE_NOT_READY = 3       # Feature cache not populated
    G_RISK_BLOCK = 4            # Risk policy blocked action
    G_MAX_DRAWDOWN = 5          # Max drawdown limit hit
    G_INSUFFICIENT_MARGIN = 6   # Insufficient margin for position
    G_COOLDOWN_ACTIVE = 7       # Post-trade cooldown period
    G_POSITION_LIMIT = 8        # Max position count reached
    G_EXPOSURE_LIMIT = 9        # Max exposure limit reached

    @property
    def description(self) -> str:
        """Return human-readable description for this gate code."""
        return _GATE_DESCRIPTIONS[self]

    @classmethod
    def get_description(cls, code: "GateCode") -> str:
        """Return human-readable description for a gate code."""
        return _GATE_DESCRIPTIONS.get(code, f"Gate failed: {code.name}")


# Internal mapping - not part of public API
_GATE_DESCRIPTIONS: dict[GateCode, str] = {
    GateCode.G_PASS: "All gates passed",
    GateCode.G_WARMUP_REMAINING: "Warmup period not complete",
    GateCode.G_HISTORY_NOT_READY: "Insufficient bar history for indicators",
    GateCode.G_CACHE_NOT_READY: "Feature cache not yet populated",
    GateCode.G_RISK_BLOCK: "Risk policy blocked this action",
    GateCode.G_MAX_DRAWDOWN: "Maximum drawdown limit reached",
    GateCode.G_INSUFFICIENT_MARGIN: "Insufficient margin for position size",
    GateCode.G_COOLDOWN_ACTIVE: "Post-trade cooldown period active",
    GateCode.G_POSITION_LIMIT: "Maximum open positions reached",
    GateCode.G_EXPOSURE_LIMIT: "Maximum exposure limit reached",
}

# Backward-compatible alias (deprecated - use GateCode.description or GateCode.get_description())
GATE_CODE_DESCRIPTIONS: dict[GateCode, str] = _GATE_DESCRIPTIONS


@dataclass(frozen=True)
class GateResult:
    """
    Immutable result of gate evaluation.

    Attributes:
        passed: True if all gates passed
        code: Primary gate code (G_PASS or first failure)
        codes: All gate codes evaluated (for multi-gate tracking)
        reason: Human-readable explanation (optional)

    Usage:
        result = GateResult.pass_()
        result = GateResult.fail_(GateCode.G_WARMUP_REMAINING)
        if result.passed:
            # proceed with action
    """
    passed: bool
    code: GateCode
    codes: tuple[GateCode, ...] = field(default_factory=tuple)
    reason: str | None = None

    @classmethod
    def pass_(cls) -> "GateResult":
        """Create a passing gate result."""
        return cls(passed=True, code=GateCode.G_PASS, codes=(GateCode.G_PASS,))

    @classmethod
    def fail_(
        cls,
        code: GateCode,
        reason: str | None = None,
        additional_codes: tuple[GateCode, ...] | None = None,
    ) -> "GateResult":
        """
        Create a failing gate result.

        Args:
            code: Primary failure code
            reason: Optional human-readable explanation
            additional_codes: Other gates that also failed (if multi-gate eval)
        """
        codes = (code,) if additional_codes is None else (code,) + additional_codes
        if reason is None:
            reason = GateCode.get_description(code)
        return cls(passed=False, code=code, codes=codes, reason=reason)

    def __repr__(self) -> str:
        if self.passed:
            return "GateResult(PASS)"
        return f"GateResult(FAIL: {self.code.name}, reason={self.reason!r})"


# Type aliases for clarity
SignalState = SignalStateValue  # Will be replaced by SignalState class
ActionState = ActionStateValue  # Will be replaced by ActionState class
