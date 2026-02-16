"""
Backtest gates for production enforcement.

Indicator Requirements Gate: validates that all required indicator keys
declared in the Play are available after feature computation.
"""

from .indicator_requirements_gate import (
    IndicatorGateStatus,
    RoleValidationResult,
    IndicatorRequirementsResult,
    validate_indicator_requirements,
    extract_available_keys_from_dataframe,
)

__all__ = [
    "IndicatorGateStatus",
    "RoleValidationResult",
    "IndicatorRequirementsResult",
    "validate_indicator_requirements",
    "extract_available_keys_from_dataframe",
]
