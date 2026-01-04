"""
Math Parity Audit: Compare snapshot artifacts against fresh pandas_ta computation.

This module validates that the indicator computations in the backtest engine
match pandas_ta exactly, ensuring no implementation drift or bugs.
"""

import pandas as pd
from pathlib import Path
from typing import Any
from dataclasses import dataclass
import numpy as np

from src.backtest.snapshot_artifacts import load_snapshot_artifacts
from src.backtest.indicator_vendor import compute_indicator
from src.backtest.indicator_registry import get_registry


@dataclass
class ColumnAuditResult:
    """Result of auditing a single indicator column."""
    column: str
    passed: bool
    max_abs_diff: float
    mean_abs_diff: float
    nan_mask_identical: bool
    snapshot_values: int
    pandas_ta_values: int
    error_message: str | None = None


@dataclass
class MathParityAuditResult:
    """Result of the complete math parity audit."""
    success: bool
    error_message: str | None = None
    data: dict[str, Any] | None = None


def audit_math_parity_from_snapshots(run_dir: Path) -> MathParityAuditResult:
    """
    Audit math parity by comparing snapshot artifacts against fresh pandas_ta computation.
    
    MANIFEST-DRIVEN: Compares only the columns listed in outputs_written from the manifest.
    No hardcoded indicator output counts - uses manifest as source of truth.

    Args:
        run_dir: Directory containing snapshots/ subdirectory

    Returns:
        MathParityAuditResult with detailed audit results
    """
    try:
        # Load snapshot artifacts
        artifacts = load_snapshot_artifacts(run_dir)
        if not artifacts:
            return MathParityAuditResult(
                success=False,
                error_message=f"No snapshot artifacts found in {run_dir}/snapshots",
            )

        manifest = artifacts["manifest"]
        frames = artifacts["frames"]
        registry = get_registry()

        all_results = []
        total_columns = 0
        passed_columns = 0

        # Process each frame by ROLE (exec/htf/mtf), not TF
        for role, frame_info in manifest["frames"].items():
            if role not in frames:
                continue

            df_snapshot = frames[role]
            feature_specs = frame_info.get("feature_specs_resolved", [])
            
            # Get outputs_written from manifest (manifest-driven comparison)
            # FAIL LOUD if not present - no legacy manifest support
            outputs_written = frame_info.get("outputs_written")
            if not outputs_written:
                raise ValueError(
                    f"LEGACY_MANIFEST_UNSUPPORTED: Frame '{role}' missing 'outputs_written' in manifest. "
                    "Legacy manifests with only 'feature_columns' are not supported. "
                    "Re-run the backtest to generate a current-format manifest."
                )

            # For each feature spec, recompute and compare ONLY outputs_written
            for spec in feature_specs:
                indicator_type = spec["indicator_type"]
                output_key = spec["output_key"]
                params = spec["params"]

                # Get columns to compare from manifest (manifest-driven)
                columns_to_compare = outputs_written.get(output_key, [])
                if not columns_to_compare:
                    continue

                # Recompute using pandas_ta
                try:
                    # Get indicator requirements from registry
                    ind_info = registry.get_indicator_info(indicator_type)
                    required_inputs = ind_info.input_series
                    
                    # Build kwargs based on what the indicator actually needs
                    compute_kwargs = dict(params)
                    
                    if "high" in required_inputs:
                        compute_kwargs["high"] = df_snapshot["high"]
                    if "low" in required_inputs:
                        compute_kwargs["low"] = df_snapshot["low"]
                    if "close" in required_inputs:
                        compute_kwargs["close"] = df_snapshot["close"]
                    # No silent fallback - if close not required and not in kwargs, don't add it
                    if "open" in required_inputs:
                        compute_kwargs["open_"] = df_snapshot["open"]
                    if "volume" in required_inputs:
                        compute_kwargs["volume"] = df_snapshot["volume"]
                    
                    recomputed = compute_indicator(indicator_type, **compute_kwargs)

                    # Handle the result format
                    if isinstance(recomputed, dict):
                        # Multi-output: dict of series
                        for col_name in columns_to_compare:
                            # Extract suffix from canonical column name
                            if col_name.startswith(f"{output_key}_"):
                                suffix = col_name[len(output_key) + 1:]
                            else:
                                suffix = col_name
                            
                            if suffix in recomputed:
                                series = recomputed[suffix]
                                audit_result = _audit_column(col_name, series, df_snapshot)
                            else:
                                audit_result = ColumnAuditResult(
                                    column=col_name,
                                    passed=False,
                                    max_abs_diff=float('inf'),
                                    mean_abs_diff=float('inf'),
                                    nan_mask_identical=False,
                                    snapshot_values=0,
                                    pandas_ta_values=0,
                                    error_message=f"Recomputed output missing suffix '{suffix}'"
                                )
                            
                            all_results.append(audit_result)
                            total_columns += 1
                            if audit_result.passed:
                                passed_columns += 1
                    else:
                        # Single-output: compare against the output_key column
                        for col_name in columns_to_compare:
                            audit_result = _audit_column(col_name, recomputed, df_snapshot)
                            all_results.append(audit_result)
                            total_columns += 1
                            if audit_result.passed:
                                passed_columns += 1

                except Exception as e:
                    # Failed to recompute this indicator
                    for col_name in columns_to_compare:
                        audit_result = ColumnAuditResult(
                            column=col_name,
                            passed=False,
                            max_abs_diff=float('inf'),
                            mean_abs_diff=float('inf'),
                            nan_mask_identical=False,
                            snapshot_values=0,
                            pandas_ta_values=0,
                            error_message=f"Failed to recompute: {str(e)}"
                        )
                        all_results.append(audit_result)
                        total_columns += 1

        # Compute summary statistics
        if all_results:
            max_diffs = [r.max_abs_diff for r in all_results if r.max_abs_diff != float('inf')]
            mean_diffs = [r.mean_abs_diff for r in all_results if r.mean_abs_diff != float('inf')]

            summary = {
                "total_columns": total_columns,
                "passed_columns": passed_columns,
                "failed_columns": total_columns - passed_columns,
                "max_abs_diff": max(max_diffs) if max_diffs else float('inf'),
                "mean_abs_diff": np.mean(mean_diffs) if mean_diffs else float('inf'),
                "overall_passed": passed_columns == total_columns,
            }
        else:
            summary = {
                "total_columns": 0,
                "passed_columns": 0,
                "failed_columns": 0,
                "max_abs_diff": 0.0,
                "mean_abs_diff": 0.0,
                "overall_passed": True,
            }

        return MathParityAuditResult(
            success=summary["overall_passed"],
            data={
                "summary": summary,
                "column_results": [r.__dict__ for r in all_results],
                "manifest": manifest,
            }
        )

    except Exception as e:
        import traceback
        return MathParityAuditResult(
            success=False,
            error_message=f"Audit failed: {str(e)}",
            data={"traceback": traceback.format_exc()}
        )


