"""
DSL Parser: YAML to AST conversion for Play blocks.

Parses the blocks format from YAML into AST node types.

YAML Schema (3.0.0):
```yaml
version: "3.0.0"

blocks:
  - id: entry
    cases:
      - when:
          all:
            - lhs: {feature_id: rsi_14}
              op: lt
              rhs: 30
            - lhs: {feature_id: trend_1h, field: direction}
              op: eq
              rhs: 1
        emit:
          - action: entry_long
    else:
      emit:
        - action: no_action
```

Usage:
    blocks = parse_blocks(yaml_data["blocks"])
    expr = parse_expr(condition_dict)
"""

from __future__ import annotations

from typing import Any

from .dsl_nodes import (
    Expr, Cond, AllExpr, AnyExpr, NotExpr,
    HoldsFor, OccurredWithin, CountTrue,
    FeatureRef, ScalarValue, RangeValue, ListValue, RhsValue,
    VALID_OPERATORS, WINDOW_BARS_CEILING,
    validate_expr_types,
)
from .strategy_blocks import Block, Case, Intent


# =============================================================================
# Expression Parsing
# =============================================================================

def parse_feature_ref(data: dict | str) -> FeatureRef:
    """
    Parse a FeatureRef from YAML.

    Formats:
        # Full format
        lhs:
          feature_id: "rsi_14"
          field: "value"
          offset: 0

        # Shorthand (string)
        lhs: "rsi_14"

    Args:
        data: Dict with feature_id/field/offset, or string feature_id.

    Returns:
        FeatureRef node.
    """
    if isinstance(data, str):
        # Shorthand: just feature_id
        return FeatureRef(feature_id=data)

    if not isinstance(data, dict):
        raise ValueError(f"FeatureRef must be dict or string, got {type(data).__name__}")

    feature_id = data.get("feature_id")
    if not feature_id:
        raise ValueError("FeatureRef requires 'feature_id'")

    return FeatureRef(
        feature_id=feature_id,
        field=data.get("field", "value"),
        offset=data.get("offset", 0),
    )


def parse_rhs(data: Any) -> RhsValue:
    """
    Parse RHS value from YAML.

    Formats:
        # Scalar
        rhs: 50.0

        # Feature reference
        rhs: {feature_id: "ema_slow"}

        # Range (for between)
        rhs: {low: 30, high: 70}

        # List (for in)
        rhs: [1, -1, 0]

    Args:
        data: RHS value from YAML.

    Returns:
        RhsValue (FeatureRef, ScalarValue, RangeValue, or ListValue).
    """
    # Scalar values
    if isinstance(data, (int, float, bool, str)) and not isinstance(data, dict):
        return ScalarValue(data)

    # List (for 'in' operator)
    if isinstance(data, list):
        return ListValue(tuple(data))

    # Dict - could be FeatureRef or RangeValue
    if isinstance(data, dict):
        # Check for range
        if "low" in data and "high" in data:
            return RangeValue(low=float(data["low"]), high=float(data["high"]))

        # Must be FeatureRef
        if "feature_id" in data:
            return parse_feature_ref(data)

        raise ValueError(f"Unknown RHS dict format: {data}")

    raise ValueError(f"Cannot parse RHS: {data}")


def parse_cond(data: dict) -> Cond:
    """
    Parse a Cond from YAML.

    Format:
        - lhs: {feature_id: "rsi_14"}
          op: gt
          rhs: 50.0
          tolerance: 0.01  # Optional, for near_* operators

    Args:
        data: Condition dict from YAML.

    Returns:
        Cond node.
    """
    if "lhs" not in data:
        raise ValueError("Condition requires 'lhs'")
    if "op" not in data:
        raise ValueError("Condition requires 'op'")
    if "rhs" not in data:
        raise ValueError("Condition requires 'rhs'")

    lhs = parse_feature_ref(data["lhs"])
    op = data["op"]
    rhs = parse_rhs(data["rhs"])
    tolerance = data.get("tolerance")

    # Validate operator
    if op not in VALID_OPERATORS:
        raise ValueError(
            f"Unknown operator '{op}'. Valid operators: {sorted(VALID_OPERATORS)}"
        )

    return Cond(lhs=lhs, op=op, rhs=rhs, tolerance=tolerance)


