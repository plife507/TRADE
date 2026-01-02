"""
Compiled reference resolver for IdeaCard conditions.

Paths are parsed and validated at IdeaCard normalization time,
not during hot-loop evaluation. This eliminates string parsing overhead.

Design:
- CompiledRef holds pre-parsed path tokens and resolver function
- validate_ref_path() checks paths against registry at compile time
- resolve() is O(1) array lookup, no string operations
"""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from .types import RefValue, ReasonCode, ValueType


class RefNamespace(str, Enum):
    """
    Reference namespaces for path resolution.

    Each namespace has its own resolution logic.
    """

    PRICE = "price"  # price.mark.close, price.last.close
    INDICATOR = "indicator"  # indicator.<key> or indicator.<key>.<tf_role>
    STRUCTURE = "structure"  # structure.<block_key>.<field>
    LITERAL = "literal"  # Compile-time constant (number, bool, enum token)


# Registry of valid price fields (Stage 1: only mark.close)
PRICE_FIELDS = {
    "mark": {"close"},  # Stage 6 adds: high, low
    # "last": {"close"},  # Reserved for future
}

# Registry of valid structure fields by type
# Imported from market_structure.types at runtime to avoid circular imports
STRUCTURE_FIELDS: Dict[str, Tuple[str, ...]] = {}


def _get_structure_fields() -> Dict[str, Tuple[str, ...]]:
    """Lazy load structure fields to avoid circular imports."""
    global STRUCTURE_FIELDS
    if not STRUCTURE_FIELDS:
        from src.backtest.market_structure.types import (
            SWING_PUBLIC_OUTPUTS,
            TREND_PUBLIC_OUTPUTS,
        )

        STRUCTURE_FIELDS = {
            "swing": SWING_PUBLIC_OUTPUTS,
            "trend": TREND_PUBLIC_OUTPUTS,
        }
    return STRUCTURE_FIELDS


@dataclass(frozen=True)
class CompiledRef:
    """
    Pre-compiled reference for fast resolution.

    Created at IdeaCard normalization time. Contains:
    - namespace: Which resolver to use
    - tokens: Pre-parsed path segments
    - path: Original path for error messages
    - literal_value: For LITERAL namespace, the constant value
    - literal_type: For LITERAL namespace, the value type

    Resolution is O(1) - just index lookup, no parsing.
    """

    namespace: RefNamespace
    tokens: Tuple[str, ...]  # Path segments after namespace
    path: str  # Original path for error messages
    literal_value: Optional[Any] = None  # For LITERAL refs
    literal_type: Optional[ValueType] = None  # For LITERAL refs

    @property
    def is_literal(self) -> bool:
        """Check if this is a compile-time literal."""
        return self.namespace == RefNamespace.LITERAL

    def resolve(self, snapshot) -> RefValue:
        """
        Resolve this reference against a snapshot.

        Args:
            snapshot: RuntimeSnapshotView instance

        Returns:
            RefValue with resolved value and type
        """
        if self.is_literal:
            return RefValue(
                value=self.literal_value,
                value_type=self.literal_type or ValueType.UNKNOWN,
                path=self.path,
            )

        # Delegate to snapshot.get() which has the resolution logic
        # This is still O(1) because snapshot.get() uses pre-indexed arrays
        try:
            value = snapshot.get(self.path)
            return RefValue.from_resolved(value, self.path)
        except (ValueError, KeyError) as e:
            # Path exists but value missing/invalid
            return RefValue.missing(self.path)

    @classmethod
    def literal(cls, value: Any, original_repr: str) -> "CompiledRef":
        """Create a compiled literal reference."""
        return cls(
            namespace=RefNamespace.LITERAL,
            tokens=(),
            path=original_repr,
            literal_value=value,
            literal_type=ValueType.from_value(value),
        )


