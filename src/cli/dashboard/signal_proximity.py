"""Signal proximity display -- shows which conditions are passing/failing now."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ConditionStatus:
    """Status of a single condition in a block."""

    lhs_path: str
    operator: str
    rhs_repr: str
    passing: bool


@dataclass(slots=True)
class BlockStatus:
    """Status of a single action block."""

    block_id: str
    conditions: list[ConditionStatus]

    @property
    def pass_ratio(self) -> float:
        if not self.conditions:
            return 0.0
        return sum(1 for c in self.conditions if c.passing) / len(self.conditions)


@dataclass
class SignalProximity:
    """Snapshot of signal proximity across all blocks."""

    blocks: list[BlockStatus] = field(default_factory=list)
    last_evaluated_bar: int = -1


def evaluate_proximity(
    manager: object,
    instance_id: str,
) -> SignalProximity | None:
    """Evaluate current signal proximity using the engine's cached snapshot.

    Reads the last snapshot view persisted by the engine after processing a bar,
    then runs evaluate_with_trace() on it. Returns None if no snapshot is available
    (e.g. before the first bar is processed).
    """
    mgr_instances: dict[str, Any] = getattr(manager, "_instances", {})
    inst = mgr_instances.get(instance_id)
    if inst is None:
        return None

    engine = inst.engine
    if engine is None:
        return None

    evaluator = getattr(engine, "_signal_evaluator", None)
    if evaluator is None:
        return None

    # Use the engine's cached snapshot (set after each bar in process_bar)
    snapshot = getattr(engine, "_snapshot_view", None)
    if snapshot is None:
        return None

    bar_index = getattr(engine, "_current_bar_index", -1)

    try:
        position = getattr(engine, "_position", None)
        has_pos = position is not None
        pos_side = position.side.lower() if position else None

        _result, trace = evaluator.evaluate_with_trace(snapshot, has_pos, pos_side)
    except Exception:
        return None

    # Convert trace to proximity display
    blocks: list[BlockStatus] = []
    for bt in trace.block_traces:
        conditions: list[ConditionStatus] = []

        # Use the first case trace (primary conditions)
        if bt.case_traces:
            ct = bt.case_traces[0]
            for cr in ct.cond_results:
                conditions.append(ConditionStatus(
                    lhs_path=cr.lhs_path or "?",
                    operator=cr.operator or "?",
                    rhs_repr=cr.rhs_repr or "?",
                    passing=cr.ok,
                ))

        blocks.append(BlockStatus(block_id=bt.block_id, conditions=conditions))

    return SignalProximity(blocks=blocks, last_evaluated_bar=bar_index)
