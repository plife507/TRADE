"""
In-Memory Math Parity Audit: Compare FeedStore indicator values against fresh pandas_ta computation.

This module validates that the indicator computations in the backtest pipeline
match pandas_ta exactly WITHOUT relying on snapshot artifacts.

Requirements:
- No snapshot artifacts required
- No Parquet emission
- In-memory comparison only
- Outputs small CSV diff report if mismatches found

CLI: python trade_cli.py backtest math-parity --idea-card <ID> --start <date> --end <date>
"""

import pandas as pd
from pathlib import Path
from typing import Any
from dataclasses import dataclass, field
from datetime import datetime
import numpy as np
import json

from ..indicator_vendor import compute_indicator
from ..indicator_registry import get_registry


@dataclass
class ColumnParityResult:
    """Result of comparing a single indicator column."""
    column: str
    tf_role: str  # "exec", "htf", "mtf"
    passed: bool
    max_abs_diff: float
    mean_abs_diff: float
    nan_mask_identical: bool
    feedstore_values: int
    recomputed_values: int
    first_mismatches: list[dict[str, Any]] = field(default_factory=list)
    error_message: str | None = None


@dataclass
class InMemoryParityResult:
    """Result of the complete in-memory math parity audit."""
    success: bool
    error_message: str | None = None
    summary: dict[str, Any] | None = None
    column_results: list[ColumnParityResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "success": self.success,
            "error_message": self.error_message,
            "summary": self.summary,
            "column_results": [
                {
                    "column": r.column,
                    "tf_role": r.tf_role,
                    "passed": r.passed,
                    "max_abs_diff": r.max_abs_diff,
                    "mean_abs_diff": r.mean_abs_diff,
                    "nan_mask_identical": r.nan_mask_identical,
                    "feedstore_values": r.feedstore_values,
                    "recomputed_values": r.recomputed_values,
                    "error_message": r.error_message,
                }
                for r in self.column_results
            ],
        }
    
    def write_diff_csv(self, output_path: Path, max_mismatches: int = 20) -> None:
        """Write CSV diff report with summary + first N mismatches."""
        import csv
        
        with open(output_path, "w", newline="") as f:
            writer = csv.writer(f)
            
            # Summary header
            writer.writerow(["# In-Memory Parity Audit Summary"])
            writer.writerow(["success", self.success])
            writer.writerow(["total_columns", self.summary.get("total_columns", 0) if self.summary else 0])
            writer.writerow(["passed_columns", self.summary.get("passed_columns", 0) if self.summary else 0])
            writer.writerow(["failed_columns", self.summary.get("failed_columns", 0) if self.summary else 0])
            writer.writerow([])
            
            # Mismatch details
            writer.writerow(["# First Mismatches (max {})".format(max_mismatches)])
            writer.writerow(["column", "tf_role", "index", "feedstore_value", "recomputed_value", "abs_diff"])
            
            mismatch_count = 0
            for result in self.column_results:
                if not result.passed and result.first_mismatches:
                    for mismatch in result.first_mismatches[:max_mismatches - mismatch_count]:
                        writer.writerow([
                            result.column,
                            result.tf_role,
                            mismatch.get("index", ""),
                            mismatch.get("feedstore", ""),
                            mismatch.get("recomputed", ""),
                            mismatch.get("abs_diff", ""),
                        ])
                        mismatch_count += 1
                        if mismatch_count >= max_mismatches:
                            break
                if mismatch_count >= max_mismatches:
                    break


