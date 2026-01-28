"""
DSL Parser: YAML to AST conversion for Play actions.

Parses the actions format from YAML into AST node types.

YAML Schema (3.0.0):
```yaml
version: "3.0.0"

actions:
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
    # G6.9.2: Updated docstring blocks: -> actions:
    blocks = parse_blocks(yaml_data["actions"])
    expr = parse_expr(condition_dict)
"""

from __future__ import annotations

from typing import Any

from .dsl_nodes import (
    Expr, Cond, AllExpr, AnyExpr, NotExpr,
    HoldsFor, OccurredWithin, CountTrue, SetupRef,
    HoldsForDuration, OccurredWithinDuration, CountTrueDuration,
    FeatureRef, ScalarValue, RangeValue, ListValue, RhsValue,
    ArithmeticExpr, ARITHMETIC_OPERATORS,
    VALID_OPERATORS, WINDOW_BARS_CEILING,
    validate_expr_types,
)
from .strategy_blocks import Block, Case, Intent


# =============================================================================
# Arithmetic Expression Parsing
# =============================================================================

def is_arithmetic_list(data: Any) -> bool:
    """
    Check if a value is an arithmetic expression list.

    Arithmetic syntax: [operand, operator, operand]
    Where operator is one of: +, -, *, /, %

    Distinguishes from ListValue (for 'in' operator) by checking:
    - Exactly 3 elements
    - Middle element is an arithmetic operator string

    Examples:
        ["ema_9", "-", "ema_21"]  → True (arithmetic)
        [1, 2, 3]                 → False (list for 'in')
        ["ema_9", ">", "ema_21"] → False (not arithmetic op)
    """
    if not isinstance(data, list):
        return False
    if len(data) != 3:
        return False
    # Middle element must be an arithmetic operator
    op = data[1]
    return isinstance(op, str) and op in ARITHMETIC_OPERATORS


PROXIMITY_OPERATORS = {"near_abs", "near_pct"}


def is_condition_list(data: Any) -> bool:
    """
    Check if a value is a condition shorthand list.

    Condition shorthand:
        - 3-element: [lhs, operator, rhs]
        - 4-element: [lhs, proximity_op, rhs, tolerance] (for near_abs, near_pct)

    Where operator is one of the VALID_OPERATORS (>, <, ==, cross_above, etc.)

    This enables the cookbook syntax:
        - ["ema_9", ">", "ema_21"]
        - ["rsi_14", "<", 30]
        - ["ema_9", "cross_above", "ema_21"]
        - ["close", "near_pct", {feature_id: "fib", field: "level_0.618"}, 0.5]

    Distinguishes from:
    - Arithmetic lists: middle element is +, -, *, /, %
    - ListValue (for 'in' operator): not 3 or 4 elements with valid operator

    Examples:
        ["ema_9", ">", "ema_21"]      → True (condition)
        ["rsi_14", "cross_above", 50] → True (condition)
        ["close", "near_pct", rhs, 0.5] → True (4-element proximity)
        ["ema_9", "-", "ema_21"]      → False (arithmetic)
        [1, 2, 3]                     → False (list values)
    """
    if not isinstance(data, list):
        return False

    # 4-element format only valid for proximity operators
    if len(data) == 4:
        op = data[1]
        return isinstance(op, str) and op in PROXIMITY_OPERATORS

    # 3-element format for all other operators
    if len(data) == 3:
        op = data[1]
        return isinstance(op, str) and op in VALID_OPERATORS and op not in ARITHMETIC_OPERATORS

    return False


def parse_arithmetic_operand(data: Any) -> FeatureRef | ScalarValue | ArithmeticExpr:
    """
    Parse an arithmetic operand.

    Valid operand types:
    - String: feature_id shorthand (e.g., "ema_9")
    - Dict with feature_id: full FeatureRef
    - Number: scalar value
    - List with 3 elements: nested arithmetic

    Args:
        data: Operand data from YAML.

    Returns:
        FeatureRef, ScalarValue, or nested ArithmeticExpr.
    """
    # Nested arithmetic
    if is_arithmetic_list(data):
        return parse_arithmetic(data)

    # String → feature_id shorthand
    if isinstance(data, str):
        return FeatureRef(feature_id=data)

    # Dict → full FeatureRef
    if isinstance(data, dict) and "feature_id" in data:
        return FeatureRef(
            feature_id=data["feature_id"],
            field=data.get("field", "value"),
            offset=data.get("offset", 0),
        )

    # Number → scalar
    if isinstance(data, (int, float)):
        return ScalarValue(data)

    raise ValueError(
        f"Invalid arithmetic operand: {data}. "
        f"Expected feature_id string, feature dict, number, or nested arithmetic."
    )


