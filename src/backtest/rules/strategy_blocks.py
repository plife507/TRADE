"""
Strategy Blocks: Case-based control flow for Play.

Provides deterministic, first-match execution semantics for trading logic.

Key Concepts:
- Intent: An action to emit (entry_long, exit_short, no_action, etc.)
- Case: A condition (when) and actions to emit if true
- Block: A named collection of cases with optional else fallback
- First-match: Cases are evaluated in order, first true case wins

Usage:
    # Define blocks
    entry_block = Block(
        id="entry",
        cases=(
            Case(
                when=AllExpr((trend_up, rsi_oversold)),
                emit=(Intent(action="entry_long"),)
            ),
            Case(
                when=AllExpr((trend_down, rsi_overbought)),
                emit=(Intent(action="entry_short"),)
            ),
        ),
        else_emit=(Intent(action="no_action"),)
    )

    # Execute
    executor = StrategyBlocksExecutor()
    intents = executor.execute([entry_block], snapshot)
    # Returns list of Intent objects
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .dsl_nodes import Expr
from .dsl_eval import ExprEvaluator, DEFAULT_MAX_WINDOW_BARS

if TYPE_CHECKING:
    from ..runtime.snapshot import RuntimeSnapshotView


# =============================================================================
# Data Structures
# =============================================================================

@dataclass(frozen=True)
class Intent:
    """
    An action to emit from strategy evaluation.

    Attributes:
        action: The action name (see VALID_ACTIONS)
        metadata: Additional key-value pairs for the action

    Examples:
        Intent(action="entry_long")
        Intent(action="exit_short", metadata={"reason": "stop_loss"})
        Intent(action="adjust_stop", metadata={"price": 100.0})
    """
    action: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate action name."""
        if not self.action:
            raise ValueError("Intent: action is required")

    def __repr__(self) -> str:
        if self.metadata:
            return f"Intent({self.action!r}, {self.metadata})"
        return f"Intent({self.action!r})"

    def to_dict(self) -> dict:
        """Serialize to dict."""
        result: dict = {"action": self.action}
        if self.metadata:
            result["metadata"] = dict(self.metadata)
        return result


# Valid action names for Intent
VALID_ACTIONS = frozenset({
    # Entry actions
    "entry_long",
    "entry_short",
    # Exit actions
    "exit_long",
    "exit_short",
    "exit_all",
    # Adjustment actions
    "adjust_stop",
    "adjust_target",
    "adjust_size",
    # No-op
    "no_action",
})


@dataclass(frozen=True)
class Case:
    """
    A single case in a strategy block.

    Attributes:
        when: Expression to evaluate (if true, emit actions)
        emit: Tuple of Intents to emit if when is true

    First-match semantics: Cases are evaluated in order within a Block.
    The first Case where 'when' evaluates to true wins.
    """
    when: Expr
    emit: tuple[Intent, ...]

    def __post_init__(self):
        """Validate case structure."""
        if not self.emit:
            raise ValueError("Case: emit cannot be empty")

    def __repr__(self) -> str:
        return f"Case(when={self.when!r}, emit={list(self.emit)})"

    def to_dict(self) -> dict:
        """Serialize to dict."""
        from .dsl_nodes import expr_to_dict
        return {
            "when": expr_to_dict(self.when),
            "emit": [i.to_dict() for i in self.emit],
        }


@dataclass(frozen=True)
class Block:
    """
    A named strategy block containing cases.

    Attributes:
        id: Unique block identifier
        cases: Tuple of Case instances (evaluated in order)
        else_emit: Optional Intents to emit if no case matches

    Execution:
        1. Evaluate each case's 'when' expression in order
        2. First case that evaluates to True: emit its Intents
        3. If no case matches and else_emit is set: emit else_emit
        4. If no case matches and no else_emit: emit nothing
    """
    id: str
    cases: tuple[Case, ...]
    else_emit: tuple[Intent, ...] | None = None

    def __post_init__(self):
        """Validate block structure."""
        if not self.id:
            raise ValueError("Block: id is required")
        if not self.cases:
            raise ValueError("Block: cases cannot be empty")

    def __repr__(self) -> str:
        cases_str = f"{len(self.cases)} cases"
        if self.else_emit:
            return f"Block({self.id!r}, {cases_str}, else={list(self.else_emit)})"
        return f"Block({self.id!r}, {cases_str})"

    def to_dict(self) -> dict:
        """Serialize to dict."""
        result: dict = {
            "id": self.id,
            "cases": [c.to_dict() for c in self.cases],
        }
        if self.else_emit:
            result["else"] = {"emit": [i.to_dict() for i in self.else_emit]}
        return result


# =============================================================================
# Executor
# =============================================================================