def audit_in_memory_parity_from_feeds(
    exec_df: pd.DataFrame,
    htf_df: pd.DataFrame | None,
    mtf_df: pd.DataFrame | None,
    feature_specs: list[dict[str, Any]],
    tolerance: float = 1e-8,
) -> InMemoryParityResult:
    """
    Audit math parity by comparing in-memory FeedStore data against fresh pandas_ta computation.
    
    This is the core parity check — compares the FeatureFrameBuilder output (already computed)
    against a fresh recomputation of the same indicators using pandas_ta.
    
    Args:
        exec_df: Exec TF DataFrame with OHLCV + computed indicators
        htf_df: Optional HTF DataFrame with OHLCV + computed indicators
        mtf_df: Optional MTF DataFrame with OHLCV + computed indicators
        feature_specs: List of feature spec dicts (from Play or manifest)
        tolerance: Max allowed absolute difference (default: 1e-8)
        
    Returns:
        InMemoryParityResult with detailed comparison results
    """
    try:
        registry = get_registry()
        all_results: list[ColumnParityResult] = []
        
        # Process each TF role
        tf_frames = [
            ("exec", exec_df),
            ("htf", htf_df),
            ("mtf", mtf_df),
        ]
        
        for tf_role, df in tf_frames:
            if df is None:
                continue
            
            # For each feature spec, recompute and compare
            for spec in feature_specs:
                # Handle different spec formats (Play vs manifest)
                if isinstance(spec, dict):
                    indicator_type = spec.get("indicator_type") or spec.get("type")
                    output_key = spec.get("output_key") or spec.get("key")
                    params = spec.get("params", {})
                    input_source = spec.get("input_source")
                    tf_roles_for_spec = spec.get("tf_roles", ["exec"])
                else:
                    continue
                
                # Skip if this spec doesn't apply to this TF role
                if tf_role not in tf_roles_for_spec and tf_role != "exec":
                    continue
                
                if not indicator_type or not output_key:
                    continue
                
                # Find columns to compare
                # Look for columns starting with output_key (e.g., "ema_fast", "macd_macd", "macd_signal")
                columns_to_compare = [
                    col for col in df.columns
                    if col == output_key or col.startswith(f"{output_key}_")
                ]
                
                if not columns_to_compare:
                    continue
                
                # Recompute using pandas_ta
                try:
                    ind_info = registry.get_indicator_info(indicator_type)
                    required_inputs = ind_info.input_series
                    
                    # Determine the primary input series based on input_source
                    # FAIL LOUD if not declared - mirrors indicators.py
                    if input_source is None:
                        raise ValueError(
                            f"MISSING_INPUT_SOURCE: Indicator '{output_key}' has no input_source in spec. "
                            "All FeatureSpecs MUST declare input_source explicitly."
                        )
                    
                    # Handle enum (use .value) or string
                    if hasattr(input_source, 'value'):
                        source_key = input_source.value  # Enum case
                    else:
                        source_key = str(input_source).lower()
                    
                    
                    # Get input series (compute hlc3/ohlc4 if needed)
                    if source_key == "hlc3":
                        primary_input = (df["high"] + df["low"] + df["close"]) / 3
                    elif source_key == "ohlc4":
                        primary_input = (df["open"] + df["high"] + df["low"] + df["close"]) / 4
                    elif source_key in df.columns:
                        primary_input = df[source_key]
                    else:
                        primary_input = df["close"]
                    
                    # Build kwargs based on what the indicator actually needs
                    compute_kwargs = dict(params)
                    
                    if "high" in required_inputs:
                        compute_kwargs["high"] = df["high"]
                    if "low" in required_inputs:
                        compute_kwargs["low"] = df["low"]
                    # Use primary_input as the "close" parameter for single-input indicators
                    if "close" in required_inputs:
                        compute_kwargs["close"] = primary_input
                    elif "close" not in compute_kwargs:
                        compute_kwargs["close"] = primary_input
                    if "open" in required_inputs:
                        compute_kwargs["open_"] = df["open"]
                    if "volume" in required_inputs:
                        compute_kwargs["volume"] = df["volume"]
                    
                    recomputed = compute_indicator(indicator_type, **compute_kwargs)
                    
                    
                    # Handle the result format
                    if isinstance(recomputed, dict):
                        # Multi-output: dict of series
                        for col_name in columns_to_compare:
                            # Extract suffix from canonical column name
                            if col_name.startswith(f"{output_key}_"):
                                suffix = col_name[len(output_key) + 1:]
                            else:
                                suffix = ""
                            
                            if suffix in recomputed:
                                result = _compare_column(
                                    col_name, tf_role, df[col_name], recomputed[suffix], tolerance
                                )
                            elif col_name == output_key and "" in recomputed:
                                result = _compare_column(
                                    col_name, tf_role, df[col_name], recomputed[""], tolerance
                                )
                            else:
                                result = ColumnParityResult(
                                    column=col_name,
                                    tf_role=tf_role,
                                    passed=False,
                                    max_abs_diff=float('inf'),
                                    mean_abs_diff=float('inf'),
                                    nan_mask_identical=False,
                                    feedstore_values=0,
                                    recomputed_values=0,
                                    error_message=f"Recomputed output missing suffix '{suffix}'"
                                )
                            
                            all_results.append(result)
                    else:
                        # Single-output: compare against the output_key column
                        for col_name in columns_to_compare:
                            result = _compare_column(
                                col_name, tf_role, df[col_name], recomputed, tolerance
                            )
                            all_results.append(result)
                
                except Exception as e:
                    # Failed to recompute this indicator
                    for col_name in columns_to_compare:
                        result = ColumnParityResult(
                            column=col_name,
                            tf_role=tf_role,
                            passed=False,
                            max_abs_diff=float('inf'),
                            mean_abs_diff=float('inf'),
                            nan_mask_identical=False,
                            feedstore_values=0,
                            recomputed_values=0,
                            error_message=f"Failed to recompute: {str(e)}"
                        )
                        all_results.append(result)
        
        # Compute summary statistics
        total_columns = len(all_results)
        passed_columns = sum(1 for r in all_results if r.passed)
        failed_columns = total_columns - passed_columns
        
        max_diffs = [r.max_abs_diff for r in all_results if r.max_abs_diff != float('inf')]
        mean_diffs = [r.mean_abs_diff for r in all_results if r.mean_abs_diff != float('inf')]
        
        summary = {
            "total_columns": total_columns,
            "passed_columns": passed_columns,
            "failed_columns": failed_columns,
            "max_abs_diff": max(max_diffs) if max_diffs else 0.0,
            "mean_abs_diff": float(np.mean(mean_diffs)) if mean_diffs else 0.0,
            "tolerance": tolerance,
        }
        
        return InMemoryParityResult(
            success=(failed_columns == 0),
            summary=summary,
            column_results=all_results,
        )
    
    except Exception as e:
        import traceback
        return InMemoryParityResult(
            success=False,
            error_message=f"In-memory parity audit failed: {str(e)}",
            summary={"traceback": traceback.format_exc()},
        )