def parse_expr(data: dict | list) -> Expr:
    """
    Parse an expression from YAML.

    Formats:
        # Single condition
        - lhs: {feature_id: "rsi_14"}
          op: gt
          rhs: 50

        # All (AND)
        all:
          - lhs: ...
          - lhs: ...

        # Any (OR)
        any:
          - lhs: ...
          - lhs: ...

        # Not
        not:
          lhs: ...

        # Window operators
        holds_for:
          bars: 5
          expr:
            lhs: ...

        occurred_within:
          bars: 3
          expr:
            lhs: ...

        count_true:
          bars: 10
          min_true: 3
          expr:
            lhs: ...

    Args:
        data: Expression dict from YAML.

    Returns:
        Expr node.
    """
    # Handle list as implicit AllExpr
    if isinstance(data, list):
        if len(data) == 1:
            return parse_expr(data[0])
        children = tuple(parse_expr(item) for item in data)
        return AllExpr(children)

    if not isinstance(data, dict):
        raise ValueError(f"Expression must be dict or list, got {type(data).__name__}")

    # Check for boolean expression types
    if "all" in data:
        items = data["all"]
        if not isinstance(items, list):
            raise ValueError("'all' must be a list")
        children = tuple(parse_expr(item) for item in items)
        return AllExpr(children)

    if "any" in data:
        items = data["any"]
        if not isinstance(items, list):
            raise ValueError("'any' must be a list")
        children = tuple(parse_expr(item) for item in items)
        return AnyExpr(children)

    if "not" in data:
        child = parse_expr(data["not"])
        return NotExpr(child)

    # Check for window operators
    if "holds_for" in data:
        window_data = data["holds_for"]
        bars = window_data.get("bars")
        if not bars:
            raise ValueError("holds_for requires 'bars'")
        if bars > WINDOW_BARS_CEILING:
            raise ValueError(f"holds_for bars exceeds ceiling ({WINDOW_BARS_CEILING})")
        expr = parse_expr(window_data.get("expr", {}))
        return HoldsFor(bars=bars, expr=expr)

    if "occurred_within" in data:
        window_data = data["occurred_within"]
        bars = window_data.get("bars")
        if not bars:
            raise ValueError("occurred_within requires 'bars'")
        if bars > WINDOW_BARS_CEILING:
            raise ValueError(
                f"occurred_within bars exceeds ceiling ({WINDOW_BARS_CEILING})"
            )
        expr = parse_expr(window_data.get("expr", {}))
        return OccurredWithin(bars=bars, expr=expr)

    if "count_true" in data:
        window_data = data["count_true"]
        bars = window_data.get("bars")
        min_true = window_data.get("min_true")
        if not bars:
            raise ValueError("count_true requires 'bars'")
        if not min_true:
            raise ValueError("count_true requires 'min_true'")
        if bars > WINDOW_BARS_CEILING:
            raise ValueError(f"count_true bars exceeds ceiling ({WINDOW_BARS_CEILING})")
        expr = parse_expr(window_data.get("expr", {}))
        return CountTrue(bars=bars, min_true=min_true, expr=expr)

    # Must be a single condition
    if "lhs" in data and "op" in data:
        return parse_cond(data)

    raise ValueError(f"Cannot parse expression: {data}")


# =============================================================================
# Intent/Case/Block Parsing
# =============================================================================

