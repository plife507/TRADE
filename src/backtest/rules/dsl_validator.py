"""
DSL Reference Validator: Compile-time validation of feature and setup references.

Validates that all FeatureRef and SetupRef nodes in the DSL expression tree
reference declared features, valid structure fields, and non-circular setups.

Functions:
- validate_dsl_references: Main entry point for reference validation
- validate_setup_references: Validate SetupRef nodes against declared setups
- detect_circular_setups: DFS-based circular dependency detection
"""

from __future__ import annotations

import difflib
from typing import TYPE_CHECKING

from .dsl_nodes.base import FeatureRef, ArithmeticExpr, ScalarValue
from .dsl_nodes.boolean import AllExpr, AnyExpr, NotExpr, SetupRef
from .dsl_nodes.condition import Cond
from .dsl_nodes.types import Expr
from .dsl_nodes.windows import (
    HoldsFor, OccurredWithin, CountTrue,
    HoldsForDuration, OccurredWithinDuration, CountTrueDuration,
)

if TYPE_CHECKING:
    from ..feature_registry import FeatureRegistry
    from .strategy_blocks import Block

# OHLCV builtins -- always valid feature_ids
OHLCV_BUILTINS: frozenset[str] = frozenset({
    "open", "high", "low", "close", "volume", "timestamp",
    "mark_price", "last_price", "open_interest", "funding_rate",
})


# =============================================================================
# Tree walkers
# =============================================================================

def _collect_all_refs(expr: Expr) -> list[FeatureRef]:
    """Walk the expression tree and collect all FeatureRef nodes."""
    refs: list[FeatureRef] = []

    def _collect_from_arithmetic(arith: ArithmeticExpr) -> None:
        if isinstance(arith.left, FeatureRef):
            refs.append(arith.left)
        elif isinstance(arith.left, ArithmeticExpr):
            _collect_from_arithmetic(arith.left)
        if isinstance(arith.right, FeatureRef):
            refs.append(arith.right)
        elif isinstance(arith.right, ArithmeticExpr):
            _collect_from_arithmetic(arith.right)

    def _walk(e: Expr) -> None:
        if isinstance(e, Cond):
            if isinstance(e.lhs, FeatureRef):
                refs.append(e.lhs)
            elif isinstance(e.lhs, ArithmeticExpr):
                _collect_from_arithmetic(e.lhs)
            if isinstance(e.rhs, FeatureRef):
                refs.append(e.rhs)
            elif isinstance(e.rhs, ArithmeticExpr):
                _collect_from_arithmetic(e.rhs)

        elif isinstance(e, AllExpr):
            for child in e.children:
                _walk(child)

        elif isinstance(e, AnyExpr):
            for child in e.children:
                _walk(child)

        elif isinstance(e, NotExpr):
            _walk(e.child)

        elif isinstance(e, (HoldsFor, OccurredWithin, CountTrue)):
            _walk(e.expr)

        elif isinstance(e, (HoldsForDuration, OccurredWithinDuration, CountTrueDuration)):
            _walk(e.expr)

        elif isinstance(e, SetupRef):
            pass  # handled separately

    _walk(expr)
    return refs


def _collect_all_setup_refs(expr: Expr) -> list[SetupRef]:
    """Walk the expression tree and collect all SetupRef nodes."""
    refs: list[SetupRef] = []

    def _walk(e: Expr) -> None:
        if isinstance(e, SetupRef):
            refs.append(e)

        elif isinstance(e, Cond):
            pass  # no SetupRef inside Cond

        elif isinstance(e, AllExpr):
            for child in e.children:
                _walk(child)

        elif isinstance(e, AnyExpr):
            for child in e.children:
                _walk(child)

        elif isinstance(e, NotExpr):
            _walk(e.child)

        elif isinstance(e, (HoldsFor, OccurredWithin, CountTrue)):
            _walk(e.expr)

        elif isinstance(e, (HoldsForDuration, OccurredWithinDuration, CountTrueDuration)):
            _walk(e.expr)

    _walk(expr)
    return refs


# =============================================================================
# Single reference validation
# =============================================================================

def _get_structure_valid_fields(feature_id: str, registry: FeatureRegistry) -> list[str] | None:
    """
    If feature_id is a structure in the registry, return its valid output fields.
    Returns None if not a structure.
    """
    from src.structures.registry import STRUCTURE_OUTPUT_TYPES

    feature = registry.get_or_none(feature_id)
    if feature is None or not feature.is_structure:
        return None

    structure_type = feature.structure_type
    if structure_type is None or structure_type not in STRUCTURE_OUTPUT_TYPES:
        return None

    return list(STRUCTURE_OUTPUT_TYPES[structure_type].keys())


