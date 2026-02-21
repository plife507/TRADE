"""
Determinism verification for backtest runs.

Phase 3: Hash-based determinism verification.

This module provides:
- Compare two backtest runs for hash equality
- Re-run verification (execute same Play, compare outputs)
- Detailed diff reporting on hash mismatches

USAGE:
    # Compare two existing runs
    result = compare_runs(run_a_path, run_b_path)
    
    # Verify determinism by re-running
    result = verify_determinism_rerun(run_path)
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .artifact_standards import (
    STANDARD_FILES,
    ResultsSummary,
)


@dataclass
class HashComparison:
    """Result of comparing hashes between two runs."""
    field_name: str
    run_a_value: str
    run_b_value: str
    matches: bool
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field_name,
            "run_a": self.run_a_value,
            "run_b": self.run_b_value,
            "matches": self.matches,
        }


@dataclass
class DeterminismResult:
    """Result of determinism verification."""
    passed: bool
    run_a_path: str
    run_b_path: str
    hash_comparisons: list[HashComparison] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # Metadata
    run_a_play_id: str = ""
    run_b_play_id: str = ""
    mode: str = "compare"  # "compare" or "rerun"

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "mode": self.mode,
            "run_a_path": self.run_a_path,
            "run_b_path": self.run_b_path,
            "run_a_play_id": self.run_a_play_id,
            "run_b_play_id": self.run_b_play_id,
            "hash_comparisons": [c.to_dict() for c in self.hash_comparisons],
            "errors": self.errors,
            "warnings": self.warnings,
        }
    
    def print_report(self) -> None:
        """Print human-readable report."""
        status = "[PASSED]" if self.passed else "[FAILED]"
        print(f"\n{'='*60}")
        print(f"  DETERMINISM VERIFICATION: {status}")
        print(f"{'='*60}")
        print(f"  Mode: {self.mode}")
        print(f"  Run A: {self.run_a_path}")
        print(f"  Run B: {self.run_b_path}")
        
        if self.run_a_play_id:
            print(f"  Play A: {self.run_a_play_id}")
        if self.run_b_play_id:
            print(f"  Play B: {self.run_b_play_id}")
        
        print(f"\n  Hash Comparisons:")
        for comp in self.hash_comparisons:
            icon = "[OK]" if comp.matches else "[MISMATCH]"
            print(f"    {icon} {comp.field_name}:")
            print(f"       A: {comp.run_a_value}")
            print(f"       B: {comp.run_b_value}")
        
        if self.errors:
            print(f"\n  Errors:")
            for err in self.errors:
                print(f"    [!] {err}")
        
        if self.warnings:
            print(f"\n  Warnings:")
            for warn in self.warnings:
                print(f"    [WARN] {warn}")
        
        print(f"{'='*60}\n")


def load_result_json(run_path: Path) -> dict[str, Any] | None:
    """Load result.json from a run path."""
    result_file = run_path / STANDARD_FILES["result"]
    if not result_file.exists():
        return None
    with open(result_file, "r", encoding="utf-8") as f:
        return json.load(f)


def compare_runs(
    run_a_path: Path,
    run_b_path: Path,
) -> DeterminismResult:
    """
    Compare two backtest runs for determinism.
    
    Args:
        run_a_path: Path to first run's artifact folder
        run_b_path: Path to second run's artifact folder
        
    Returns:
        DeterminismResult with comparison details
    """
    result = DeterminismResult(
        passed=True,
        run_a_path=str(run_a_path),
        run_b_path=str(run_b_path),
        mode="compare",
    )
    
    # Load result.json from both runs
    result_a = load_result_json(run_a_path)
    result_b = load_result_json(run_b_path)
    
    if result_a is None:
        result.passed = False
        result.errors.append(f"Cannot load result.json from run A: {run_a_path}")
        return result
    
    if result_b is None:
        result.passed = False
        result.errors.append(f"Cannot load result.json from run B: {run_b_path}")
        return result
    
    # Extract Play IDs
    result.run_a_play_id = result_a.get("play_id", "")
    result.run_b_play_id = result_b.get("play_id", "")
    
    # Warn if different Plays
    if result.run_a_play_id != result.run_b_play_id:
        result.warnings.append(
            f"Comparing different Plays: {result.run_a_play_id} vs {result.run_b_play_id}"
        )
    
    # Compare hashes
    hash_fields = ["trades_hash", "equity_hash", "run_hash", "play_hash"]
    
    for field_name in hash_fields:
        a_missing = field_name not in result_a
        b_missing = field_name not in result_b
        if a_missing or b_missing:
            missing_in = []
            if a_missing:
                missing_in.append("run_a")
            if b_missing:
                missing_in.append("run_b")
            result.warnings.append(
                f"Hash field '{field_name}' missing from {', '.join(missing_in)}"
            )
            continue

        val_a = result_a[field_name]
        val_b = result_b[field_name]

        matches = val_a == val_b
        
        comparison = HashComparison(
            field_name=field_name,
            run_a_value=val_a,
            run_b_value=val_b,
            matches=matches,
        )
        result.hash_comparisons.append(comparison)
        
        # Output hashes must match for determinism
        if field_name in ["trades_hash", "equity_hash", "run_hash"] and not matches:
            result.passed = False
            result.errors.append(f"Hash mismatch for {field_name}")
    
    return result


def verify_determinism_rerun(
    run_path: Path,
    sync: bool = False,
    plays_dir: Path | None = None,
) -> DeterminismResult:
    """
    Verify determinism by re-running the same Play and comparing outputs.

    Args:
        run_path: Path to existing run's artifact folder
        sync: Whether to allow data sync during re-run
        plays_dir: Override Play directory (propagated to re-run)

    Returns:
        DeterminismResult with comparison details
    """
    result = DeterminismResult(
        passed=True,
        run_a_path=str(run_path),
        run_b_path="",  # Will be set after re-run
        mode="rerun",
    )
    
    # Load manifest from existing run to get Play and window
    manifest_file = run_path / STANDARD_FILES["run_manifest"]
    if not manifest_file.exists():
        result.passed = False
        result.errors.append(f"Cannot load run_manifest.json from: {run_path}")
        return result
    
    with open(manifest_file, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    
    play_id = manifest.get("play_id", "")
    window_start = manifest.get("window_start", "")
    window_end = manifest.get("window_end", "")

    if not play_id:
        result.passed = False
        result.errors.append("Manifest missing play_id")
        return result

    # Extract data_env from manifest's data_source_id (e.g., "duckdb_live" -> "live")
    data_source_id = manifest.get("data_source_id", "duckdb_live")
    if data_source_id.startswith("duckdb_"):
        data_env = data_source_id.removeprefix("duckdb_")
    else:
        data_env = "live"  # Default for non-duckdb sources

    result.run_a_play_id = play_id

    # Import here to avoid circular imports
    from src.tools.backtest_play_tools import backtest_run_play_tool

    # Re-run the Play with the same window, env, and plays_dir
    rerun_result = backtest_run_play_tool(
        play_id=play_id,
        env=data_env,
        start=window_start,
        end=window_end,
        sync=sync,
        plays_dir=plays_dir,
    )
    
    if not rerun_result.success:
        result.passed = False
        result.errors.append(f"Re-run failed: {rerun_result.message}")
        return result
    
    # Get the new run path from the result
    if not rerun_result.data or "artifact_path" not in rerun_result.data:
        result.passed = False
        result.errors.append("Re-run did not return artifact_path")
        return result
    
    rerun_path = Path(rerun_result.data["artifact_path"])
    result.run_b_path = str(rerun_path)
    result.run_b_play_id = play_id
    
    # Now compare the two runs
    comparison = compare_runs(run_path, rerun_path)
    
    # Merge results
    result.hash_comparisons = comparison.hash_comparisons
    result.errors.extend(comparison.errors)
    result.warnings.extend(comparison.warnings)
    result.passed = comparison.passed
    
    return result