def parse_intent(data: dict | str) -> Intent:
    """
    Parse an Intent from YAML.

    Formats:
        # Full format
        - action: entry_long
          metadata:
            reason: "signal"

        # Shorthand
        - action: entry_long

        # String shorthand
        - entry_long

    Args:
        data: Intent dict or action string.

    Returns:
        Intent instance.
    """
    if isinstance(data, str):
        return Intent(action=data)

    if not isinstance(data, dict):
        raise ValueError(f"Intent must be dict or string, got {type(data).__name__}")

    action = data.get("action")
    if not action:
        raise ValueError("Intent requires 'action'")

    metadata = data.get("metadata", {})
    return Intent(action=action, metadata=metadata)


def parse_case(data: dict) -> Case:
    """
    Parse a Case from YAML.

    Format:
        - when:
            all:
              - lhs: ...
          emit:
            - action: entry_long

    Args:
        data: Case dict from YAML.

    Returns:
        Case instance.
    """
    if "when" not in data:
        raise ValueError("Case requires 'when'")
    if "emit" not in data:
        raise ValueError("Case requires 'emit'")

    when = parse_expr(data["when"])

    emit_data = data["emit"]
    if not isinstance(emit_data, list):
        raise ValueError("Case 'emit' must be a list")
    emit = tuple(parse_intent(item) for item in emit_data)

    return Case(when=when, emit=emit)


def parse_block(data: dict) -> Block:
    """
    Parse a Block from YAML.

    Format:
        - id: entry
          cases:
            - when: ...
              emit: ...
          else:
            emit:
              - action: no_action

    Args:
        data: Block dict from YAML.

    Returns:
        Block instance.
    """
    block_id = data.get("id")
    if not block_id:
        raise ValueError("Block requires 'id'")

    cases_data = data.get("cases")
    if not cases_data:
        raise ValueError("Block requires 'cases'")
    if not isinstance(cases_data, list):
        raise ValueError("Block 'cases' must be a list")

    cases = tuple(parse_case(item) for item in cases_data)

    # Parse else
    else_emit = None
    else_data = data.get("else")
    if else_data:
        emit_data = else_data.get("emit", [])
        if emit_data:
            else_emit = tuple(parse_intent(item) for item in emit_data)

    return Block(id=block_id, cases=cases, else_emit=else_emit)


def parse_blocks(data: list) -> list[Block]:
    """
    Parse a list of Blocks from YAML.

    Args:
        data: List of block dicts from YAML.

    Returns:
        List of Block instances.
    """
    if not isinstance(data, list):
        raise ValueError("'blocks' must be a list")

    return [parse_block(item) for item in data]


# =============================================================================
# High-Level API
# =============================================================================

def parse_play_blocks(play_dict: dict) -> list[Block]:
    """
    Parse blocks from an Play dict.

    Args:
        play_dict: Raw Play dictionary.

    Returns:
        List of Block instances.

    Raises:
        ValueError: If no 'blocks' key in dict.
    """
    if "blocks" not in play_dict:
        raise ValueError(
            "Play must have 'blocks' key. "
            "Legacy signal_rules format is not supported."
        )

    return parse_blocks(play_dict["blocks"])


def validate_blocks_types(
    blocks: list[Block],
    get_output_type,
) -> list[str]:
    """
    Validate operator/type compatibility for all blocks.

    This is called after parsing to catch type errors at compile-time.
    For example, using 'eq' on a FLOAT type will be rejected.

    Args:
        blocks: List of parsed Block instances.
        get_output_type: Callback that takes (feature_id, field) and returns
            FeatureOutputType. Typically registry.get_output_type.

    Returns:
        List of error messages (empty if valid).

    Example:
        >>> blocks = parse_blocks(yaml_data["blocks"])
        >>> errors = validate_blocks_types(blocks, registry.get_output_type)
        >>> if errors:
        ...     raise ValueError("Type validation failed:\\n" + "\\n".join(errors))
    """
    errors: list[str] = []

    for block in blocks:
        for case in block.cases:
            case_errors = validate_expr_types(case.when, get_output_type)
            for err in case_errors:
                errors.append(f"Block '{block.id}': {err}")

    return errors
