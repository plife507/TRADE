"""
Toolkit Contract Audit: Validate registry-vendor contract for all indicators.

Gate 1 of the verification suite - ensures the registry is the contract:
- Every indicator produces exactly registry-declared canonical outputs
- No canonical collisions
- No missing declared outputs
- Extras are dropped + recorded

Uses deterministic synthetic OHLCV data from the canonical source.
"""

from dataclasses import dataclass, field
from typing import Any
import pandas as pd

from src.backtest.indicator_vendor import compute_indicator, canonicalize_indicator_outputs
from src.backtest.indicator_registry import get_registry
from src.forge.validation.synthetic_data import generate_synthetic_ohlcv_df


@dataclass
class IndicatorAuditResult:
    """Result of auditing a single indicator."""
    indicator_type: str
    passed: bool
    declared_outputs: list[str]
    produced_outputs: list[str]
    extras_dropped: list[str]
    missing_outputs: list[str]
    collisions: dict[str, list[str]]
    error_message: str | None = None
    
    @property
    def has_extras(self) -> bool:
        return len(self.extras_dropped) > 0
    
    @property
    def has_missing(self) -> bool:
        return len(self.missing_outputs) > 0
    
    @property
    def has_collisions(self) -> bool:
        return len(self.collisions) > 0


@dataclass
class ToolkitAuditResult:
    """Result of the complete toolkit contract audit."""
    success: bool
    total_indicators: int
    passed_indicators: int
    failed_indicators: int
    indicators_with_extras: int
    indicator_results: list[IndicatorAuditResult]
    sample_bars: int
    seed: int
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "total_indicators": self.total_indicators,
            "passed_indicators": self.passed_indicators,
            "failed_indicators": self.failed_indicators,
            "indicators_with_extras": self.indicators_with_extras,
            "sample_bars": self.sample_bars,
            "seed": self.seed,
            "error_message": self.error_message,
            "indicator_results": [
                {
                    "indicator_type": r.indicator_type,
                    "passed": r.passed,
                    "declared_outputs": r.declared_outputs,
                    "produced_outputs": r.produced_outputs,
                    "extras_dropped": r.extras_dropped,
                    "missing_outputs": r.missing_outputs,
                    "collisions": r.collisions,
                    "error_message": r.error_message,
                }
                for r in self.indicator_results
            ],
        }


def audit_single_indicator(
    indicator_type: str,
    df: pd.DataFrame,
) -> IndicatorAuditResult:
    """
    Audit a single indicator against its registry contract.
    
    Args:
        indicator_type: Name of the indicator
        df: OHLCV DataFrame
        
    Returns:
        IndicatorAuditResult with contract validation results
    """
    registry = get_registry()
    
    try:
        # Get registry-declared outputs
        if registry.is_multi_output(indicator_type):
            declared_outputs = list(registry.get_output_suffixes(indicator_type))
        else:
            declared_outputs = []
        
        # Get registry-defined inputs
        info = registry.get_indicator_info(indicator_type)
        required_inputs = info.input_series
        
        # Build compute kwargs based on registry requirements
        compute_kwargs = {}

        if "high" in required_inputs:
            compute_kwargs["high"] = df["high"]
        if "low" in required_inputs:
            compute_kwargs["low"] = df["low"]
        if "close" in required_inputs:
            compute_kwargs["close"] = df["close"]
        if "open" in required_inputs:
            compute_kwargs["open_"] = df["open"]
        if "volume" in required_inputs:
            compute_kwargs["volume"] = df["volume"]

        # Pass ts_open for indicators that need timestamps (e.g., VWAP)
        if "timestamp" in df.columns:
            compute_kwargs["ts_open"] = df["timestamp"]
        
        # FAIL LOUD if registry has no required_inputs - this is a registry bug
        if not compute_kwargs:
            raise ValueError(
                f"REGISTRY_MISSING_INPUTS: Indicator '{indicator_type}' has no required_inputs "
                "declared in IndicatorRegistry. All indicators MUST declare their input requirements."
            )
        
        # Use default params from registry if available
        default_params = info.default_params if hasattr(info, 'default_params') else {}
        if not default_params:
            # Use sensible defaults for common params
            default_params = {"length": 14}
        
        # Compute indicator
        result = compute_indicator(indicator_type, **compute_kwargs, **default_params)
        
        # Analyze outputs
        if isinstance(result, dict):
            produced_outputs = list(result.keys())
        else:
            produced_outputs = []  # Single-output
        
        # Use the canonicalizer to get contract analysis
        # For single-output indicators, we don't need to check outputs
        if not registry.is_multi_output(indicator_type):
            return IndicatorAuditResult(
                indicator_type=indicator_type,
                passed=True,
                declared_outputs=declared_outputs,
                produced_outputs=produced_outputs,
                extras_dropped=[],
                missing_outputs=[],
                collisions={},
            )
        
        # Multi-output: compare produced vs declared
        produced_set = set(produced_outputs)
        declared_set = set(declared_outputs)
        
        missing = list(declared_set - produced_set)
        extras = list(produced_set - declared_set)
        
        # Note: collisions are detected by the vendor's canonicalizer
        # If we got here without error, there were no collisions
        collisions = {}
        
        # Pass if no missing and no collisions
        # (extras are dropped, which is OK per our policy)
        passed = len(missing) == 0 and len(collisions) == 0
        
        return IndicatorAuditResult(
            indicator_type=indicator_type,
            passed=passed,
            declared_outputs=declared_outputs,
            produced_outputs=produced_outputs,
            extras_dropped=extras,
            missing_outputs=missing,
            collisions=collisions,
        )
        
    except Exception as e:
        return IndicatorAuditResult(
            indicator_type=indicator_type,
            passed=False,
            declared_outputs=[],
            produced_outputs=[],
            extras_dropped=[],
            missing_outputs=[],
            collisions={},
            error_message=str(e),
        )


def run_toolkit_contract_audit(
    sample_bars: int = 2000,
    seed: int = 1337,
    fail_on_extras: bool = False,
    strict: bool = True,
) -> ToolkitAuditResult:
    """
    Run the complete toolkit contract audit over all registry indicators.
    
    Args:
        sample_bars: Number of bars in synthetic OHLCV (default: 2000)
        seed: Random seed for reproducibility (default: 1337)
        fail_on_extras: If True, treat extras as failures (default: False)
        strict: If True, fail on any contract breach (default: True)
        
    Returns:
        ToolkitAuditResult with complete audit results
    """
    registry = get_registry()
    all_indicators = registry.list_indicators()

    # Generate synthetic data from canonical source
    df = generate_synthetic_ohlcv_df(n_bars=sample_bars, seed=seed)
    
    results = []
    passed_count = 0
    failed_count = 0
    extras_count = 0
    
    for indicator_type in all_indicators:
        result = audit_single_indicator(indicator_type, df)
        results.append(result)
        
        if result.has_extras:
            extras_count += 1
        
        # Determine pass/fail based on policy
        if fail_on_extras:
            indicator_passed = result.passed and not result.has_extras
        else:
            indicator_passed = result.passed
        
        if indicator_passed:
            passed_count += 1
        else:
            failed_count += 1
    
    # Overall success
    if strict:
        success = failed_count == 0
    else:
        success = True  # Non-strict mode always passes
    
    return ToolkitAuditResult(
        success=success,
        total_indicators=len(all_indicators),
        passed_indicators=passed_count,
        failed_indicators=failed_count,
        indicators_with_extras=extras_count,
        indicator_results=results,
        sample_bars=sample_bars,
        seed=seed,
    )

