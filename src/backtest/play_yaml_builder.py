"""
Play YAML Builder: Build-time validation and normalization.

This module provides build-time validation for Play YAML files:
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
    Agents may only generate Plays through `backtest play-normalize`
    and must refuse to write YAML if normalization fails.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
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
    location: str | None = None
    suggestions: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
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
    """Result of Play YAML validation."""
    is_valid: bool
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
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
    declared_keys: set[str] = field(default_factory=set)
    base_to_expanded: dict[str, list[str]] = field(default_factory=dict)


def build_scope_mappings(
    tf_config: dict[str, Any],
    role: str,
    registry: IndicatorRegistry,
) -> tuple[ScopeMappings, list[ValidationError]]:
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
    errors: list[ValidationError] = []
    
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
    play_dict: dict[str, Any],
    registry: IndicatorRegistry,
) -> tuple[dict[str, ScopeMappings], list[ValidationError]]:
    """
    Build scope mappings for all tf_configs.
    
    Args:
        play_dict: The raw Play dict from YAML
        registry: IndicatorRegistry instance
        
    Returns:
        Tuple of (dict of role -> ScopeMappings, list of ValidationErrors)
    """
    all_mappings: dict[str, ScopeMappings] = {}
    all_errors: list[ValidationError] = []
    
    tf_configs = play_dict.get("tf_configs", {})
    
    for role, tf_config in tf_configs.items():
        mappings, errors = build_scope_mappings(tf_config, role, registry)
        all_mappings[role] = mappings
        all_errors.extend(errors)
    
    return all_mappings, all_errors


# =============================================================================
# Reference Validation
# =============================================================================

# OHLCV columns and builtin price features are always implicitly available
# mark_price is a runtime builtin - accessible via snapshot_view.get_feature()
OHLCV_COLUMNS = {"open", "high", "low", "close", "volume", "timestamp", "mark_price"}


def validate_feature_reference(
    key: str,
    role: str,
    location: str,
    all_mappings: dict[str, ScopeMappings],
) -> ValidationError | None:
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


# REMOVED: validate_signal_rules() - Legacy signal_rules format deprecated
# All Plays now use blocks DSL v3.0.0. See configs/plays/README.md


def validate_risk_model_refs(
    play_dict: dict[str, Any],
    all_mappings: dict[str, ScopeMappings],
) -> list[ValidationError]:
    """
    Validate feature references in risk_model (e.g., atr_key).
    
    Args:
        play_dict: The raw Play dict
        all_mappings: All scope mappings (uses "exec" for risk model)
        
    Returns:
        List of ValidationErrors
    """
    errors: list[ValidationError] = []
    risk_model = play_dict.get("risk_model", {})
    
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

# Import structure enums and zone fields from source of truth
from src.backtest.market_structure.types import TrendState, ZoneState
from src.backtest.market_structure.detectors import ZONE_PUBLIC_FIELDS
from enum import Enum as EnumType

# Map field names to their enum classes
# Only enum fields should be listed here
# Keep namespace-specific: structure enums only
STRUCTURE_ENUM_FIELDS: dict[str, type[EnumType]] = {
    "trend_state": TrendState,
    "state": ZoneState,  # Stage 5+: Zone state field (NONE/ACTIVE/BROKEN)
}


def normalize_enum_token(
    field_name: str,
    value: str | int,
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
    play_dict: dict[str, Any],
) -> tuple[list[ValidationError], dict[str, set[str]], dict[str, set[str]]]:
    """
    Validate market_structure_blocks in Play YAML.

    Stage 3+ validation:
    - tf_role must be "exec" only
    - Zones allowed on SWING blocks (Stage 5+)
    - Valid structure types (swing, trend)
    - Required params per type

    Args:
        play_dict: The raw Play dict from YAML

    Returns:
        Tuple of (errors, structure_fields_by_key, zone_keys_by_block)
        - structure_fields_by_key: maps block_key -> set of valid field names
        - zone_keys_by_block: maps block_key -> set of zone keys (Stage 5+)
    """
    errors: list[ValidationError] = []
    structure_fields: dict[str, set[str]] = {}
    zone_keys: dict[str, set[str]] = {}  # Stage 5+: block_key -> {zone_key, ...}

    blocks = play_dict.get("market_structure_blocks", [])
    if not blocks:
        return errors, structure_fields, zone_keys

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

        # Stage 5+: Zones supported for SWING blocks only
        # Zone validation now handled by StructureSpec.from_dict()

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

        # Stage 5+: Track zone keys for this block
        zones = block.get("zones", [])
        if zones:
            zone_keys[key] = {z.get("key") for z in zones if z.get("key")}

    return errors, structure_fields, zone_keys


# REMOVED: validate_structure_references() - Legacy signal_rules format deprecated
# Structure references in blocks DSL are validated by dsl_parser.py


# =============================================================================
# Main Entry Points
# =============================================================================

def validate_play_yaml(play_dict: dict[str, Any]) -> ValidationResult:
    """
    Validate a Play YAML dict at build time.

    This is the main validation entry point. It:
    1. Validates all indicator_types are supported
    2. Validates all params are accepted
    3. Validates market_structure_blocks
    4. Validates risk_model references

    NOTE: Legacy signal_rules validation removed. All Plays now use
    blocks DSL v3.0.0, validated by dsl_parser.py at parse time.

    Args:
        play_dict: The raw Play dict from YAML

    Returns:
        ValidationResult with is_valid and list of errors
    """
    registry = get_registry()
    all_errors: list[ValidationError] = []

    # Build scope mappings (also validates indicator types and params)
    all_mappings, mapping_errors = build_all_scope_mappings(play_dict, registry)
    all_errors.extend(mapping_errors)

    # Validate market structure blocks
    structure_errors, _structure_fields, _zone_keys = validate_structure_blocks(play_dict)
    all_errors.extend(structure_errors)

    # Validate risk model references
    risk_errors = validate_risk_model_refs(play_dict, all_mappings)
    all_errors.extend(risk_errors)

    is_valid = len(all_errors) == 0

    return ValidationResult(
        is_valid=is_valid,
        errors=all_errors,
    )


def generate_required_indicators(
    play_dict: dict[str, Any],
) -> dict[str, list[str]]:
    """
    Generate required_indicators for each TF role.
    
    This auto-generates required_indicators from the declared feature_specs,
    so users don't need to manually maintain this list.
    
    Args:
        play_dict: The raw Play dict
        
    Returns:
        Dict of role -> list of required indicator keys
    """
    registry = get_registry()
    result: dict[str, list[str]] = {}
    
    tf_configs = play_dict.get("tf_configs", {})
    
    for role, tf_config in tf_configs.items():
        keys: list[str] = []
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


def normalize_play_yaml(
    play_dict: dict[str, Any],
    auto_generate_required: bool = True,
) -> tuple[dict[str, Any], ValidationResult]:
    """
    Normalize and validate a Play YAML dict.
    
    This is the main entry point for the YAML builder. It:
    1. Validates the YAML (fails loud if invalid)
    2. Optionally auto-generates required_indicators
    3. Returns the normalized dict
    
    Args:
        play_dict: The raw Play dict from YAML
        auto_generate_required: If True, auto-generate required_indicators
        
    Returns:
        Tuple of (normalized dict, ValidationResult)
        
    Note:
        If validation fails (is_valid=False), the returned dict is unchanged.
        Callers should refuse to write YAML if validation fails.
    """
    # Validate first
    result = validate_play_yaml(play_dict)
    
    if not result.is_valid:
        # Return unchanged - caller should refuse to write
        return play_dict, result
    
    # Make a copy for normalization
    normalized = dict(play_dict)
    
    # Auto-generate required_indicators if requested
    if auto_generate_required:
        required_by_role = generate_required_indicators(normalized)
        
        # Update each tf_config with generated required_indicators
        tf_configs = normalized.get("tf_configs", {})
        for role, keys in required_by_role.items():
            if role in tf_configs:
                tf_configs[role]["required_indicators"] = keys
    
    return normalized, result


def format_validation_errors(errors: list[ValidationError]) -> str:
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
        "PLAY YAML VALIDATION FAILED",
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
# Stage 4c: DSL Block Validation
# =============================================================================
# Blocks are validated at parse time by dsl_parser.py
# All operator/expression validation happens in dsl_nodes.py and dsl_eval.py