class StrategyBlocksExecutor:
    """
    Executes strategy blocks against a snapshot.

    Provides first-match semantics: within each block, cases are
    evaluated in order and the first matching case's intents are emitted.

    Thread-safe and stateless (evaluator is created per-call if not provided).

    Attributes:
        evaluator: ExprEvaluator instance (optional, created if not provided)

    Example:
        executor = StrategyBlocksExecutor()

        blocks = [entry_block, exit_block]
        intents = executor.execute(blocks, snapshot)

        for intent in intents:
            if intent.action == "entry_long":
                # Handle long entry
                pass
    """

    def __init__(
        self,
        evaluator: ExprEvaluator | None = None,
        max_window_bars: int = DEFAULT_MAX_WINDOW_BARS,
    ):
        """
        Initialize executor.

        Args:
            evaluator: Optional pre-configured ExprEvaluator.
            max_window_bars: Max bars for window operators (if no evaluator provided).
        """
        self._evaluator = evaluator or ExprEvaluator(max_window_bars=max_window_bars)

    def execute(
        self,
        blocks: list[Block],
        snapshot: "RuntimeSnapshotView",
    ) -> list[Intent]:
        """
        Execute all blocks and collect emitted intents.

        Args:
            blocks: List of Block instances to execute.
            snapshot: RuntimeSnapshotView providing feature values.

        Returns:
            List of Intent objects emitted (may be empty).
        """
        intents: list[Intent] = []

        for block in blocks:
            block_intents = self._execute_block(block, snapshot)
            intents.extend(block_intents)

        return intents

    def _execute_block(
        self,
        block: Block,
        snapshot: "RuntimeSnapshotView",
    ) -> list[Intent]:
        """
        Execute a single block with first-match semantics.

        Args:
            block: Block to execute.
            snapshot: RuntimeSnapshotView providing feature values.

        Returns:
            List of Intent objects emitted by this block.
        """
        # Evaluate cases in order
        for case in block.cases:
            result = self._evaluator.evaluate(case.when, snapshot)
            if result.ok:
                # First match wins - return this case's intents
                return list(case.emit)

        # No case matched - use else_emit if available
        if block.else_emit:
            return list(block.else_emit)

        # No match, no else - return empty
        return []

    def execute_single_block(
        self,
        block: Block,
        snapshot: "RuntimeSnapshotView",
    ) -> list[Intent]:
        """
        Execute a single block (convenience method).

        Args:
            block: Block to execute.
            snapshot: RuntimeSnapshotView providing feature values.

        Returns:
            List of Intent objects emitted by this block.
        """
        return self._execute_block(block, snapshot)


# =============================================================================
# Intent Helpers
# =============================================================================

def intent_entry_long(**metadata: Any) -> Intent:
    """Create an entry_long intent."""
    return Intent(action="entry_long", metadata=metadata)


def intent_entry_short(**metadata: Any) -> Intent:
    """Create an entry_short intent."""
    return Intent(action="entry_short", metadata=metadata)


def intent_exit_long(**metadata: Any) -> Intent:
    """Create an exit_long intent."""
    return Intent(action="exit_long", metadata=metadata)


def intent_exit_short(**metadata: Any) -> Intent:
    """Create an exit_short intent."""
    return Intent(action="exit_short", metadata=metadata)


def intent_no_action() -> Intent:
    """Create a no_action intent."""
    return Intent(action="no_action")


# =============================================================================
# Block Builders
# =============================================================================

def build_entry_block(
    long_expr: Expr | None = None,
    short_expr: Expr | None = None,
    block_id: str = "entry",
) -> Block | None:
    """
    Build an entry block from long/short expressions.

    Args:
        long_expr: Expression for long entry (optional).
        short_expr: Expression for short entry (optional).
        block_id: Block identifier.

    Returns:
        Block instance, or None if no expressions provided.
    """
    cases: list[Case] = []

    if long_expr:
        cases.append(Case(
            when=long_expr,
            emit=(Intent(action="entry_long"),)
        ))

    if short_expr:
        cases.append(Case(
            when=short_expr,
            emit=(Intent(action="entry_short"),)
        ))

    if not cases:
        return None

    return Block(
        id=block_id,
        cases=tuple(cases),
        else_emit=(Intent(action="no_action"),)
    )


def build_exit_block(
    long_exit_expr: Expr | None = None,
    short_exit_expr: Expr | None = None,
    block_id: str = "exit",
) -> Block | None:
    """
    Build an exit block from long/short exit expressions.

    Args:
        long_exit_expr: Expression for long exit (optional).
        short_exit_expr: Expression for short exit (optional).
        block_id: Block identifier.

    Returns:
        Block instance, or None if no expressions provided.
    """
    cases: list[Case] = []

    if long_exit_expr:
        cases.append(Case(
            when=long_exit_expr,
            emit=(Intent(action="exit_long"),)
        ))

    if short_exit_expr:
        cases.append(Case(
            when=short_exit_expr,
            emit=(Intent(action="exit_short"),)
        ))

    if not cases:
        return None

    return Block(
        id=block_id,
        cases=tuple(cases),
        # No else for exit - only exit when condition is met
    )