def parse_arithmetic(data: list) -> ArithmeticExpr:
    """
    Parse an arithmetic expression from list syntax.

    Format: [left, operator, right]

    Args:
        data: List of [operand, operator, operand].

    Returns:
        ArithmeticExpr node.

    Examples:
        ["ema_9", "-", "ema_21"]
        → ArithmeticExpr(left=FeatureRef("ema_9"), op="-", right=FeatureRef("ema_21"))

        [["ema_9", "-", "ema_21"], "/", "atr_14"]
        → ArithmeticExpr(left=ArithmeticExpr(...), op="/", right=FeatureRef("atr_14"))
    """
    if not is_arithmetic_list(data):
        raise ValueError(
            f"Invalid arithmetic expression: {data}. "
            f"Expected [operand, operator, operand] where operator is one of {sorted(ARITHMETIC_OPERATORS)}."
        )

    left_data, op, right_data = data
    left = parse_arithmetic_operand(left_data)
    right = parse_arithmetic_operand(right_data)

    return ArithmeticExpr(left=left, op=op, right=right)


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

        # Arithmetic expression
        rhs: ["ema_9", "-", 100]

    Args:
        data: RHS value from YAML.

    Returns:
        RhsValue (FeatureRef, ScalarValue, RangeValue, ListValue, or ArithmeticExpr).
    """
    # Scalar values
    if isinstance(data, (int, float, bool, str)) and not isinstance(data, dict):
        return ScalarValue(data)

    # List - check if arithmetic or ListValue
    if isinstance(data, list):
        # Arithmetic: [operand, operator, operand]
        if is_arithmetic_list(data):
            return parse_arithmetic(data)
        # Otherwise: list for 'in' operator
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


def parse_lhs(data: Any) -> FeatureRef | ArithmeticExpr:
    """
    Parse LHS value from YAML.

    LHS can be:
    - Feature reference (string or dict)
    - Arithmetic expression (list)

    Args:
        data: LHS value from YAML.

    Returns:
        FeatureRef or ArithmeticExpr.
    """
    # Arithmetic expression
    if is_arithmetic_list(data):
        return parse_arithmetic(data)

    # Feature reference
    return parse_feature_ref(data)


def _normalize_bracket_syntax(field: str) -> str:
    """
    Convert bracket syntax to internal field format.

    Bracket syntax is the user-facing format:
        - level[0.618]     -> level_0.618     (fibonacci levels)
        - zone[0].state    -> zone0_state     (zone slot fields)
        - zone[2].lower    -> zone2_lower     (zone slot fields)

    Args:
        field: Field string, possibly with bracket syntax.

    Returns:
        Internal field format string.

    Examples:
        >>> _normalize_bracket_syntax("level[0.618]")
        "level_0.618"
        >>> _normalize_bracket_syntax("zone[0].state")
        "zone0_state"
        >>> _normalize_bracket_syntax("high_level")
        "high_level"
    """
    import re

    # Pattern: word[index] optionally followed by .subfield
    # Examples: level[0.618], zone[0], zone[0].state
    pattern = r"(\w+)\[([^\]]+)\](?:\.(\w+))?"

    def replace_bracket(match: re.Match) -> str:
        prefix = match.group(1)   # e.g., "level" or "zone"
        index = match.group(2)    # e.g., "0.618" or "0"
        subfield = match.group(3)  # e.g., "state" or None

        # For fibonacci levels: level[0.618] -> level_0.618
        # For zone slots: zone[0].state -> zone0_state
        if subfield:
            # zone[N].field -> zoneN_field
            return f"{prefix}{index}_{subfield}"
        else:
            # level[N] -> level_N (with underscore for readability)
            return f"{prefix}_{index}"

    return re.sub(pattern, replace_bracket, field)


def _string_to_feature_ref_dict(s: str) -> dict:
    """
    Convert a string to a feature reference dict.

    Handles simple feature IDs, dotted syntax, and bracket syntax:
    - "ema_21" -> {"feature_id": "ema_21"}
    - "swing.low_level" -> {"feature_id": "swing", "field": "low_level"}
    - "fib.level[0.618]" -> {"feature_id": "fib", "field": "level_0.618"}
    - "zones.zone[0].state" -> {"feature_id": "zones", "field": "zone0_state"}

    Args:
        s: String to convert.

    Returns:
        Dict with feature_id (and optionally field).
    """
    if "." in s:
        parts = s.split(".", 1)
        field = _normalize_bracket_syntax(parts[1])
        return {"feature_id": parts[0], "field": field}
    return {"feature_id": s}


def _is_enum_literal(s: str) -> bool:
    """
    Check if a string looks like an enum literal.

    Enum literals are discrete state values used for comparisons:
    - "active", "broken", "none" (zone states - lowercase)
    - "bullish", "bearish", "none" (direction strings - lowercase)
    - "high", "low" (pivot types - lowercase)

    Does NOT match:
    - Feature IDs: "ema_9", "ema_21", "rsi_14" (have underscores with digits)
    - Dotted refs: "fib.level" (have dots)
    - Boolean strings: "true", "false" (handled separately)

    Args:
        s: String to check.

    Returns:
        True if string is an enum literal (pure alphabetic, no dots, no digit suffix).
    """
    if not s:
        return False

    # Dots indicate a feature reference, not an enum literal
    if "." in s:
        return False

    # Brackets indicate indexed access, not an enum literal
    if "[" in s:
        return False

    # Check for feature ID pattern: word_number (e.g., "ema_9", "rsi_14")
    # These have underscores followed by digits
    if "_" in s:
        parts = s.rsplit("_", 1)
        # If last part after underscore is all digits, it's a feature ID
        if len(parts) == 2 and parts[1].isdigit():
            return False

    # Pure alphabetic (with optional underscores between letters) is an enum literal
    # Examples: "active", "bullish", "none", "ACTIVE", "swing_high"
    return s.replace("_", "").isalpha()


def _normalize_rhs_for_operator(rhs: any, op: str) -> any:
    """
    Normalize RHS value based on operator context.

    For verbose format conditions like:
        lhs: "ema_9"
        op: cross_above
        rhs: "ema_21"

    The string "ema_21" should be treated as a feature reference, not a literal.

    Rules:
    1. Numeric operators (>, <, >=, <=, cross_above, cross_below, near_*, between):
       String RHS MUST be a FeatureRef (convert string to dict)
    2. Discrete operators (==, !=):
       - ALL_CAPS strings are enum literals (keep as string)
       - Other strings are feature refs (convert to dict)
    3. Set operator (in):
       Already handled correctly (list)

    Args:
        rhs: Original RHS value from YAML.
        op: Operator string.

    Returns:
        Normalized RHS (string converted to feature ref dict if needed).
    """
    from .dsl_nodes import NUMERIC_OPERATORS, DISCRETE_OPERATORS

    # Only normalize string RHS values
    if not isinstance(rhs, str):
        return rhs

    # Numeric operators: string RHS is always a feature reference
    if op in NUMERIC_OPERATORS:
        return _string_to_feature_ref_dict(rhs)

    # Discrete operators: ALL_CAPS strings are enum literals, otherwise feature ref
    if op in DISCRETE_OPERATORS:
        if _is_enum_literal(rhs):
            return rhs  # Keep as scalar string (enum literal)
        return _string_to_feature_ref_dict(rhs)

    # Default: return as-is
    return rhs


def parse_cond(data: dict) -> Cond:
    """
    Parse a Cond from YAML.

    Format:
        - lhs: {feature_id: "rsi_14"}
          op: gt
          rhs: 50.0
          tolerance: 0.01  # Optional, for near_* operators

        # With arithmetic LHS
        - lhs: ["ema_9", "-", "ema_21"]
          op: gt
          rhs: 100

        # Verbose with feature RHS (BUG-008 fix)
        - lhs: "ema_9"
          op: cross_above
          rhs: "ema_21"    # Now correctly resolved as FeatureRef

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

    lhs = parse_lhs(data["lhs"])
    op = data["op"]

    # Normalize string RHS based on operator context (BUG-008 fix)
    rhs_raw = data["rhs"]
    rhs_normalized = _normalize_rhs_for_operator(rhs_raw, op)
    rhs = parse_rhs(rhs_normalized)

    tolerance = data.get("tolerance")

    # Validate operator
    if op not in VALID_OPERATORS:
        raise ValueError(
            f"Unknown operator '{op}'. Valid operators: {sorted(VALID_OPERATORS)}"
        )

    return Cond(lhs=lhs, op=op, rhs=rhs, tolerance=tolerance)