class CompileError(Exception):
    """Error during reference compilation with actionable message."""

    def __init__(self, path: str, message: str, allowed: Optional[List[str]] = None):
        self.path = path
        self.allowed = allowed
        full_msg = f"Invalid path '{path}': {message}"
        if allowed:
            full_msg += f". Allowed: {', '.join(sorted(allowed))}"
        super().__init__(full_msg)


def validate_ref_path(
    path: str,
    available_indicators: Optional[Dict[str, List[str]]] = None,
    available_structures: Optional[List[str]] = None,
) -> Tuple[RefNamespace, Tuple[str, ...]]:
    """
    Validate a reference path and return parsed tokens.

    Called at IdeaCard normalization time. Fails fast with actionable errors.

    Args:
        path: Dot-separated path (e.g., "price.mark.close", "indicator.rsi_14")
        available_indicators: Dict of tf_role -> list of indicator keys
        available_structures: List of structure block keys

    Returns:
        Tuple of (namespace, tokens)

    Raises:
        CompileError: If path is invalid with actionable fix message
    """
    if not path or not isinstance(path, str):
        raise CompileError(path, "Path must be a non-empty string")

    parts = path.split(".")
    if len(parts) < 2:
        raise CompileError(
            path,
            "Path must have at least 2 segments (namespace.field)",
            allowed=["price.*", "indicator.*", "structure.*"],
        )

    namespace_str = parts[0]
    tokens = tuple(parts[1:])

    # Dispatch by namespace
    if namespace_str == "price":
        _validate_price_path(path, tokens)
        return RefNamespace.PRICE, tokens

    elif namespace_str == "indicator":
        _validate_indicator_path(path, tokens, available_indicators)
        return RefNamespace.INDICATOR, tokens

    elif namespace_str == "structure":
        _validate_structure_path(path, tokens, available_structures)
        return RefNamespace.STRUCTURE, tokens

    else:
        raise CompileError(
            path,
            f"Unknown namespace '{namespace_str}'",
            allowed=["price", "indicator", "structure"],
        )


def _validate_price_path(path: str, tokens: Tuple[str, ...]) -> None:
    """Validate price.* path."""
    if len(tokens) < 2:
        raise CompileError(
            path,
            "Price path requires at least 2 segments (price.<type>.<field>)",
            allowed=["price.mark.close"],
        )

    price_type = tokens[0]
    field = tokens[1]

    if price_type not in PRICE_FIELDS:
        raise CompileError(
            path,
            f"Unknown price type '{price_type}'",
            allowed=list(PRICE_FIELDS.keys()),
        )

    if field not in PRICE_FIELDS[price_type]:
        raise CompileError(
            path,
            f"Unknown field '{field}' for price.{price_type}",
            allowed=list(PRICE_FIELDS[price_type]),
        )


def _validate_indicator_path(
    path: str,
    tokens: Tuple[str, ...],
    available_indicators: Optional[Dict[str, List[str]]],
) -> None:
    """Validate indicator.* path."""
    if len(tokens) < 1:
        raise CompileError(
            path,
            "Indicator path requires key (indicator.<key>)",
        )

    indicator_key = tokens[0]
    tf_role = tokens[1] if len(tokens) > 1 else "exec"

    # Validate tf_role
    valid_roles = ("exec", "htf", "mtf", "ltf")
    if tf_role not in valid_roles:
        raise CompileError(
            path,
            f"Unknown tf_role '{tf_role}'",
            allowed=list(valid_roles),
        )

    # Validate indicator key if registry provided
    if available_indicators is not None:
        role_indicators = available_indicators.get(tf_role, [])
        # Also check OHLCV which is always available
        ohlcv = ["open", "high", "low", "close", "volume"]
        if indicator_key not in role_indicators and indicator_key not in ohlcv:
            all_available = role_indicators + ohlcv
            raise CompileError(
                path,
                f"Indicator '{indicator_key}' not declared for tf_role '{tf_role}'",
                allowed=all_available,
            )


