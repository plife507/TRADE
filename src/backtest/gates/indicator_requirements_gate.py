"""
Indicator Requirements Gate.

Validates that all required indicator keys declared in the IdeaCard
are available after feature computation, before signal evaluation.

This gate ensures:
- No silent KeyErrors or NaN access during rule evaluation
- Missing indicators fail loudly with actionable error messages
- Exact match between declared requirements and computed features

Gate runs AFTER FeatureFrameBuilder computes indicators.
Gate runs BEFORE signal_rules evaluation.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ..play import IdeaCard


class IndicatorGateStatus(str, Enum):
    """Status of indicator requirements gate."""
    PASSED = "passed"       # All required indicators available
    FAILED = "failed"       # Missing required indicators
    SKIPPED = "skipped"     # No required indicators declared


@dataclass
class RoleValidationResult:
    """Validation result for a single TF role."""
    role: str
    tf: str
    passed: bool
    required_keys: list[str]
    available_keys: list[str]
    missing_keys: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "tf": self.tf,
            "passed": self.passed,
            "required_keys": self.required_keys,
            "available_keys": self.available_keys,
            "missing_keys": self.missing_keys,
        }


@dataclass
class IndicatorRequirementsResult:
    """
    Result of indicator requirements validation.

    Contains per-role validation results and overall status.
    """
    status: IndicatorGateStatus
    role_results: dict[str, RoleValidationResult] = field(default_factory=dict)
    error_message: str | None = None
    
    @property
    def passed(self) -> bool:
        return self.status == IndicatorGateStatus.PASSED
    
    @property
    def failed(self) -> bool:
        return self.status == IndicatorGateStatus.FAILED
    
    def get_missing_keys_by_role(self) -> dict[str, list[str]]:
        """Get missing keys grouped by role."""
        return {
            role: result.missing_keys
            for role, result in self.role_results.items()
            if result.missing_keys
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "passed": self.passed,
            "role_results": {
                role: result.to_dict() 
                for role, result in self.role_results.items()
            },
            "error_message": self.error_message,
        }
    
    def format_error(self) -> str:
        """Format actionable error message."""
        if self.passed:
            return ""
        
        lines = [
            "INDICATOR REQUIREMENTS GATE FAILED",
            "=" * 50,
        ]
        
        for role, result in self.role_results.items():
            if not result.passed:
                lines.append(f"\n[{role.upper()}] ({result.tf}):")
                lines.append(f"  Missing keys: {sorted(result.missing_keys)}")
                lines.append(f"  Available keys: {sorted(result.available_keys)}")
                lines.append(f"  Required keys: {sorted(result.required_keys)}")
        
        lines.append("\n" + "-" * 50)
        lines.append("FIX: Check that FeatureSpec output_key names match required_indicators.")
        lines.append("     Verify indicator_type produces expected columns.")
        lines.append("     Multi-output indicators may need suffixes (e.g., macd_signal).")
        lines.append("=" * 50)
        
        return "\n".join(lines)


def validate_indicator_requirements(
    idea_card: IdeaCard,
    available_keys_by_role: dict[str, set[str]],
) -> IndicatorRequirementsResult:
    """
    Validate that all required indicator keys are available.

    This gate runs after feature computation (FeatureFrameBuilder) and
    before signal evaluation. It ensures:
    - All features declared in the registry are available
    - Missing keys produce actionable error messages
    - Gate fails loudly, no silent NaNs or KeyErrors

    Args:
        idea_card: IdeaCard with features declared in feature_registry
        available_keys_by_role: Dict of TF -> set of available indicator keys
            (from computed feature frames)

    Returns:
        IndicatorRequirementsResult with pass/fail status and details
    """
    role_results: dict[str, RoleValidationResult] = {}
    all_passed = True
    has_requirements = False

    # Use feature_registry to get features by TF
    registry = idea_card.feature_registry
    for tf in registry.get_all_tfs():
        features = registry.get_for_tf(tf)
        # Get required keys from features (feature IDs + output_keys)
        required = set()
        for f in features:
            required.add(f.id)
            if f.output_keys:
                required.update(f.output_keys)

        available = available_keys_by_role.get(tf, set())

        if not required:
            # No requirements declared for this TF
            role_results[tf] = RoleValidationResult(
                role=tf,
                tf=tf,
                passed=True,
                required_keys=[],
                available_keys=sorted(available),
                missing_keys=[],
            )
            continue

        has_requirements = True

        # Check which required keys are missing
        missing = required - available

        passed = len(missing) == 0
        if not passed:
            all_passed = False

        role_results[tf] = RoleValidationResult(
            role=tf,
            tf=tf,
            passed=passed,
            required_keys=sorted(required),
            available_keys=sorted(available),
            missing_keys=sorted(missing),
        )
    
    # Determine overall status
    if not has_requirements:
        status = IndicatorGateStatus.SKIPPED
        error_message = None
    elif all_passed:
        status = IndicatorGateStatus.PASSED
        error_message = None
    else:
        status = IndicatorGateStatus.FAILED
        # Build error message
        missing_by_role = {
            role: result.missing_keys
            for role, result in role_results.items()
            if result.missing_keys
        }
        error_message = (
            f"Missing required indicators: {missing_by_role}. "
            "Check that FeatureSpec output_key names match required_indicators."
        )
    
    result = IndicatorRequirementsResult(
        status=status,
        role_results=role_results,
        error_message=error_message,
    )
    
    return result


def extract_available_keys_from_dataframe(
    df: "pd.DataFrame",
    exclude_ohlcv: bool = True,
) -> set[str]:
    """
    Extract available indicator keys from a computed DataFrame.
    
    Args:
        df: DataFrame with computed indicators
        exclude_ohlcv: If True, exclude standard OHLCV columns
        
    Returns:
        Set of available indicator column names
    """
    import pandas as pd
    
    all_cols = set(df.columns)
    
    if exclude_ohlcv:
        ohlcv_cols = {
            "timestamp", "ts_open", "ts_close",
            "open", "high", "low", "close", "volume",
            "symbol", "tf", "timeframe",
        }
        return all_cols - ohlcv_cols
    
    return all_cols


def extract_available_keys_from_feature_frames(
    feature_frames: dict[str, Any],
) -> dict[str, set[str]]:
    """
    Extract available indicator keys from computed feature frames.
    
    Args:
        feature_frames: Dict of role -> feature frame (DataFrame or PreparedFrame)
        
    Returns:
        Dict of role -> set of available indicator keys
    """
    import pandas as pd
    
    result = {}
    
    for role, frame in feature_frames.items():
        if hasattr(frame, 'df'):
            # PreparedFrame or similar wrapper
            df = frame.df
        elif isinstance(frame, pd.DataFrame):
            df = frame
        else:
            # Unknown type, skip
            result[role] = set()
            continue
        
        result[role] = extract_available_keys_from_dataframe(df, exclude_ohlcv=True)
    
    return result