def _validate_single_ref(
    ref: FeatureRef,
    registry: FeatureRegistry,
    location: str,
) -> str | None:
    """
    Validate a single FeatureRef against the registry + builtins.
    Returns an error message or None if valid.
    """
    fid = ref.feature_id

    # OHLCV builtins are always valid
    if fid in OHLCV_BUILTINS:
        return None

    # Check if declared in the feature registry
    if not registry.has(fid):
        all_ids = sorted(registry._features.keys()) + sorted(OHLCV_BUILTINS)  # noqa: SLF001
        suggestions = difflib.get_close_matches(fid, all_ids, n=3, cutoff=0.5)
        msg = f"{location}: undeclared feature '{fid}'"
        if suggestions:
            msg += f" (did you mean: {', '.join(suggestions)}?)"
        return msg

    # For structure features with a non-default field, validate the field
    if ref.field != "value":
        valid_fields = _get_structure_valid_fields(fid, registry)
        if valid_fields is not None:
            if ref.field not in valid_fields:
                # Check for dynamic fields (fibonacci level_*, derived_zone zone*_*)
                feature = registry.get(fid)
                structure_type = feature.structure_type
                # Handle fibonacci level_* dynamically
                if structure_type == "fibonacci" and ref.field.startswith("level_"):
                    return None
                # Handle derived_zone zone*_* dynamically
                if structure_type == "derived_zone" and ref.field.startswith("zone"):
                    try:
                        underscore_idx = ref.field.index("_")
                        slot_field = ref.field[underscore_idx + 1:]
                        canonical_key = f"zone0_{slot_field}"
                        if canonical_key in valid_fields:
                            return None
                    except ValueError:
                        pass

                suggestions = difflib.get_close_matches(ref.field, valid_fields, n=3, cutoff=0.5)
                msg = f"{location}: invalid field '{ref.field}' for structure '{fid}'"
                if suggestions:
                    msg += f" (did you mean: {', '.join(suggestions)}?)"
                return msg

    return None


# =============================================================================
# Setup validation
# =============================================================================

def validate_setup_references(
    actions: list[Block],
    declared_setups: dict[str, Expr],
) -> list[str]:
    """
    Validate that all SetupRef nodes reference declared setups.

    Args:
        actions: List of strategy blocks to walk.
        declared_setups: Map of setup_id -> expression.

    Returns:
        List of error messages.
    """
    errors: list[str] = []
    setup_ids = set(declared_setups.keys())

    for block in actions:
        for case_idx, case in enumerate(block.cases):
            refs = _collect_all_setup_refs(case.when)
            location = f"block '{block.id}' case {case_idx}"
            for ref in refs:
                if ref.setup_id not in setup_ids:
                    suggestions = difflib.get_close_matches(
                        ref.setup_id, sorted(setup_ids), n=3, cutoff=0.5
                    )
                    msg = f"{location}: undeclared setup '{ref.setup_id}'"
                    if suggestions:
                        msg += f" (did you mean: {', '.join(suggestions)}?)"
                    errors.append(msg)

    return errors


def detect_circular_setups(setups: dict[str, Expr]) -> list[str]:
    """
    Detect circular references in setup definitions via DFS.

    Args:
        setups: Map of setup_id -> expression tree.

    Returns:
        List of error messages describing circular references.
    """
    errors: list[str] = []
    # States: 0=unvisited, 1=in-progress, 2=done
    state: dict[str, int] = {sid: 0 for sid in setups}
    path: list[str] = []

    def _dfs(sid: str) -> None:
        if state[sid] == 2:
            return
        if state[sid] == 1:
            # Found a cycle
            cycle_start = path.index(sid)
            cycle = path[cycle_start:] + [sid]
            errors.append(
                f"circular setup reference: {' -> '.join(cycle)}"
            )
            return

        state[sid] = 1
        path.append(sid)

        # Walk the expression tree for this setup
        expr = setups[sid]
        for ref in _collect_all_setup_refs(expr):
            if ref.setup_id in setups:
                _dfs(ref.setup_id)

        path.pop()
        state[sid] = 2

    for sid in setups:
        _dfs(sid)

    return errors


# =============================================================================
# Main entry point
# =============================================================================

def validate_dsl_references(
    actions: list[Block],
    registry: FeatureRegistry,
    setups: dict[str, Expr] | None = None,
) -> list[str]:
    """
    Validate all FeatureRef and SetupRef nodes in the action blocks.

    Checks:
    1. All FeatureRef.feature_id values exist in the registry or OHLCV builtins
    2. Structure field references are valid for their structure type
    3. SetupRef nodes reference declared setups (if setups dict provided)
    4. No circular setup references

    Args:
        actions: List of strategy Block instances.
        registry: The Play's FeatureRegistry.
        setups: Optional dict of setup_id -> Expr. If None, setup validation skipped.

    Returns:
        List of error messages (empty if valid).
    """
    errors: list[str] = []

    # 1. Validate FeatureRef nodes in actions
    for block in actions:
        for case_idx, case in enumerate(block.cases):
            location = f"block '{block.id}' case {case_idx}"
            refs = _collect_all_refs(case.when)
            for ref in refs:
                err = _validate_single_ref(ref, registry, location)
                if err is not None:
                    errors.append(err)

    # 2. Validate FeatureRef nodes inside setup expressions
    if setups:
        for setup_id, expr in setups.items():
            location = f"setup '{setup_id}'"
            refs = _collect_all_refs(expr)
            for ref in refs:
                err = _validate_single_ref(ref, registry, location)
                if err is not None:
                    errors.append(err)

    # 3. Validate SetupRef nodes reference declared setups
    if setups is not None:
        setup_errors = validate_setup_references(actions, setups)
        errors.extend(setup_errors)

        # 4. Detect circular setup references
        circular_errors = detect_circular_setups(setups)
        errors.extend(circular_errors)

    return errors