def _compare_column(
    column_name: str,
    tf_role: str,
    feedstore_series: pd.Series,
    recomputed_series: pd.Series,
    tolerance: float,
) -> ColumnParityResult:
    """
    Compare a single indicator column between FeedStore and fresh computation.
    
    Args:
        column_name: Column name for reporting
        tf_role: TF role for reporting
        feedstore_series: Series from FeedStore/DataFrame
        recomputed_series: Freshly computed series
        tolerance: Max allowed absolute difference
        
    Returns:
        ColumnParityResult with comparison statistics
    """
    # Align the series (they should have the same index)
    aligned_feedstore, aligned_recomputed = feedstore_series.align(recomputed_series)
    
    # Check NaN mask identical
    nan_mask_feedstore = aligned_feedstore.isna()
    nan_mask_recomputed = aligned_recomputed.isna()
    nan_mask_identical = nan_mask_feedstore.equals(nan_mask_recomputed)
    
    # Compute differences only on non-NaN values
    valid_mask = aligned_feedstore.notna() & aligned_recomputed.notna()
    
    if valid_mask.any():
        diffs = (aligned_feedstore - aligned_recomputed).abs()
        max_abs_diff = float(diffs[valid_mask].max())
        mean_abs_diff = float(diffs[valid_mask].mean())
        feedstore_values = int(valid_mask.sum())
        recomputed_values = int(valid_mask.sum())
        
        # Collect first few mismatches
        first_mismatches = []
        mismatch_mask = valid_mask & (diffs > tolerance)
        mismatch_indices = mismatch_mask[mismatch_mask].index[:10]
        for idx in mismatch_indices:
            first_mismatches.append({
                "index": str(idx),
                "feedstore": float(aligned_feedstore.loc[idx]),
                "recomputed": float(aligned_recomputed.loc[idx]),
                "abs_diff": float(diffs.loc[idx]),
            })
        
        # Check if within tolerance
        passed = max_abs_diff <= tolerance and nan_mask_identical
    else:
        max_abs_diff = 0.0
        mean_abs_diff = 0.0
        feedstore_values = 0
        recomputed_values = 0
        first_mismatches = []
        passed = nan_mask_identical  # If no valid values, just check NaN pattern
    
    return ColumnParityResult(
        column=column_name,
        tf_role=tf_role,
        passed=passed,
        max_abs_diff=max_abs_diff,
        mean_abs_diff=mean_abs_diff,
        nan_mask_identical=nan_mask_identical,
        feedstore_values=feedstore_values,
        recomputed_values=recomputed_values,
        first_mismatches=first_mismatches,
    )


