"""
Block Normalizer - Strict validation and normalization.

Pure function that validates Block configurations against:
- Required fields (id, version, features, condition)
- Feature registry (indicators must exist in INDICATOR_REGISTRY)
- DSL condition syntax (must be parseable)
- Forbidden fields (account, risk - inherited from Play)

Returns NormalizationResult with errors/warnings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.backtest.indicator_registry import get_registry
from src.backtest.rules.dsl_parser import parse_expr

from .block import Block


@dataclass
class NormalizationResult:
    """Result of normalization with errors, warnings, and validity status."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        """Return True if no errors."""
        return len(self.errors) == 0

    def add_error(self, msg: str) -> None:
        """Add an error message."""
        self.errors.append(msg)

    def add_warning(self, msg: str) -> None:
        """Add a warning message."""
        self.warnings.append(msg)


class NormalizationError(Exception):
    """Raised when normalization fails with critical errors."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(f"Normalization failed: {'; '.join(errors)}")


# Fields that are NOT allowed in Block (inherited from Play)
FORBIDDEN_BLOCK_FIELDS = {
    "account",
    "risk",
    "risk_model",
    "position_policy",
    "symbol",
    "symbol_universe",
    "execution_tf",
    "tf",
}


def normalize_block_strict(
    raw: dict[str, Any],
    fail_on_error: bool = True,
) -> tuple[Block | None, NormalizationResult]:
    """
    Normalize and validate a Block configuration.

    Pure function. No side effects. Fail-loud on invalid input.

    Validation rules:
    - Required fields: id, version, features (≥1), condition
    - All feature indicator_types must exist in INDICATOR_REGISTRY
    - Condition must be valid DSL (parseable)
    - No account/risk fields (inherited from Play)

    Args:
        raw: Raw dictionary from YAML
        fail_on_error: If True, raise NormalizationError on errors

    Returns:
        Tuple of (Block or None, NormalizationResult)

    Raises:
        NormalizationError: If fail_on_error=True and validation fails
    """
    result = NormalizationResult()

    # Check for forbidden fields
    for forbidden in FORBIDDEN_BLOCK_FIELDS:
        if forbidden in raw:
            result.add_error(
                f"Field '{forbidden}' not allowed in Block (inherited from Play)"
            )

    # Required fields
    if not raw.get("id"):
        result.add_error("Missing required field: id")

    if not raw.get("version"):
        result.add_error("Missing required field: version")

    features = raw.get("features")
    if not features:
        result.add_error("Missing required field: features (must have at least one)")
    elif not isinstance(features, list):
        result.add_error("Field 'features' must be a list")
    elif len(features) == 0:
        result.add_error("Field 'features' must have at least one entry")

    condition = raw.get("condition")
    if not condition:
        result.add_error("Missing required field: condition")

    # If we have critical errors, stop here
    if not result.valid:
        if fail_on_error:
            raise NormalizationError(result.errors)
        return None, result

    # Validate features against registry
    registry = get_registry()
    declared_feature_ids: set[str] = set()

    for i, feature in enumerate(features):
        if not isinstance(feature, dict):
            result.add_error(f"features[{i}]: must be a dict")
            continue

        feature_id = feature.get("id")
        if not feature_id:
            result.add_error(f"features[{i}]: missing 'id' field")
            continue

        declared_feature_ids.add(feature_id)

        feature_type = feature.get("type")
        if not feature_type:
            result.add_error(f"features[{i}] ({feature_id}): missing 'type' field")
            continue

        if feature_type == "indicator":
            indicator_type = feature.get("indicator_type")
            if not indicator_type:
                result.add_error(
                    f"features[{i}] ({feature_id}): missing 'indicator_type'"
                )
                continue

            # Check indicator exists in registry
            if not registry.is_supported(indicator_type):
                result.add_error(
                    f"features[{i}] ({feature_id}): indicator_type '{indicator_type}' "
                    f"not found in INDICATOR_REGISTRY"
                )
                continue

            # Validate params if provided
            params = feature.get("params", {})
            if params:
                try:
                    registry.validate_params(indicator_type, params)
                except ValueError as e:
                    result.add_error(
                        f"features[{i}] ({feature_id}): {e}"
                    )

        elif feature_type == "structure":
            # Structure validation (basic check)
            structure_type = feature.get("structure_type")
            if not structure_type:
                result.add_error(
                    f"features[{i}] ({feature_id}): missing 'structure_type'"
                )

        else:
            result.add_warning(
                f"features[{i}] ({feature_id}): unknown type '{feature_type}'"
            )

    # Validate condition DSL
    try:
        parse_expr(condition)
    except Exception as e:
        result.add_error(f"Invalid condition DSL: {e}")

    # Validate condition references declared features
    _validate_condition_refs(condition, declared_feature_ids, result)

    # If there are errors and fail_on_error, raise
    if not result.valid and fail_on_error:
        raise NormalizationError(result.errors)

    # Create Block if valid
    if result.valid:
        try:
            block = Block.from_dict(raw)
            return block, result
        except Exception as e:
            result.add_error(f"Failed to create Block: {e}")
            if fail_on_error:
                raise NormalizationError(result.errors)

    return None, result


def _validate_condition_refs(
    condition: dict[str, Any],
    declared_ids: set[str],
    result: NormalizationResult,
    path: str = "condition",
) -> None:
    """
    Recursively validate that condition references only declared features.

    Args:
        condition: DSL condition dict
        declared_ids: Set of declared feature IDs
        result: NormalizationResult to add errors to
        path: Current path for error messages
    """
    if not isinstance(condition, dict):
        return

    # Check for feature_id references in lhs/rhs
    for key in ("lhs", "rhs"):
        ref = condition.get(key)
        if isinstance(ref, dict) and "feature_id" in ref:
            feature_id = ref["feature_id"]
            # Built-in features are always available
            builtin_features = {"open", "high", "low", "close", "volume", "mark_price"}
            if feature_id not in declared_ids and feature_id not in builtin_features:
                result.add_warning(
                    f"{path}.{key}: references undeclared feature '{feature_id}'"
                )

    # Recurse into all/any/not
    if "all" in condition:
        for i, item in enumerate(condition["all"]):
            _validate_condition_refs(item, declared_ids, result, f"{path}.all[{i}]")

    if "any" in condition:
        for i, item in enumerate(condition["any"]):
            _validate_condition_refs(item, declared_ids, result, f"{path}.any[{i}]")

    if "not" in condition:
        _validate_condition_refs(condition["not"], declared_ids, result, f"{path}.not")

    # Window operators
    for window_op in ("holds_for", "occurred_within", "count_true"):
        if window_op in condition:
            window_data = condition[window_op]
            if "expr" in window_data:
                _validate_condition_refs(
                    window_data["expr"], declared_ids, result, f"{path}.{window_op}.expr"
                )
