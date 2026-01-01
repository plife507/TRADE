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
            if indicator_key:
                error = validate_feature_reference(
                    indicator_key, role, f"{location}.indicator_key", all_mappings
                )
                if error:
                    errors.append(error)
            
            # Check value if it's an indicator comparison
            if cond.get("is_indicator_comparison", False):
                value = cond.get("value", "")
                if isinstance(value, str) and value:
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
            if indicator_key:
                error = validate_feature_reference(
                    indicator_key, role, f"{location}.indicator_key", all_mappings
                )
                if error:
                    errors.append(error)
            
            if cond.get("is_indicator_comparison", False):
                value = cond.get("value", "")
                if isinstance(value, str) and value:
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
# Main Entry Points
# =============================================================================

def validate_idea_card_yaml(idea_card_dict: Dict[str, Any]) -> ValidationResult:
    """
    Validate an IdeaCard YAML dict at build time.
    
    This is the main validation entry point. It:
    1. Validates all indicator_types are supported
    2. Validates all params are accepted
    3. Validates all signal_rules/risk_model references use expanded keys
    
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
    
    # Validate signal rules references
    signal_errors = validate_signal_rules(idea_card_dict, all_mappings)
    all_errors.extend(signal_errors)
    
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

