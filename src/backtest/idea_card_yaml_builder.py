"""
IdeaCard YAML Builder: Build-time validation and normalization.

This module provides build-time validation for IdeaCard YAML files:
- Validates indicator types are supported (via IndicatorRegistry)
- Validates params are accepted by each indicator
- Validates all feature references use expanded keys (not base keys)
- Raises actionable errors before YAML is written

Key Design (per user specification):
    For each tf_config scope:
        declared_keys = set(all expanded output keys from feature_specs)
        base_to_expanded = { base_output_key: [expanded_keys...] }  # multi-output only
    
    On a miss:
        if missing_key in base_to_expanded:
            raise MULTI_OUTPUT_BASE_KEY_REFERENCED with suggestions
        else:
            raise UNDECLARED_FEATURE

Agent Rule:
    Agents may only generate IdeaCards through `backtest idea-card-normalize`
    and must refuse to write YAML if normalization fails.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Any, Tuple
from enum import Enum

from .indicator_registry import get_registry, IndicatorRegistry


# =============================================================================
# Error Types
# =============================================================================

class ValidationErrorCode(str, Enum):
    """Error codes for YAML validation."""
    UNSUPPORTED_INDICATOR = "UNSUPPORTED_INDICATOR"
    INVALID_PARAM = "INVALID_PARAM"
    MULTI_OUTPUT_BASE_KEY_REFERENCED = "MULTI_OUTPUT_BASE_KEY_REFERENCED"
    UNDECLARED_FEATURE = "UNDECLARED_FEATURE"
    UNKNOWN_TF_ROLE = "UNKNOWN_TF_ROLE"
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
    # Stage 3: Market structure validation
    UNSUPPORTED_STRUCTURE_TYPE = "UNSUPPORTED_STRUCTURE_TYPE"
    INVALID_STRUCTURE_PARAM = "INVALID_STRUCTURE_PARAM"
    STRUCTURE_EXEC_ONLY = "STRUCTURE_EXEC_ONLY"
    STRUCTURE_ZONES_NOT_SUPPORTED = "STRUCTURE_ZONES_NOT_SUPPORTED"
    UNDECLARED_STRUCTURE = "UNDECLARED_STRUCTURE"
    DUPLICATE_STRUCTURE_KEY = "DUPLICATE_STRUCTURE_KEY"
    INVALID_ENUM_TOKEN = "INVALID_ENUM_TOKEN"


@dataclass
class ValidationError:
    """A single validation error."""
    code: ValidationErrorCode
    message: str
    location: Optional[str] = None
    suggestions: Optional[List[str]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "code": self.code.value,
            "message": self.message,
        }
        if self.location:
            result["location"] = self.location
        if self.suggestions:
            result["suggestions"] = self.suggestions
        return result
    
    def __str__(self) -> str:
        s = f"[{self.code.value}] {self.message}"
        if self.location:
            s += f"\n  Location: {self.location}"
        if self.suggestions:
            s += f"\n  Suggestions: {self.suggestions}"
        return s


@dataclass
class ValidationResult:
    """Result of IdeaCard YAML validation."""
    is_valid: bool
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": self.warnings,
        }


# =============================================================================
# Scope Mappings (per user specification)
# =============================================================================

@dataclass
class ScopeMappings:
    """
    Mappings for a single tf_config scope.
    
    Attributes:
        role: The TF role ("exec", "htf", "mtf")
        declared_keys: All expanded output keys from feature_specs
        base_to_expanded: For multi-output specs, base_output_key -> [expanded_keys]
    """
    role: str
    declared_keys: Set[str] = field(default_factory=set)
    base_to_expanded: Dict[str, List[str]] = field(default_factory=dict)


def build_scope_mappings(
    tf_config: Dict[str, Any],
    role: str,
    registry: IndicatorRegistry,
) -> Tuple[ScopeMappings, List[ValidationError]]:
    """
    Build scope mappings for a single tf_config.
    
    Args:
        tf_config: The tf_config dict from YAML
        role: The TF role name
        registry: IndicatorRegistry instance
        
    Returns:
        Tuple of (ScopeMappings, list of ValidationErrors)
    """
    mappings = ScopeMappings(role=role)
    errors: List[ValidationError] = []
    
    feature_specs = tf_config.get("feature_specs", [])
    
    for i, spec in enumerate(feature_specs):
        indicator_type = spec.get("indicator_type", "")
        output_key = spec.get("output_key", "")
        params = spec.get("params", {})
        location = f"tf_configs.{role}.feature_specs[{i}]"
        
        # Validate indicator type is supported (registry check)
        if not registry.is_supported(indicator_type):
            errors.append(ValidationError(
                code=ValidationErrorCode.UNSUPPORTED_INDICATOR,
                message=f"Indicator type '{indicator_type}' is not supported.",
                location=location,
                suggestions=registry.list_indicators(),
            ))
            continue

        # Validate indicator is callable in pandas_ta (fail loud)
        try:
            import pandas_ta as ta
            ta_func = getattr(ta, indicator_type, None)
            if ta_func is None or not callable(ta_func):
                errors.append(ValidationError(
                    code=ValidationErrorCode.UNSUPPORTED_INDICATOR,
                    message=f"Indicator '{indicator_type}' is supported in registry but not callable in pandas_ta.",
                    location=location,
                ))
                continue
        except ImportError:
            errors.append(ValidationError(
                code=ValidationErrorCode.UNSUPPORTED_INDICATOR,
                message="pandas_ta not available for validation.",
                location=location,
            ))
            continue
        
        # Validate params are accepted
        try:
            registry.validate_params(indicator_type, params)
        except ValueError as e:
            errors.append(ValidationError(
                code=ValidationErrorCode.INVALID_PARAM,
                message=str(e),
                location=location,
            ))
        
        # Get expanded keys
        expanded_keys = registry.get_expanded_keys(indicator_type, output_key)
        
        # Add to declared_keys
        mappings.declared_keys.update(expanded_keys)
        
        # If multi-output, add to base_to_expanded
        if registry.is_multi_output(indicator_type):
            mappings.base_to_expanded[output_key] = expanded_keys
    
    return mappings, errors


def build_all_scope_mappings(
    idea_card_dict: Dict[str, Any],
    registry: IndicatorRegistry,
) -> Tuple[Dict[str, ScopeMappings], List[ValidationError]]:
    """
    Build scope mappings for all tf_configs.
    
    Args:
        idea_card_dict: The raw IdeaCard dict from YAML
        registry: IndicatorRegistry instance
        
    Returns:
        Tuple of (dict of role -> ScopeMappings, list of ValidationErrors)
    """
    all_mappings: Dict[str, ScopeMappings] = {}
    all_errors: List[ValidationError] = []
    
    tf_configs = idea_card_dict.get("tf_configs", {})
    
    for role, tf_config in tf_configs.items():
        mappings, errors = build_scope_mappings(tf_config, role, registry)
        all_mappings[role] = mappings
        all_errors.extend(errors)
    
    return all_mappings, all_errors


# =============================================================================
# Reference Validation
# =============================================================================

# OHLCV columns are always implicitly available
OHLCV_COLUMNS = {"open", "high", "low", "close", "volume", "timestamp"}


def validate_feature_reference(
    key: str,
    role: str,
    location: str,
    all_mappings: Dict[str, ScopeMappings],
) -> Optional[ValidationError]:
    """
    Validate a single feature reference.
    
    Args:
        key: The referenced key (e.g., "ema_fast", "macd")
        role: The TF role this reference is in
        location: Location string for error message
        all_mappings: All scope mappings
        
    Returns:
        ValidationError if invalid, None if valid
    """
    # OHLCV columns are always valid
    if key in OHLCV_COLUMNS:
        return None
    
    # Check if role exists
    if role not in all_mappings:
        return ValidationError(
            code=ValidationErrorCode.UNKNOWN_TF_ROLE,
            message=f"TF role '{role}' referenced but not configured.",
            location=location,
        )
    
    mappings = all_mappings[role]
    
    # Check if key is in declared_keys
    if key in mappings.declared_keys:
        return None
    
    # Check if key is a base key of a multi-output indicator
    if key in mappings.base_to_expanded:
        expanded = mappings.base_to_expanded[key]
        return ValidationError(
            code=ValidationErrorCode.MULTI_OUTPUT_BASE_KEY_REFERENCED,
            message=(
                f"Multi-output indicator '{key}' referenced by base key. "
                f"Use one of the expanded keys instead."
            ),
            location=location,
            suggestions=expanded,
        )
    
    # Key is truly undeclared
    return ValidationError(
        code=ValidationErrorCode.UNDECLARED_FEATURE,
        message=f"Feature '{key}' referenced but not declared in {role} TF.",
        location=location,
        suggestions=sorted(mappings.declared_keys)[:10] if mappings.declared_keys else None,
    )


def validate_signal_rules(
    idea_card_dict: Dict[str, Any],
    all_mappings: Dict[str, ScopeMappings],
) -> List[ValidationError]:
    """
    Validate all feature references in signal_rules.
    
    Args:
        idea_card_dict: The raw IdeaCard dict
        all_mappings: All scope mappings
        
    Returns:
        List of ValidationErrors
    """
    errors: List[ValidationError] = []
    signal_rules = idea_card_dict.get("signal_rules", {})
    
    # Entry rules
    for i, rule in enumerate(signal_rules.get("entry_rules", [])):
        for j, cond in enumerate(rule.get("conditions", [])):
            location = f"signal_rules.entry_rules[{i}].conditions[{j}]"
            role = cond.get("tf", "exec")

            # Check indicator_key
            indicator_key = cond.get("indicator_key", "")
            # Stage 3: Skip structure references (validated separately)
            if indicator_key and not indicator_key.startswith("structure."):
                error = validate_feature_reference(
                    indicator_key, role, f"{location}.indicator_key", all_mappings
                )
                if error:
                    errors.append(error)

            # Check value if it's an indicator comparison
            if cond.get("is_indicator_comparison", False):
                value = cond.get("value", "")
                # Stage 3: Skip structure references (validated separately)
                if isinstance(value, str) and value and not value.startswith("structure."):
                    error = validate_feature_reference(
                        value, role, f"{location}.value", all_mappings
                    )
                    if error:
                        errors.append(error)

    # Exit rules
    for i, rule in enumerate(signal_rules.get("exit_rules", [])):
        for j, cond in enumerate(rule.get("conditions", [])):
            location = f"signal_rules.exit_rules[{i}].conditions[{j}]"
            role = cond.get("tf", "exec")

            indicator_key = cond.get("indicator_key", "")
            # Stage 3: Skip structure references (validated separately)
            if indicator_key and not indicator_key.startswith("structure."):
                error = validate_feature_reference(
                    indicator_key, role, f"{location}.indicator_key", all_mappings
                )
                if error:
                    errors.append(error)

            if cond.get("is_indicator_comparison", False):
                value = cond.get("value", "")
                # Stage 3: Skip structure references (validated separately)
                if isinstance(value, str) and value and not value.startswith("structure."):
                    error = validate_feature_reference(
                        value, role, f"{location}.value", all_mappings
                    )
                    if error:
                        errors.append(error)
    
    return errors


def validate_risk_model_refs(
    idea_card_dict: Dict[str, Any],
    all_mappings: Dict[str, ScopeMappings],
) -> List[ValidationError]:
    """
    Validate feature references in risk_model (e.g., atr_key).
    
    Args:
        idea_card_dict: The raw IdeaCard dict
        all_mappings: All scope mappings (uses "exec" for risk model)
        
    Returns:
        List of ValidationErrors
    """
    errors: List[ValidationError] = []
    risk_model = idea_card_dict.get("risk_model", {})
    
    # Check stop_loss.atr_key
    stop_loss = risk_model.get("stop_loss", {})
    atr_key = stop_loss.get("atr_key")
    if atr_key:
        error = validate_feature_reference(
            atr_key, "exec", "risk_model.stop_loss.atr_key", all_mappings
        )
        if error:
            errors.append(error)
    
    # Check take_profit.atr_key
    take_profit = risk_model.get("take_profit", {})
    atr_key = take_profit.get("atr_key")
    if atr_key:
        error = validate_feature_reference(
            atr_key, "exec", "risk_model.take_profit.atr_key", all_mappings
        )
        if error:
            errors.append(error)
    
    return errors


# =============================================================================
# Structure Block Validation (Stage 3)
# =============================================================================

# Required params per structure type
STRUCTURE_REQUIRED_PARAMS = {
    "swing": ["left", "right"],
    "trend": [],  # TREND derives from SWING, no params required
}

# Valid structure types
VALID_STRUCTURE_TYPES = {"swing", "trend"}

# Public output fields per structure type (for reference validation)
STRUCTURE_PUBLIC_FIELDS = {
    "swing": {"swing_high_level", "swing_high_idx", "swing_low_level", "swing_low_idx", "swing_recency_bars"},
    "trend": {"trend_state", "parent_version"},
}

# =============================================================================
# Enum Token Maps (Stage 3.3)
# =============================================================================

# Import structure enums from source of truth
from src.backtest.market_structure.types import TrendState, ZoneState
from enum import Enum as EnumType
from typing import Union, Type

# Map field names to their enum classes
# Only enum fields should be listed here
# Keep namespace-specific: structure enums only
STRUCTURE_ENUM_FIELDS: Dict[str, Type[EnumType]] = {
    "trend_state": TrendState,
    # Future: "zone_state": ZoneState,
}


def normalize_enum_token(
    field_name: str,
    value: Union[str, int],
) -> int:
    """
    Normalize enum token to int value.

    Strict canonical tokens only - no numeric literals allowed for enum fields.
    Tokens are derived from enum class member names (case-insensitive).

    Args:
        field_name: The structure field name (e.g., "trend_state")
        value: String token (canonical enum member name)

    Returns:
        Int value if valid

    Raises:
        ValueError: If token is unknown or numeric literal used
        KeyError: If field is not an enum field
    """
    if field_name not in STRUCTURE_ENUM_FIELDS:
        raise KeyError(f"Field '{field_name}' is not a registered enum field")

    enum_class = STRUCTURE_ENUM_FIELDS[field_name]
    allowed = sorted(m.name for m in enum_class)

    # Reject numeric literals - require canonical tokens only
    if isinstance(value, int):
        raise ValueError(
            f"Enum field '{field_name}' requires canonical token, not numeric literal '{value}'. "
            f"Use one of: {', '.join(allowed)}"
        )

    if isinstance(value, str):
        # Uppercase for comparison (case-insensitive)
        token = value.upper()
        # Check membership against enum member names
        for member in enum_class:
            if member.name == token:
                return member.value
        # Unknown token
        raise ValueError(
            f"Unknown enum token '{value}' for field '{field_name}'. "
            f"Allowed tokens: {', '.join(allowed)}"
        )

    raise ValueError(
        f"Invalid value type for enum field '{field_name}': {type(value).__name__}. "
        f"Use one of: {', '.join(allowed)}"
    )


def validate_structure_blocks(
    idea_card_dict: Dict[str, Any],
) -> Tuple[List[ValidationError], Dict[str, Set[str]]]:
    """
    Validate market_structure_blocks in IdeaCard YAML.

    Stage 3 validation:
    - tf_role must be "exec" only
    - No zones allowed (Stage 5+)
    - Valid structure types (swing, trend)
    - Required params per type

    Args:
        idea_card_dict: The raw IdeaCard dict from YAML

    Returns:
        Tuple of (errors, structure_fields_by_key)
        structure_fields_by_key maps block_key -> set of valid field names
    """
    errors: List[ValidationError] = []
    structure_fields: Dict[str, Set[str]] = {}

    blocks = idea_card_dict.get("market_structure_blocks", [])
    if not blocks:
        return errors, structure_fields

    seen_keys = set()

    for i, block in enumerate(blocks):
        location = f"market_structure_blocks[{i}]"

        # Validate key exists and is unique
        key = block.get("key")
        if not key:
            errors.append(ValidationError(
                code=ValidationErrorCode.MISSING_REQUIRED_FIELD,
                message="Structure block missing 'key' field.",
                location=location,
            ))
            continue

        if key in seen_keys:
            errors.append(ValidationError(
                code=ValidationErrorCode.DUPLICATE_STRUCTURE_KEY,
                message=(
                    f"Duplicate structure block key: '{key}'. "
                    f"Each market_structure_block must have a unique key. "
                    f"Tip: Use TF suffix for clarity (e.g., 'swing_15m', 'trend_15m')."
                ),
                location=f"{location}.key",
            ))
        seen_keys.add(key)

        # Validate type
        struct_type = block.get("type")
        if not struct_type:
            errors.append(ValidationError(
                code=ValidationErrorCode.MISSING_REQUIRED_FIELD,
                message="Structure block missing 'type' field.",
                location=location,
            ))
            continue

        # Check for legacy key
        if block.get("structure_type"):
            errors.append(ValidationError(
                code=ValidationErrorCode.INVALID_STRUCTURE_PARAM,
                message="Use 'type', not 'structure_type'. Legacy key not supported.",
                location=f"{location}.structure_type",
            ))

        if struct_type not in VALID_STRUCTURE_TYPES:
            errors.append(ValidationError(
                code=ValidationErrorCode.UNSUPPORTED_STRUCTURE_TYPE,
                message=f"Unknown structure type '{struct_type}'.",
                location=f"{location}.type",
                suggestions=sorted(VALID_STRUCTURE_TYPES),
            ))
            continue

        # Stage 3: tf_role must be "exec" only
        tf_role = block.get("tf_role", "exec")
        if tf_role != "exec":
            errors.append(ValidationError(
                code=ValidationErrorCode.STRUCTURE_EXEC_ONLY,
                message=(
                    f"Stage 3 supports exec-only market structure blocks. "
                    f"tf_role='{tf_role}' is not supported until Stage 4."
                ),
                location=f"{location}.tf_role",
            ))

        # Stage 3: No zones
        if block.get("zones"):
            errors.append(ValidationError(
                code=ValidationErrorCode.STRUCTURE_ZONES_NOT_SUPPORTED,
                message=(
                    "Zones in market_structure_blocks are not supported until Stage 5+. "
                    "Remove the 'zones' key from your structure block."
                ),
                location=f"{location}.zones",
            ))

        # Validate required params
        params = block.get("params", {})
        required = STRUCTURE_REQUIRED_PARAMS.get(struct_type, [])
        for param in required:
            if param not in params:
                errors.append(ValidationError(
                    code=ValidationErrorCode.INVALID_STRUCTURE_PARAM,
                    message=f"Structure type '{struct_type}' requires param '{param}'.",
                    location=f"{location}.params",
                ))

        # Track valid fields for this block
        if struct_type in STRUCTURE_PUBLIC_FIELDS:
            structure_fields[key] = STRUCTURE_PUBLIC_FIELDS[struct_type]

    return errors, structure_fields


def validate_structure_references(
    idea_card_dict: Dict[str, Any],
    structure_fields: Dict[str, Set[str]],
) -> List[ValidationError]:
    """
    Validate structure references in signal_rules.

    Checks conditions that reference structure.<block_key>.<field>.
    Stage 3.3: Also normalizes enum tokens (e.g., "BULL" -> 1 for trend_state).

    Args:
        idea_card_dict: The raw IdeaCard dict (modified in-place for normalization)
        structure_fields: Dict from validate_structure_blocks()

    Returns:
        List of ValidationErrors
    """
    errors: List[ValidationError] = []

    # For now, structure references in signal rules use the indicator_key field
    # with format "structure.<block_key>.<field>" parsed at runtime.
    # Validation here ensures referenced blocks/fields exist.

    signal_rules = idea_card_dict.get("signal_rules", {})

    for rule_type in ["entry_rules", "exit_rules"]:
        for i, rule in enumerate(signal_rules.get(rule_type, [])):
            for j, cond in enumerate(rule.get("conditions", [])):
                indicator_key = cond.get("indicator_key", "")
                location = f"signal_rules.{rule_type}[{i}].conditions[{j}].indicator_key"
                value_location = f"signal_rules.{rule_type}[{i}].conditions[{j}].value"

                # Check if this is a structure reference
                if indicator_key.startswith("structure."):
                    parts = indicator_key.split(".")
                    if len(parts) < 3:
                        errors.append(ValidationError(
                            code=ValidationErrorCode.UNDECLARED_STRUCTURE,
                            message=f"Invalid structure reference: '{indicator_key}'. Expected format: structure.<block_key>.<field>",
                            location=location,
                        ))
                        continue

                    block_key = parts[1]
                    field_name = parts[2]

                    # Check block exists
                    if block_key not in structure_fields:
                        errors.append(ValidationError(
                            code=ValidationErrorCode.UNDECLARED_STRUCTURE,
                            message=f"Structure block '{block_key}' referenced but not declared in market_structure_blocks.",
                            location=location,
                            suggestions=sorted(structure_fields.keys()) if structure_fields else None,
                        ))
                        continue

                    # Check field exists
                    valid_fields = structure_fields[block_key]
                    if field_name not in valid_fields:
                        errors.append(ValidationError(
                            code=ValidationErrorCode.UNDECLARED_STRUCTURE,
                            message=f"Structure field '{field_name}' not valid for block '{block_key}'.",
                            location=location,
                            suggestions=sorted(valid_fields),
                        ))
                        continue

                    # Stage 3.3: Validate and normalize enum tokens
                    # Strict canonical tokens only - no numeric literals for enum fields
                    value = cond.get("value")

                    if field_name in STRUCTURE_ENUM_FIELDS:
                        # Enum field - require canonical token, reject numeric
                        try:
                            normalized = normalize_enum_token(field_name, value)
                            cond["value"] = normalized
                        except ValueError as e:
                            # Unknown token or numeric literal
                            enum_class = STRUCTURE_ENUM_FIELDS[field_name]
                            allowed = sorted(m.name for m in enum_class)
                            errors.append(ValidationError(
                                code=ValidationErrorCode.INVALID_ENUM_TOKEN,
                                message=str(e),
                                location=value_location,
                                suggestions=allowed,
                            ))
                    elif isinstance(value, str):
                        # String value on non-enum field
                        errors.append(ValidationError(
                            code=ValidationErrorCode.INVALID_ENUM_TOKEN,
                            message=(
                                f"Field '{field_name}' is not an enum field. "
                                f"Use numeric value instead of '{value}'."
                            ),
                            location=value_location,
                        ))

    return errors


# =============================================================================
# Main Entry Points
# =============================================================================

def validate_idea_card_yaml(idea_card_dict: Dict[str, Any]) -> ValidationResult:
    """
    Validate an IdeaCard YAML dict at build time.

    This is the main validation entry point. It:
    1. Validates all indicator_types are supported
    2. Validates all params are accepted
    3. Validates all signal_rules/risk_model references use expanded keys
    4. Validates market_structure_blocks (Stage 3)

    Args:
        idea_card_dict: The raw IdeaCard dict from YAML

    Returns:
        ValidationResult with is_valid and list of errors
    """
    registry = get_registry()
    all_errors: List[ValidationError] = []

    # Build scope mappings (also validates indicator types and params)
    all_mappings, mapping_errors = build_all_scope_mappings(idea_card_dict, registry)
    all_errors.extend(mapping_errors)

    # Validate market structure blocks (Stage 3)
    structure_errors, structure_fields = validate_structure_blocks(idea_card_dict)
    all_errors.extend(structure_errors)

    # Validate signal rules references (indicators)
    signal_errors = validate_signal_rules(idea_card_dict, all_mappings)
    all_errors.extend(signal_errors)

    # Validate structure references in signal rules
    if structure_fields:
        structure_ref_errors = validate_structure_references(idea_card_dict, structure_fields)
        all_errors.extend(structure_ref_errors)

    # Validate risk model references
    risk_errors = validate_risk_model_refs(idea_card_dict, all_mappings)
    all_errors.extend(risk_errors)

    is_valid = len(all_errors) == 0

    return ValidationResult(
        is_valid=is_valid,
        errors=all_errors,
    )


def generate_required_indicators(
    idea_card_dict: Dict[str, Any],
) -> Dict[str, List[str]]:
    """
    Generate required_indicators for each TF role.
    
    This auto-generates required_indicators from the declared feature_specs,
    so users don't need to manually maintain this list.
    
    Args:
        idea_card_dict: The raw IdeaCard dict
        
    Returns:
        Dict of role -> list of required indicator keys
    """
    registry = get_registry()
    result: Dict[str, List[str]] = {}
    
    tf_configs = idea_card_dict.get("tf_configs", {})
    
    for role, tf_config in tf_configs.items():
        keys: List[str] = []
        feature_specs = tf_config.get("feature_specs", [])
        
        for spec in feature_specs:
            indicator_type = spec.get("indicator_type", "")
            output_key = spec.get("output_key", "")
            
            if registry.is_supported(indicator_type):
                expanded = registry.get_expanded_keys(indicator_type, output_key)
                keys.extend(expanded)
        
        if keys:
            result[role] = sorted(set(keys))
    
    return result


def normalize_idea_card_yaml(
    idea_card_dict: Dict[str, Any],
    auto_generate_required: bool = True,
) -> Tuple[Dict[str, Any], ValidationResult]:
    """
    Normalize and validate an IdeaCard YAML dict.
    
    This is the main entry point for the YAML builder. It:
    1. Validates the YAML (fails loud if invalid)
    2. Optionally auto-generates required_indicators
    3. Returns the normalized dict
    
    Args:
        idea_card_dict: The raw IdeaCard dict from YAML
        auto_generate_required: If True, auto-generate required_indicators
        
    Returns:
        Tuple of (normalized dict, ValidationResult)
        
    Note:
        If validation fails (is_valid=False), the returned dict is unchanged.
        Callers should refuse to write YAML if validation fails.
    """
    # Validate first
    result = validate_idea_card_yaml(idea_card_dict)
    
    if not result.is_valid:
        # Return unchanged - caller should refuse to write
        return idea_card_dict, result
    
    # Make a copy for normalization
    normalized = dict(idea_card_dict)
    
    # Auto-generate required_indicators if requested
    if auto_generate_required:
        required_by_role = generate_required_indicators(normalized)
        
        # Update each tf_config with generated required_indicators
        tf_configs = normalized.get("tf_configs", {})
        for role, keys in required_by_role.items():
            if role in tf_configs:
                tf_configs[role]["required_indicators"] = keys
    
    return normalized, result


def format_validation_errors(errors: List[ValidationError]) -> str:
    """
    Format validation errors for display.
    
    Args:
        errors: List of ValidationErrors
        
    Returns:
        Formatted string for display
    """
    if not errors:
        return "No errors."
    
    lines = [
        "=" * 60,
        "IDEACARD YAML VALIDATION FAILED",
        "=" * 60,
    ]
    
    for i, error in enumerate(errors, 1):
        lines.append(f"\n{i}. [{error.code.value}]")
        lines.append(f"   {error.message}")
        if error.location:
            lines.append(f"   Location: {error.location}")
        if error.suggestions:
            if len(error.suggestions) <= 5:
                lines.append(f"   Suggestions: {error.suggestions}")
            else:
                lines.append(f"   Suggestions: {error.suggestions[:5]}... ({len(error.suggestions)} total)")
    
    lines.append("\n" + "=" * 60)
    lines.append("FIX: Correct the errors above and re-run normalization.")
    lines.append("=" * 60)

    return "\n".join(lines)


# =============================================================================
# Stage 4c: Condition Compilation with Strict Validation
# =============================================================================
# Compiles condition references at normalization time for O(1) hot-loop evaluation.
# All validation happens here - unsupported constructs never reach hot loop.


class ConditionCompileError(ValueError):
    """
    Error during condition compilation with actionable message.

    Stage 4c: All unsupported operators/constructs must fail at compile time.
    """

    def __init__(
        self,
        message: str,
        operator: Optional[str] = None,
        lhs: Optional[str] = None,
        rhs: Optional[str] = None,
    ):
        self.operator = operator
        self.lhs = lhs
        self.rhs = rhs
        full_msg = f"Condition compile error: {message}"
        if operator:
            full_msg += f"\n  Operator: {operator}"
        if lhs:
            full_msg += f"\n  LHS: {lhs}"
        if rhs:
            full_msg += f"\n  RHS: {rhs}"
        super().__init__(full_msg)


def _validate_condition_operator(condition: "Condition") -> None:
    """
    Validate operator at compile time using registry.

    Stage 4c: Unsupported operators fail here, never reach hot loop.

    Args:
        condition: The condition to validate

    Raises:
        ConditionCompileError: If operator is unsupported or invalid
    """
    from .rules.registry import validate_operator, get_operator_spec
    import math

    op_str = condition.operator.value

    # Check operator is supported
    error = validate_operator(op_str)
    if error:
        raise ConditionCompileError(
            error,
            operator=op_str,
            lhs=condition.indicator_key,
            rhs=str(condition.value),
        )

    spec = get_operator_spec(op_str)

    # Validate tolerance for approx_eq
    if spec.needs_tolerance:
        if condition.tolerance is None:
            raise ConditionCompileError(
                f"Operator '{op_str}' requires 'tolerance' parameter",
                operator=op_str,
                lhs=condition.indicator_key,
                rhs=str(condition.value),
            )
        if not isinstance(condition.tolerance, (int, float)):
            raise ConditionCompileError(
                f"Tolerance must be a number, got {type(condition.tolerance).__name__}",
                operator=op_str,
            )
        if math.isnan(condition.tolerance) or math.isinf(condition.tolerance):
            raise ConditionCompileError(
                f"Tolerance must be finite, got {condition.tolerance}",
                operator=op_str,
            )
        if condition.tolerance <= 0:
            raise ConditionCompileError(
                f"Tolerance must be > 0, got {condition.tolerance}",
                operator=op_str,
            )

    # Validate eq operator rejects float literals
    if op_str == "eq" and not condition.is_indicator_comparison:
        if isinstance(condition.value, float):
            raise ConditionCompileError(
                "Operator 'eq' does not allow float literals. "
                "Use 'approx_eq' with tolerance for float comparison.",
                operator=op_str,
                lhs=condition.indicator_key,
                rhs=str(condition.value),
            )


def compile_condition(
    condition: "Condition",
    available_indicators: Optional[Dict[str, List[str]]] = None,
    available_structures: Optional[List[str]] = None,
) -> "Condition":
    """
    Compile a Condition's references for O(1) hot-loop evaluation.

    Stage 4c: All validation happens here. Unsupported operators/constructs
    fail at compile time with actionable error messages.

    Takes an existing Condition and returns a new one with compiled lhs_ref
    and rhs_ref fields populated.

    Args:
        condition: The Condition to compile
        available_indicators: Dict of tf_role -> list of indicator keys
        available_structures: List of structure block keys

    Returns:
        New Condition with compiled refs

    Raises:
        ConditionCompileError: If operator is unsupported
        ValueError: If reference path is invalid
    """
    from .rules.compile import compile_ref

    # Stage 4c: Validate operator first (fail fast for unsupported operators)
    _validate_condition_operator(condition)

    # Build LHS path from indicator_key and tf
    indicator_key = condition.indicator_key
    tf = condition.tf

    if indicator_key.startswith("structure."):
        lhs_path = indicator_key
    elif indicator_key.startswith("price."):
        lhs_path = indicator_key
    else:
        # Build indicator path with namespace
        lhs_path = f"indicator.{indicator_key}"
        if tf != "exec":
            lhs_path = f"indicator.{indicator_key}.{tf}"

    # Compile LHS
    lhs_ref = compile_ref(
        lhs_path,
        available_indicators=available_indicators,
        available_structures=available_structures,
    )

    # Compile RHS (value - can be literal or indicator path)
    if condition.is_indicator_comparison:
        # Value is another indicator path - also need to build full path
        value_str = str(condition.value)
        if value_str.startswith("structure.") or value_str.startswith("price."):
            rhs_path = value_str
        else:
            rhs_path = f"indicator.{value_str}"
            if tf != "exec":
                rhs_path = f"indicator.{value_str}.{tf}"
        rhs_ref = compile_ref(
            rhs_path,
            available_indicators=available_indicators,
            available_structures=available_structures,
        )
    else:
        # Value is a literal
        rhs_ref = compile_ref(condition.value)

    # Create new Condition with compiled refs
    from .idea_card import Condition as ConditionClass

    return ConditionClass(
        indicator_key=condition.indicator_key,
        operator=condition.operator,
        value=condition.value,
        is_indicator_comparison=condition.is_indicator_comparison,
        tf=condition.tf,
        prev_offset=condition.prev_offset,
        lhs_ref=lhs_ref,
        rhs_ref=rhs_ref,
        tolerance=condition.tolerance,
    )


def compile_signal_rules(
    signal_rules: "SignalRules",
    available_indicators: Optional[Dict[str, List[str]]] = None,
    available_structures: Optional[List[str]] = None,
) -> "SignalRules":
    """
    Compile all conditions in SignalRules.

    Args:
        signal_rules: SignalRules to compile
        available_indicators: Dict of tf_role -> list of indicator keys
        available_structures: List of structure block keys

    Returns:
        New SignalRules with all conditions compiled
    """
    from .idea_card import SignalRules, EntryRule, ExitRule

    # Compile entry rules
    compiled_entry_rules = []
    for rule in signal_rules.entry_rules:
        compiled_conditions = tuple(
            compile_condition(cond, available_indicators, available_structures)
            for cond in rule.conditions
        )
        compiled_entry_rules.append(
            EntryRule(direction=rule.direction, conditions=compiled_conditions)
        )

    # Compile exit rules
    compiled_exit_rules = []
    for rule in signal_rules.exit_rules:
        compiled_conditions = tuple(
            compile_condition(cond, available_indicators, available_structures)
            for cond in rule.conditions
        )
        compiled_exit_rules.append(
            ExitRule(direction=rule.direction, conditions=compiled_conditions)
        )

    return SignalRules(
        entry_rules=tuple(compiled_entry_rules),
        exit_rules=tuple(compiled_exit_rules),
    )


def compile_idea_card(
    idea_card: "IdeaCard",
) -> "IdeaCard":
    """
    Compile all conditions in an IdeaCard for O(1) hot-loop evaluation.

    This is a post-processing step that takes a validated IdeaCard and returns
    a new one with all condition references compiled.

    Args:
        idea_card: The validated IdeaCard to compile

    Returns:
        New IdeaCard with compiled condition refs

    Note:
        This should be called AFTER validation passes, before engine startup.
        Compiled refs enable O(1) value resolution in the hot loop.
    """
    if idea_card.signal_rules is None:
        return idea_card  # Nothing to compile

    # Build context for compilation - Dict[tf_role, List[indicator_keys]]
    available_indicators: Dict[str, List[str]] = {}
    for role, tf_config in idea_card.tf_configs.items():
        keys = [spec.output_key for spec in tf_config.feature_specs]
        # Add OHLCV which is always available
        keys.extend(["open", "high", "low", "close", "volume"])
        available_indicators[role] = keys

    # Build structure keys
    available_structures: List[str] = []
    if idea_card.market_structure_blocks:
        available_structures = [block.key for block in idea_card.market_structure_blocks]

    # Compile signal rules
    compiled_rules = compile_signal_rules(
        idea_card.signal_rules,
        available_indicators,
        available_structures,
    )

    # Create new IdeaCard with compiled rules
    # Since IdeaCard is frozen, we need to create a new instance
    from dataclasses import replace
    return replace(idea_card, signal_rules=compiled_rules)