def parse_condition_shorthand(data: list) -> Cond:
    """
    Parse a condition from shorthand list syntax.

    Shorthand formats:
        - 3-element: [lhs, operator, rhs]
        - 4-element: [lhs, proximity_op, rhs, tolerance] (for near_abs, near_pct)

    This enables the cookbook syntax:
        - ["ema_9", ">", "ema_21"]
        - ["rsi_14", "<", 30]
        - ["ema_9", "cross_above", "ema_21"]
        - ["zone.state", "==", "active"]
        - ["rsi_14", "between", [30, 70]]
        - ["close", "near_pct", "fib.level[0.618]", 0.5]

    Bracket syntax (universal indexed access):
        - ["fib.level[0.618]", ">", 0]           # Fibonacci level
        - ["zones.zone[0].state", "==", "active"] # Zone slot field
        - ["zones.zone[2].lower", ">", 50000]    # Zone slot boundary

    Args:
        data: List of [lhs, operator, rhs] or [lhs, proximity_op, rhs, tolerance].

    Returns:
        Cond node.

    Raises:
        ValueError: If list format is invalid or operator is unknown.
    """
    tolerance = None

    # Handle 4-element format for proximity operators
    if len(data) == 4:
        lhs_raw, op, rhs_raw, tolerance = data
        if op not in PROXIMITY_OPERATORS:
            raise ValueError(
                f"4-element shorthand only valid for proximity operators {PROXIMITY_OPERATORS}, got '{op}'"
            )
    elif len(data) == 3:
        lhs_raw, op, rhs_raw = data
    else:
        raise ValueError(
            f"Condition shorthand requires 3 or 4 elements, got {len(data)}"
        )

    # Validate operator
    if op not in VALID_OPERATORS:
        raise ValueError(
            f"Unknown operator '{op}' in shorthand. Valid operators: {sorted(VALID_OPERATORS)}"
        )

    # Parse LHS
    lhs = parse_lhs(lhs_raw)

    # Normalize and parse RHS based on operator context
    rhs_normalized = _normalize_rhs_for_operator(rhs_raw, op)
    rhs = parse_rhs(rhs_normalized)

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

        # Condition shorthand (cookbook syntax)
        - ["ema_9", ">", "ema_21"]
        - ["rsi_14", "cross_above", 50]

    Args:
        data: Expression dict from YAML.

    Returns:
        Expr node.
    """
    # Handle list - check for condition shorthand first
    if isinstance(data, list):
        # Condition shorthand: ["lhs", "op", "rhs"]
        if is_condition_list(data):
            return parse_condition_shorthand(data)
        # Single-element list: unwrap
        if len(data) == 1:
            return parse_expr(data[0])
        # Multi-element list: implicit AllExpr
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

    # Check for bar-based window operators
    if "holds_for" in data:
        window_data = data["holds_for"]
        bars = window_data.get("bars")
        if not bars:
            raise ValueError("holds_for requires 'bars'")
        if bars > WINDOW_BARS_CEILING:
            raise ValueError(f"holds_for bars exceeds ceiling ({WINDOW_BARS_CEILING})")
        expr = parse_expr(window_data.get("expr", {}))
        anchor_tf = window_data.get("anchor_tf")  # Optional
        return HoldsFor(bars=bars, expr=expr, anchor_tf=anchor_tf)

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
        anchor_tf = window_data.get("anchor_tf")  # Optional
        return OccurredWithin(bars=bars, expr=expr, anchor_tf=anchor_tf)

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
        anchor_tf = window_data.get("anchor_tf")  # Optional
        return CountTrue(bars=bars, min_true=min_true, expr=expr, anchor_tf=anchor_tf)

    # Check for duration-based window operators
    if "holds_for_duration" in data:
        window_data = data["holds_for_duration"]
        duration = window_data.get("duration")
        if not duration:
            raise ValueError("holds_for_duration requires 'duration'")
        expr = parse_expr(window_data.get("expr", {}))
        return HoldsForDuration(duration=duration, expr=expr)

    if "occurred_within_duration" in data:
        window_data = data["occurred_within_duration"]
        duration = window_data.get("duration")
        if not duration:
            raise ValueError("occurred_within_duration requires 'duration'")
        expr = parse_expr(window_data.get("expr", {}))
        return OccurredWithinDuration(duration=duration, expr=expr)

    if "count_true_duration" in data:
        window_data = data["count_true_duration"]
        duration = window_data.get("duration")
        min_true = window_data.get("min_true")
        if not duration:
            raise ValueError("count_true_duration requires 'duration'")
        if not min_true:
            raise ValueError("count_true_duration requires 'min_true'")
        expr = parse_expr(window_data.get("expr", {}))
        return CountTrueDuration(duration=duration, min_true=min_true, expr=expr)

    # Check for setup reference
    if "setup" in data:
        setup_id = data["setup"]
        if not isinstance(setup_id, str):
            raise ValueError("'setup' must be a string setup_id")
        return SetupRef(setup_id=setup_id)

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
        # Full format with partial exit
        - action: exit_long
          percent: 50
          metadata:
            reason: "take_profit"

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
    percent = data.get("percent", 100.0)

    return Intent(action=action, metadata=metadata, percent=percent)


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

def parse_play_actions(play_dict: dict) -> list[Block]:
    """
    Parse actions (entry/exit rules) from a Play dict.

    Args:
        play_dict: Raw Play dictionary.

    Returns:
        List of Block instances.

    Raises:
        ValueError: If no 'actions' key in dict.
    """
    # G6.5.2: Removed legacy 'blocks' key support - use 'actions' only
    actions_data = play_dict.get("actions")
    if not actions_data:
        raise ValueError(
            "Play must have 'actions' key. "
            "Define entry/exit rules in the actions section."
        )

    return parse_blocks(actions_data)


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
