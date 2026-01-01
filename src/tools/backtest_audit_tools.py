"""
Backtest audit and verification tools.

This module contains all audit tools for backtest validation:
- Toolkit contract audit (indicator registry consistency)
- In-memory parity audit (indicator computation validation)
- Math parity audit (combined contract + parity)
- Snapshot plumbing audit (data flow validation)
- Rollup parity audit (1m price feed validation)
- Artifact parity verification (CSV ↔ Parquet)

All tools use synthetic or in-memory data for validation.
No production data is modified.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional
import traceback

from .shared import ToolResult
from ..utils.logger import get_logger


logger = get_logger()


# =============================================================================
# Math Parity from Snapshots (artifact-based audit)
# =============================================================================

def backtest_audit_math_from_snapshots_tool(run_dir: Path) -> ToolResult:
    """
    Audit math parity by comparing snapshot artifacts against fresh pandas_ta computation.

    Args:
        run_dir: Directory containing snapshots/ subdirectory with artifacts

    Returns:
        ToolResult with audit results including per-column diff statistics
    """
    try:
        from ..backtest.audits.audit_math_parity import audit_math_parity_from_snapshots

        result = audit_math_parity_from_snapshots(run_dir)

        if result.success:
            return ToolResult(
                success=True,
                message="Math parity audit completed successfully",
                data=result.data,
            )
        else:
            return ToolResult(
                success=False,
                error=result.error_message or "Math parity audit failed",
                data=result.data,
            )

    except Exception as e:
        logger.error(f"Math parity audit failed: {e}\n{traceback.format_exc()}")
        return ToolResult(
            success=False,
            error=f"Math parity audit error: {e}",
        )


# =============================================================================
# Toolkit Contract Audit (indicator registry consistency check)
# =============================================================================

def backtest_audit_toolkit_tool(
    sample_bars: int = 2000,
    seed: int = 1337,
    fail_on_extras: bool = False,
    strict: bool = True,
) -> ToolResult:
    """
    Run the toolkit contract audit over all registry indicators.

    Gate 1 of the verification suite - ensures the registry is the contract:
    - Every indicator produces exactly registry-declared canonical outputs
    - No canonical collisions
    - No missing declared outputs
    - Extras are dropped + recorded

    Uses deterministic synthetic OHLCV data for reproducibility.

    Args:
        sample_bars: Number of bars in synthetic OHLCV (default: 2000)
        seed: Random seed for reproducibility (default: 1337)
        fail_on_extras: If True, treat extras as failures (default: False)
        strict: If True, fail on any contract breach (default: True)

    Returns:
        ToolResult with complete audit results
    """
    try:
        from ..backtest.audits.toolkit_contract_audit import run_toolkit_contract_audit

        result = run_toolkit_contract_audit(
            sample_bars=sample_bars,
            seed=seed,
            fail_on_extras=fail_on_extras,
            strict=strict,
        )

        if result.success:
            return ToolResult(
                success=True,
                message=(
                    f"Toolkit contract audit PASSED: {result.passed_indicators}/{result.total_indicators} "
                    f"indicators OK ({result.indicators_with_extras} have extras dropped)"
                ),
                data=result.to_dict(),
            )
        else:
            # Collect failure details
            failed = [r for r in result.indicator_results if not r.passed]
            failure_summary = [
                {
                    "indicator": r.indicator_type,
                    "missing": r.missing_outputs,
                    "collisions": r.collisions,
                    "error": r.error_message,
                }
                for r in failed
            ]
            return ToolResult(
                success=False,
                error=(
                    f"Toolkit contract audit FAILED: {result.failed_indicators} indicator(s) "
                    f"with contract breaches"
                ),
                data=result.to_dict(),
            )

    except Exception as e:
        logger.error(f"Toolkit contract audit failed: {e}\n{traceback.format_exc()}")
        return ToolResult(
            success=False,
            error=f"Toolkit contract audit error: {e}",
        )


# =============================================================================
# In-Memory Parity Audit (indicator computation validation)
# =============================================================================

def backtest_audit_in_memory_parity_tool(
    idea_card: str,
    start_date: str,
    end_date: str,
    output_dir: Optional[str] = None,
) -> ToolResult:
    """
    Run in-memory math parity audit for an IdeaCard.

    Compares FeatureFrameBuilder output against fresh pandas_ta computation.
    Does NOT emit snapshot artifacts or Parquet — purely in-memory comparison.

    Args:
        idea_card: Path to IdeaCard YAML
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        output_dir: Optional output directory for diff CSV (written only on failure)

    Returns:
        ToolResult with parity audit results
    """
    try:
        from ..backtest.audits.audit_in_memory_parity import run_in_memory_parity_for_idea_card

        output_path = Path(output_dir) if output_dir else None

        result = run_in_memory_parity_for_idea_card(
            idea_card_path=idea_card,
            start_date=start_date,
            end_date=end_date,
            output_dir=output_path,
        )

        if result.success:
            return ToolResult(
                success=True,
                message=(
                    f"In-memory parity audit PASSED: {result.summary['passed_columns']}/{result.summary['total_columns']} "
                    f"columns OK (max_diff={result.summary['max_abs_diff']:.2e})"
                ),
                data=result.to_dict(),
            )
        else:
            return ToolResult(
                success=False,
                error=(
                    f"In-memory parity audit FAILED: {result.summary['failed_columns']} column(s) "
                    f"exceeded tolerance (max_diff={result.summary['max_abs_diff']:.2e})"
                    if result.summary else result.error_message
                ),
                data=result.to_dict(),
            )

    except Exception as e:
        logger.error(f"In-memory parity audit failed: {e}\n{traceback.format_exc()}")
        return ToolResult(
            success=False,
            error=f"In-memory parity audit error: {e}",
        )


# =============================================================================
# Math Parity Tool (combined: contract audit + in-memory parity)
# =============================================================================

def backtest_math_parity_tool(
    idea_card: str,
    start_date: str,
    end_date: str,
    output_dir: Optional[str] = None,
    contract_sample_bars: int = 2000,
    contract_seed: int = 1337,
) -> ToolResult:
    """
    Run math parity audit: contract audit + in-memory parity.

    Validates indicator math correctness by running:
    1. Toolkit contract audit (registry validation)
    2. In-memory math parity audit (indicator computation validation)

    Args:
        idea_card: Path to IdeaCard YAML for parity audit
        start_date: Start date for parity audit (YYYY-MM-DD)
        end_date: End date for parity audit (YYYY-MM-DD)
        output_dir: Optional output directory for diff reports
        contract_sample_bars: Synthetic bars for contract audit
        contract_seed: Random seed for contract audit

    Returns:
        ToolResult with combined audit results
    """
    from ..backtest.audits.toolkit_contract_audit import run_toolkit_contract_audit
    from ..backtest.audits.audit_in_memory_parity import run_in_memory_parity_for_idea_card

    results = {
        "contract_audit": None,
        "parity_audit": None,
    }

    try:
        # Step 1: Toolkit contract audit
        contract_result = run_toolkit_contract_audit(
            sample_bars=contract_sample_bars,
            seed=contract_seed,
            fail_on_extras=False,
            strict=True,
        )
        results["contract_audit"] = {
            "success": contract_result.success,
            "passed": contract_result.passed_indicators,
            "failed": contract_result.failed_indicators,
            "total": contract_result.total_indicators,
        }

        if not contract_result.success:
            return ToolResult(
                success=False,
                error=f"Math parity FAILED at contract audit: {contract_result.failed_indicators} indicator(s) with breaches",
                data=results,
            )

        # Step 2: In-memory parity audit
        output_path = Path(output_dir) if output_dir else None
        parity_result = run_in_memory_parity_for_idea_card(
            idea_card_path=idea_card,
            start_date=start_date,
            end_date=end_date,
            output_dir=output_path,
        )
        results["parity_audit"] = {
            "success": parity_result.success,
            "summary": parity_result.summary,
        }

        if not parity_result.success:
            return ToolResult(
                success=False,
                error=f"Math parity FAILED: {parity_result.summary.get('failed_columns', 0)} column(s) mismatched",
                data=results,
            )

        # Both passed
        return ToolResult(
            success=True,
            message=(
                f"Math parity PASSED: "
                f"contract={contract_result.passed_indicators}/{contract_result.total_indicators}, "
                f"parity={parity_result.summary['passed_columns']}/{parity_result.summary['total_columns']}"
            ),
            data=results,
        )

    except Exception as e:
        logger.error(f"Math parity audit failed: {e}\n{traceback.format_exc()}")
        return ToolResult(
            success=False,
            error=f"Math parity audit error: {e}",
            data=results,
        )


# =============================================================================
# Artifact Parity Verification (CSV ↔ Parquet)
# =============================================================================

def verify_artifact_parity_tool(
    idea_card_id: str = None,
    symbol: str = None,
    run_id: Optional[str] = None,
    base_dir: Optional[str] = None,
    run_dir: Path = None,
) -> ToolResult:
    """
    Verify CSV ↔ Parquet parity for backtest artifacts.

    Phase 3.1 tool: Validates that dual-written CSV and Parquet files
    contain identical data. Used during migration validation.

    Args:
        idea_card_id: IdeaCard ID (optional if run_dir provided)
        symbol: Trading symbol (optional if run_dir provided)
        run_id: Specific run ID (e.g., "run-001") or None for latest
        base_dir: Base backtests directory (default: "backtests")
        run_dir: Direct path to run directory (overrides other args)

    Returns:
        ToolResult with parity verification results
    """
    from ..backtest.artifact_parity_verifier import (
        verify_idea_card_parity,
        RunParityResult,
    )

    try:
        # If run_dir provided directly, use simpler verification
        if run_dir is not None:
            # Direct verification of a run directory
            from ..backtest.artifacts import validate_artifacts

            artifact_validation = validate_artifacts(run_dir)

            if artifact_validation.passed:
                return ToolResult(
                    success=True,
                    message=f"Artifact validation PASSED for {run_dir}",
                    data=artifact_validation.to_dict(),
                )
            else:
                return ToolResult(
                    success=False,
                    error=f"Artifact validation FAILED for {run_dir}",
                    data=artifact_validation.to_dict(),
                )

        # Standard verification via idea_card_id and symbol
        if idea_card_id is None or symbol is None:
            return ToolResult(
                success=False,
                error="Either run_dir or both idea_card_id and symbol are required",
            )

        # Default base dir
        backtests_dir = Path(base_dir) if base_dir else Path("backtests")

        # Run parity verification
        result = verify_idea_card_parity(
            base_dir=backtests_dir,
            idea_card_id=idea_card_id,
            symbol=symbol,
            run_id=run_id,
        )

        if result.passed:
            return ToolResult(
                success=True,
                message=f"CSV ↔ Parquet parity PASSED: {result.artifacts_passed}/{result.artifacts_checked} artifacts",
                data=result.to_dict(),
            )
        else:
            return ToolResult(
                success=False,
                error=f"CSV ↔ Parquet parity FAILED: {result.artifacts_passed}/{result.artifacts_checked} artifacts passed",
                data=result.to_dict(),
            )

    except Exception as e:
        logger.error(f"Artifact parity verification failed: {e}\n{traceback.format_exc()}")
        return ToolResult(
            success=False,
            error=f"Parity verification error: {e}",
        )


# =============================================================================
# Snapshot Plumbing Parity Audit (data flow validation)
# =============================================================================

def backtest_audit_snapshot_plumbing_tool(
    idea_card_id: str,
    start_date: str,
    end_date: str,
    symbol: Optional[str] = None,
    max_samples: int = 2000,
    tolerance: float = 1e-12,
    strict: bool = True,
) -> ToolResult:
    """
    Run Phase 4 snapshot plumbing parity audit.

    Validates RuntimeSnapshotView.get_feature() against direct FeedStore reads.
    This audit proves the plumbing is correct without testing indicator math.

    Args:
        idea_card_id: IdeaCard identifier or path
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        symbol: Override symbol (optional, inferred from IdeaCard)
        max_samples: Max exec bar samples (default: 2000)
        tolerance: Tolerance for float comparison (default: 1e-12)
        strict: Stop at first mismatch (default: True)

    Returns:
        ToolResult with plumbing parity audit results
    """
    from ..backtest.audits.audit_snapshot_plumbing_parity import audit_snapshot_plumbing_parity

    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")

        result = audit_snapshot_plumbing_parity(
            idea_card_id=idea_card_id,
            symbol=symbol,
            start_date=start,
            end_date=end,
            max_samples=max_samples,
            tolerance=tolerance,
            strict=strict,
        )

        if result.success:
            return ToolResult(
                success=True,
                message=(
                    f"Snapshot plumbing parity PASSED: "
                    f"{result.total_samples} samples, {result.total_comparisons} comparisons "
                    f"(runtime: {result.runtime_seconds:.1f}s)"
                ),
                data=result.to_dict(),
            )
        else:
            return ToolResult(
                success=False,
                error=result.error_message or "Plumbing parity audit failed",
                data=result.to_dict(),
            )

    except Exception as e:
        logger.error(f"Snapshot plumbing parity audit failed: {e}\n{traceback.format_exc()}")
        return ToolResult(
            success=False,
            error=f"Plumbing audit error: {e}",
        )


# =============================================================================
# Rollup Parity Audit (1m Price Feed Validation)
# =============================================================================

def backtest_audit_rollup_parity_tool(
    n_intervals: int = 10,
    quotes_per_interval: int = 15,
    seed: int = 1337,
    tolerance: float = 1e-10,
) -> ToolResult:
    """
    Run rollup parity audit for ExecRollupBucket and RuntimeSnapshotView accessors.

    Validates the 1m rollup system that aggregates price data between exec closes:
    - ExecRollupBucket.accumulate() correctly tracks min/max/sum/count
    - ExecRollupBucket.freeze() produces correct px.rollup.* values
    - RuntimeSnapshotView accessors return correct rollup values
    - Rollup values match manual recomputation from 1m quote data

    This is a critical audit for the simulator - rollups are used for:
    - Zone touch detection (Market Structure)
    - Intrabar price movement analysis
    - Stop/limit fill simulation accuracy

    Args:
        n_intervals: Number of exec intervals to test (default: 10)
        quotes_per_interval: Approximate quotes per interval (default: 15)
        seed: Random seed for reproducibility (default: 1337)
        tolerance: Float comparison tolerance (default: 1e-10)

    Returns:
        ToolResult with rollup parity audit results
    """
    try:
        from ..backtest.audits.audit_rollup_parity import run_rollup_parity_audit

        result = run_rollup_parity_audit(
            n_intervals=n_intervals,
            quotes_per_interval=quotes_per_interval,
            seed=seed,
            tolerance=tolerance,
        )

        if result.success:
            return ToolResult(
                success=True,
                message=(
                    f"Rollup parity audit PASSED: "
                    f"{result.passed_intervals}/{result.total_intervals} intervals, "
                    f"{result.total_comparisons} comparisons "
                    f"(bucket={result.bucket_tests_passed}, accessors={result.accessor_tests_passed})"
                ),
                data=result.to_dict(),
            )
        else:
            return ToolResult(
                success=False,
                error=(
                    f"Rollup parity audit FAILED: "
                    f"{result.failed_intervals} interval(s) failed, "
                    f"{result.failed_comparisons} comparison(s) failed"
                    + (f" - {result.error_message}" if result.error_message else "")
                ),
                data=result.to_dict(),
            )

    except Exception as e:
        logger.error(f"Rollup parity audit failed: {e}\n{traceback.format_exc()}")
        return ToolResult(
            success=False,
            error=f"Rollup audit error: {e}",
        )