def run_in_memory_parity_for_idea_card(
    idea_card_path: str,
    start_date: str,
    end_date: str,
    output_dir: Path | None = None,
) -> InMemoryParityResult:
    """
    Run in-memory parity audit for an Play without producing backtest artifacts.
    
    This:
    1. Loads the Play
    2. Fetches historical data
    3. Builds FeatureFrames using FeatureFrameBuilder
    4. Compares computed indicators against fresh pandas_ta computation
    
    Args:
        idea_card_path: Path to Play YAML (or idea card ID for lookup)
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        output_dir: Optional output directory for diff CSV
        
    Returns:
        InMemoryParityResult with detailed comparison
    """
    from ..play import load_idea_card
    from ..runner import RunnerConfig, run_backtest_with_gates
    from datetime import datetime as dt
    
    try:
        # Use RunnerConfig to load and prepare the Play
        config = RunnerConfig(
            idea_card_id=idea_card_path,
            window_start=dt.fromisoformat(start_date),
            window_end=dt.fromisoformat(end_date),
        )
        
        # Load the Play
        idea_card = config.load_idea_card()
        symbol = idea_card.symbol_universe[0]
        
        # Get the feature spec sets using the correct API
        exec_spec_set = idea_card.get_feature_spec_set("exec", symbol)
        htf_spec_set = idea_card.get_feature_spec_set("htf", symbol)
        mtf_spec_set = idea_card.get_feature_spec_set("mtf", symbol)
        
        # Collect all feature specs across TFs
        all_feature_specs = []
        
        if exec_spec_set:
            for spec in exec_spec_set.specs:
                all_feature_specs.append({
                    "indicator_type": spec.indicator_type,
                    "output_key": spec.output_key,
                    "params": spec.params,
                    "input_source": spec.input_source,
                    "tf_roles": ["exec"],
                })
        
        if htf_spec_set:
            for spec in htf_spec_set.specs:
                all_feature_specs.append({
                    "indicator_type": spec.indicator_type,
                    "output_key": spec.output_key,
                    "params": spec.params,
                    "input_source": spec.input_source,
                    "tf_roles": ["htf"],
                })
        
        if mtf_spec_set:
            for spec in mtf_spec_set.specs:
                all_feature_specs.append({
                    "indicator_type": spec.indicator_type,
                    "output_key": spec.output_key,
                    "params": spec.params,
                    "input_source": spec.input_source,
                    "tf_roles": ["mtf"],
                })
        
        # Build the backtest engine using the Play-native engine factory
        # P1.2 Refactor: Use create_engine_from_idea_card() instead of legacy adapter
        from ..engine import create_engine_from_idea_card
        from ..execution_validation import compute_warmup_requirements
        
        # Compute warmup requirements
        warmup_req = compute_warmup_requirements(idea_card)
        
        # Create engine directly from Play
        engine = create_engine_from_idea_card(
            idea_card=idea_card,
            window_start=config.window_start,
            window_end=config.window_end,
            warmup_by_role=warmup_req.warmup_by_role,
            delay_by_role=warmup_req.delay_by_role,
        )
        
        # Prepare multi-TF frames (triggers FeatureFrameBuilder)
        engine.prepare_multi_tf_frames()
        
        # Extract DataFrames from engine's internal state
        exec_df = engine._ltf_df if hasattr(engine, '_ltf_df') and engine._ltf_df is not None else None
        htf_df = engine._htf_df if hasattr(engine, '_htf_df') and engine._htf_df is not None else None
        mtf_df = engine._mtf_df if hasattr(engine, '_mtf_df') and engine._mtf_df is not None else None
        
        # Run parity check
        result = audit_in_memory_parity_from_feeds(
            exec_df=exec_df,
            htf_df=htf_df,
            mtf_df=mtf_df,
            feature_specs=all_feature_specs,
        )
        
        # Write diff CSV if requested and there are failures
        if output_dir and not result.success:
            output_dir.mkdir(parents=True, exist_ok=True)
            diff_path = output_dir / "parity_diff.csv"
            result.write_diff_csv(diff_path)
        
        return result
    
    except Exception as e:
        import traceback
        return InMemoryParityResult(
            success=False,
            error_message=f"Failed to run in-memory parity: {str(e)}",
            summary={"traceback": traceback.format_exc()},
        )