def _validate_structure_path(
    path: str,
    tokens: Tuple[str, ...],
    available_structures: Optional[List[str]],
) -> None:
    """
    Validate structure.* path.

    Supports:
    - structure.<block_key>.<field>
    - structure.<block_key>.zones.<zone_key>.<field>  (Stage 5+)
    """
    if len(tokens) < 2:
        raise CompileError(
            path,
            "Structure path requires block_key and field (structure.<key>.<field>)",
        )

    block_key = tokens[0]
    field_or_zones = tokens[1]

    # Validate block key if registry provided
    if available_structures is not None:
        if block_key not in available_structures:
            raise CompileError(
                path,
                f"Unknown structure block_key '{block_key}'",
                allowed=available_structures,
            )

    # Stage 5+: Handle zones namespace
    if field_or_zones == "zones":
        # structure.<block_key>.zones.<zone_key>.<field>
        if len(tokens) < 4:
            raise CompileError(
                path,
                "Zone path requires: structure.<key>.zones.<zone_key>.<field>",
            )
        # zone_key = tokens[2]
        # zone_field = tokens[3]
        # Runtime validation of zone_key and zone_field happens in snapshot
        return

    # Field validation happens at runtime since we don't know the block type here
    # The snapshot resolver will validate the field


def compile_ref(
    value: Any,
    available_indicators: Optional[Dict[str, List[str]]] = None,
    available_structures: Optional[List[str]] = None,
) -> CompiledRef:
    """
    Compile a reference value (path string or literal).

    Args:
        value: Either a path string ("price.mark.close") or literal (42, True)
        available_indicators: Dict of tf_role -> list of indicator keys
        available_structures: List of structure block keys

    Returns:
        CompiledRef ready for fast resolution

    Raises:
        CompileError: If path is invalid
    """
    # Handle literals
    if isinstance(value, (int, float, bool)):
        return CompiledRef.literal(value, repr(value))

    # Handle None
    if value is None:
        return CompiledRef.literal(None, "None")

    # Handle string - could be path or enum token
    if isinstance(value, str):
        # Check if it looks like a path (has dots and starts with namespace)
        if "." in value:
            parts = value.split(".")
            if parts[0] in ("price", "indicator", "structure"):
                namespace, tokens = validate_ref_path(
                    value, available_indicators, available_structures
                )
                return CompiledRef(
                    namespace=namespace,
                    tokens=tokens,
                    path=value,
                )

        # Otherwise treat as string literal (enum token or constant)
        return CompiledRef.literal(value, repr(value))

    # Unknown type
    raise CompileError(
        str(value),
        f"Cannot compile value of type {type(value).__name__}",
    )


def compile_condition(
    condition_dict: Dict[str, Any],
    available_indicators: Optional[Dict[str, List[str]]] = None,
    available_structures: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Compile a condition dict, replacing paths with CompiledRefs.

    This is called during IdeaCard normalization to pre-compile all references.

    Args:
        condition_dict: Raw condition from YAML
        available_indicators: Dict of tf_role -> list of indicator keys
        available_structures: List of structure block keys

    Returns:
        Dict with 'lhs_ref' and 'rhs_ref' CompiledRef objects added
    """
    result = dict(condition_dict)

    # Compile LHS (indicator_key with optional tf prefix becomes path)
    indicator_key = condition_dict.get("indicator_key", "")
    tf = condition_dict.get("tf", "exec")

    # Build LHS path
    if indicator_key.startswith("structure."):
        # Already a structure path
        lhs_path = indicator_key
    elif indicator_key.startswith("price."):
        # Already a price path
        lhs_path = indicator_key
    else:
        # Indicator path - add namespace
        lhs_path = f"indicator.{indicator_key}"
        if tf != "exec":
            lhs_path = f"indicator.{indicator_key}.{tf}"

    result["lhs_ref"] = compile_ref(
        lhs_path, available_indicators, available_structures
    )

    # Compile RHS (value - could be literal or path)
    rhs_value = condition_dict.get("value")
    result["rhs_ref"] = compile_ref(
        rhs_value, available_indicators, available_structures
    )

    return result