def _audit_column(
    column_name: str,
    pandas_ta_series: pd.Series,
    snapshot_df: pd.DataFrame
) -> ColumnAuditResult:
    """
    Audit a single indicator column by comparing pandas_ta result against snapshot.

    Args:
        column_name: Canonical column name to compare
        pandas_ta_series: Freshly computed series from pandas_ta
        snapshot_df: DataFrame from snapshot artifacts

    Returns:
        ColumnAuditResult with comparison statistics
    """
    if column_name not in snapshot_df.columns:
        return ColumnAuditResult(
            column=column_name,
            passed=False,
            max_abs_diff=float('inf'),
            mean_abs_diff=float('inf'),
            nan_mask_identical=False,
            snapshot_values=0,
            pandas_ta_values=0,
            error_message=f"Column '{column_name}' not found in snapshot"
        )

    snapshot_series = snapshot_df[column_name]

    # Align the series (they should have the same index)
    aligned_snapshot, aligned_pandas_ta = snapshot_series.align(pandas_ta_series)

    # Check NaN mask identical
    nan_mask_identical = aligned_snapshot.isna().equals(aligned_pandas_ta.isna())

    # Compute differences only on non-NaN values
    valid_mask = aligned_snapshot.notna() & aligned_pandas_ta.notna()
    if valid_mask.any():
        diffs = (aligned_snapshot - aligned_pandas_ta).abs()
        max_abs_diff = diffs[valid_mask].max()
        mean_abs_diff = diffs[valid_mask].mean()
        snapshot_values = valid_mask.sum()
        pandas_ta_values = valid_mask.sum()

        # Check if within tolerance (1e-8)
        passed = max_abs_diff <= 1e-8 and nan_mask_identical
    else:
        max_abs_diff = 0.0
        mean_abs_diff = 0.0
        snapshot_values = 0
        pandas_ta_values = 0
        passed = nan_mask_identical  # If no valid values, just check NaN pattern

    return ColumnAuditResult(
        column=column_name,
        passed=passed,
        max_abs_diff=max_abs_diff,
        mean_abs_diff=mean_abs_diff,
        nan_mask_identical=nan_mask_identical,
        snapshot_values=snapshot_values,
        pandas_ta_values=pandas_ta_values,
    )
