"""
Rule evaluation module for IdeaCard conditions.

Stage 4c: Compiled reference resolver + strict operator semantics.

Design principles:
- Compile paths at normalization time, not in hot loop
- Strict type checking with actionable error messages
- ReasonCode for every evaluation outcome
- No float equality (use approx_eq with tolerance)
- Unsupported operators fail at compile time (never reach hot loop)
"""

from .types import (
    ReasonCode,
    ValueType,
    EvalResult,
    RefValue,
)
from .compile import (
    CompiledRef,
    compile_ref,
    validate_ref_path,
    RefNamespace,
)
from .eval import (
    evaluate_condition,
    OPERATORS,
)
from .registry import (
    OperatorSpec,
    OpCategory,
    OPERATOR_REGISTRY,
    SUPPORTED_OPERATORS,
    get_operator_spec,
    is_operator_supported,
    validate_operator,
    get_canonical_operator,
)

__all__ = [
    # Types
    "ReasonCode",
    "ValueType",
    "EvalResult",
    "RefValue",
    # Compilation
    "CompiledRef",
    "compile_ref",
    "validate_ref_path",
    "RefNamespace",
    # Evaluation
    "evaluate_condition",
    "OPERATORS",
    # Registry
    "OperatorSpec",
    "OpCategory",
    "OPERATOR_REGISTRY",
    "SUPPORTED_OPERATORS",
    "get_operator_spec",
    "is_operator_supported",
    "validate_operator",
    "get_canonical_operator",
]
