"""
Conflict Resolver - Priority rules and veto handling for signal conflicts.

Architecture Principle: Pure Math
- Input: List of signals, resolution config
- Output: Resolved signal or None (vetoed)
- No side effects, stateless computation
- Engine orchestrates invocation

Resolution Strategies:
- FIRST_WINS: First signal takes precedence
- PRIORITY: Higher timeframe wins
- UNANIMOUS: All must agree, else vetoed

Veto Conditions:
- zone_broken: Any broken zone vetoes entry
- trend_reversal: Trend flip vetoes continuation
- Custom veto rules from Play config

See: docs/specs/PLAY_VISION.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.structures import MultiTFIncrementalState


class ResolutionStrategy(Enum):
    """Signal conflict resolution strategy."""
    FIRST_WINS = "first_wins"
    PRIORITY = "priority"
    UNANIMOUS = "unanimous"


class VetoCondition(Enum):
    """Standard veto conditions."""
    ZONE_BROKEN = "zone_broken"
    TREND_REVERSAL = "trend_reversal"
    CONFLICTING_HIGH_TF = "conflicting_high_tf"
    LOW_CONFLUENCE = "low_confluence"


@dataclass(frozen=True, slots=True)
class Signal:
    """Represents a trading signal from a timeframe.

    Immutable signal container for conflict resolution.

    Attributes:
        action: Signal action (entry_long, entry_short, exit_long, exit_short)
        timeframe: Source timeframe (low_tf, med_tf, high_tf)
        priority: Priority level (higher = more important)
        confidence: Signal confidence (0.0-1.0)
        metadata: Additional signal data
    """
    action: str
    timeframe: str
    priority: int = 0
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_entry(self) -> bool:
        """Check if this is an entry signal."""
        return self.action.startswith("entry_")

    @property
    def is_exit(self) -> bool:
        """Check if this is an exit signal."""
        return self.action.startswith("exit_")

    @property
    def direction(self) -> str:
        """Get signal direction: 'long' or 'short'."""
        if "long" in self.action:
            return "long"
        if "short" in self.action:
            return "short"
        return "neutral"


@dataclass(frozen=True, slots=True)
class ResolutionConfig:
    """Configuration for conflict resolution.

    Parsed from Play YAML `rationalization:` section.

    Example YAML:
        rationalization:
          strategy: priority
          priority_order: [high_tf, med_tf, exec]
          veto_on: [zone_broken, trend_reversal]
          min_confluence: 0.5
    """
    strategy: ResolutionStrategy = ResolutionStrategy.PRIORITY
    priority_order: tuple[str, ...] = ("high_tf", "med_tf", "exec")
    veto_on: tuple[VetoCondition, ...] = field(default_factory=tuple)
    min_confluence: float = 0.0
    require_high_tf_alignment: bool = False

    @classmethod
    def from_dict(cls, config: dict[str, Any]) -> "ResolutionConfig":
        """Create config from Play YAML dict."""
        strategy_str = config.get("strategy", "priority")
        strategy = ResolutionStrategy(strategy_str)

        priority_order = tuple(config.get("priority_order", ["high_tf", "med_tf", "exec"]))

        veto_strs = config.get("veto_on", [])
        veto_on = tuple(VetoCondition(v) for v in veto_strs)

        return cls(
            strategy=strategy,
            priority_order=priority_order,
            veto_on=veto_on,
            min_confluence=config.get("min_confluence", 0.0),
            require_high_tf_alignment=config.get("require_high_tf_alignment", False),
        )


@dataclass
class ResolutionResult:
    """Result of conflict resolution.

    Attributes:
        resolved_signal: The winning signal, or None if vetoed
        vetoed: Whether the signal was vetoed
        veto_reason: Reason for veto if applicable
        contributing_signals: All signals that contributed to resolution
    """
    resolved_signal: Signal | None
    vetoed: bool = False
    veto_reason: str | None = None
    contributing_signals: tuple[Signal, ...] = field(default_factory=tuple)


class ConflictResolver:
    """
    Resolves conflicts between signals from different timeframes.

    Pure computation class. Applies resolution strategy and veto rules
    to determine winning signal.

    Strategies:
        FIRST_WINS: First signal in list wins (order determined by caller)
        PRIORITY: Higher priority wins (based on priority_order config)
        UNANIMOUS: All signals must agree, else vetoed

    Example:
        >>> resolver = ConflictResolver(config)
        >>> result = resolver.resolve(signals, incremental_state)
        >>> if not result.vetoed:
        ...     execute(result.resolved_signal)
    """

    def __init__(self, config: ResolutionConfig | None = None) -> None:
        """Initialize the resolver.

        Args:
            config: Resolution configuration (defaults to PRIORITY strategy)
        """
        self._config = config or ResolutionConfig()
        # Build priority map from config
        self._priority_map = {
            tf: len(self._config.priority_order) - i
            for i, tf in enumerate(self._config.priority_order)
        }

    def resolve(
        self,
        signals: list[Signal],
        incremental_state: "MultiTFIncrementalState" | None = None,
        derived_values: dict[str, Any] | None = None,
    ) -> ResolutionResult:
        """
        Resolve conflicts between signals.

        Pure function: (signals, state, derived) -> ResolutionResult

        Args:
            signals: List of signals to resolve
            incremental_state: Current structure state (for veto checks)
            derived_values: Derived values (for confluence check)

        Returns:
            ResolutionResult with resolved signal or veto info
        """
        if not signals:
            return ResolutionResult(resolved_signal=None)

        # Apply veto checks first
        veto_result = self._check_veto_conditions(
            signals=signals,
            incremental_state=incremental_state,
            derived_values=derived_values,
        )
        if veto_result is not None:
            return veto_result

        # Apply resolution strategy
        match self._config.strategy:
            case ResolutionStrategy.FIRST_WINS:
                resolved = self._resolve_first_wins(signals)
            case ResolutionStrategy.PRIORITY:
                resolved = self._resolve_priority(signals)
            case ResolutionStrategy.UNANIMOUS:
                resolved = self._resolve_unanimous(signals)
            case _:
                resolved = self._resolve_priority(signals)

        return ResolutionResult(
            resolved_signal=resolved,
            vetoed=resolved is None,
            veto_reason="No consensus" if resolved is None else None,
            contributing_signals=tuple(signals),
        )

    def _check_veto_conditions(
        self,
        signals: list[Signal],
        incremental_state: "MultiTFIncrementalState" | None,
        derived_values: dict[str, Any] | None,
    ) -> ResolutionResult | None:
        """Check veto conditions. Returns ResolutionResult if vetoed."""

        # Check min confluence
        if self._config.min_confluence > 0 and derived_values:
            confluence = derived_values.get("confluence_score", 0.0)
            if confluence < self._config.min_confluence:
                return ResolutionResult(
                    resolved_signal=None,
                    vetoed=True,
                    veto_reason=f"Low confluence: {confluence:.2f} < {self._config.min_confluence:.2f}",
                    contributing_signals=tuple(signals),
                )

        # Check high_tf alignment if required
        if self._config.require_high_tf_alignment and derived_values:
            alignment = derived_values.get("alignment", 0.0)
            if alignment < 0.5:
                return ResolutionResult(
                    resolved_signal=None,
                    vetoed=True,
                    veto_reason=f"high_tf not aligned: {alignment:.2f}",
                    contributing_signals=tuple(signals),
                )

        # Check configured veto conditions
        for veto in self._config.veto_on:
            if self._is_veto_triggered(veto, incremental_state):
                return ResolutionResult(
                    resolved_signal=None,
                    vetoed=True,
                    veto_reason=f"Veto: {veto.value}",
                    contributing_signals=tuple(signals),
                )

        return None  # No veto

    def _is_veto_triggered(
        self,
        veto: VetoCondition,
        incremental_state: "MultiTFIncrementalState" | None,
    ) -> bool:
        """Check if a veto condition is triggered."""
        if incremental_state is None:
            return False

        match veto:
            case VetoCondition.ZONE_BROKEN:
                return self._check_zone_broken(incremental_state)
            case VetoCondition.TREND_REVERSAL:
                return self._check_trend_reversal(incremental_state)
            case VetoCondition.CONFLICTING_HIGH_TF:
                return self._check_conflicting_high_tf(incremental_state)
            case VetoCondition.LOW_CONFLUENCE:
                return False  # Handled separately
            case _:
                return False

    def _check_zone_broken(
        self,
        incremental_state: "MultiTFIncrementalState",
    ) -> bool:
        """Check if any zone is broken."""
        try:
            exec_state = incremental_state.exec
            for detector_key in exec_state.list_structures():
                if "zone" in detector_key.lower():
                    detector = exec_state.structures[detector_key]
                    state = detector.get_value("state")
                    if state == "BROKEN":
                        return True
        except (KeyError, AttributeError):
            pass
        return False

    def _check_trend_reversal(
        self,
        incremental_state: "MultiTFIncrementalState",
    ) -> bool:
        """Check if trend recently reversed.

        Would need transition history - placeholder implementation.
        """
        # TODO: Check transition history for recent trend direction change
        return False

    def _check_conflicting_high_tf(
        self,
        incremental_state: "MultiTFIncrementalState",
    ) -> bool:
        """Check if high_tf trends conflict with exec."""
        try:
            exec_trend = self._get_trend_direction(incremental_state.exec)

            for tf_name, tf_state in incremental_state.high_tf.items():
                high_tf_trend = self._get_trend_direction(tf_state)
                if high_tf_trend is not None and exec_trend is not None:
                    if high_tf_trend != exec_trend and high_tf_trend != 0 and exec_trend != 0:
                        return True
        except (KeyError, AttributeError):
            pass
        return False

    def _get_trend_direction(self, tf_state: Any) -> int | None:
        """Get trend direction from TF state."""
        try:
            for detector_key in tf_state.list_structures():
                if "trend" in detector_key.lower():
                    detector = tf_state.structures[detector_key]
                    return detector.get_value("direction")
        except (KeyError, AttributeError):
            pass
        return None

    def _resolve_first_wins(self, signals: list[Signal]) -> Signal | None:
        """First signal wins."""
        return signals[0] if signals else None

    def _resolve_priority(self, signals: list[Signal]) -> Signal | None:
        """Highest priority signal wins."""
        if not signals:
            return None

        # Sort by priority (higher first)
        def get_priority(s: Signal) -> int:
            return self._priority_map.get(s.timeframe, 0)

        sorted_signals = sorted(signals, key=get_priority, reverse=True)
        return sorted_signals[0]

    def _resolve_unanimous(self, signals: list[Signal]) -> Signal | None:
        """All signals must agree on action."""
        if not signals:
            return None

        # Check if all signals have same action
        actions = {s.action for s in signals}
        if len(actions) == 1:
            # All agree - return highest priority
            return self._resolve_priority(signals)

        # No consensus
        return None

    @property
    def config(self) -> ResolutionConfig:
        """Get the resolution config."""
        return self._config
