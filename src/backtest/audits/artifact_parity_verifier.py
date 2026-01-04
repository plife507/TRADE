"""
Artifact Parity Verifier.

Validates CSV ↔ Parquet parity for backtest artifacts.
Phase 3.1: Used during dual-write phase to ensure identical data.

Usage:
    from src.backtest.audits.artifact_parity_verifier import verify_run_parity
    
    result = verify_run_parity(run_dir)
    if not result.passed:
        for error in result.errors:
            print(error)
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from ..artifacts.parquet_writer import compare_csv_parquet


# Artifacts that should have both CSV and Parquet versions
PARITY_ARTIFACTS = [
    "trades",
    "equity", 
    "account_curve",
]


@dataclass
class ArtifactParityResult:
    """Result of a single artifact parity check."""
    artifact_name: str
    csv_path: Path
    parquet_path: Path
    passed: bool
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_name": self.artifact_name,
            "csv_path": str(self.csv_path),
            "parquet_path": str(self.parquet_path),
            "passed": self.passed,
            "errors": self.errors,
        }


@dataclass
class RunParityResult:
    """Result of parity verification for an entire run."""
    run_dir: Path
    passed: bool
    artifacts_checked: int = 0
    artifacts_passed: int = 0
    artifact_results: list[ArtifactParityResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_dir": str(self.run_dir),
            "passed": self.passed,
            "artifacts_checked": self.artifacts_checked,
            "artifacts_passed": self.artifacts_passed,
            "artifact_results": [r.to_dict() for r in self.artifact_results],
            "errors": self.errors,
        }
    
    def print_summary(self) -> None:
        """Print verification summary to console."""
        status = "[PASS]" if self.passed else "[FAIL]"
        print(f"\n{status} CSV ↔ Parquet Parity Verification")
        print(f"   Run Dir: {self.run_dir}")
        print(f"   Artifacts: {self.artifacts_passed}/{self.artifacts_checked} passed")
        
        for ar in self.artifact_results:
            icon = "✓" if ar.passed else "✗"
            print(f"   {icon} {ar.artifact_name}: {'PASS' if ar.passed else 'FAIL'}")
            for err in ar.errors:
                print(f"      - {err}")
        
        if self.errors:
            print("   Errors:")
            for err in self.errors:
                print(f"      - {err}")
        print()


def verify_artifact_parity(
    run_dir: Path,
    artifact_name: str,
    float_tolerance: float = 1e-12,
) -> ArtifactParityResult:
    """
    Verify parity between CSV and Parquet versions of an artifact.
    
    Args:
        run_dir: Path to run directory
        artifact_name: Name of artifact (e.g., "trades", "equity")
        float_tolerance: Tolerance for float comparison
        
    Returns:
        ArtifactParityResult with pass/fail and error details
    """
    csv_path = run_dir / f"{artifact_name}.csv"
    parquet_path = run_dir / f"{artifact_name}.parquet"
    
    result = ArtifactParityResult(
        artifact_name=artifact_name,
        csv_path=csv_path,
        parquet_path=parquet_path,
        passed=False,
    )
    
    # Check both files exist
    if not csv_path.exists():
        result.errors.append(f"CSV file not found: {csv_path}")
        return result
    
    if not parquet_path.exists():
        result.errors.append(f"Parquet file not found: {parquet_path}")
        return result
    
    # Compare contents
    passed, errors = compare_csv_parquet(csv_path, parquet_path, float_tolerance)
    result.passed = passed
    result.errors = errors
    
    return result


def verify_run_parity(
    run_dir: Path,
    artifacts: list[str] | None = None,
    float_tolerance: float = 1e-12,
) -> RunParityResult:
    """
    Verify CSV ↔ Parquet parity for all artifacts in a run.
    
    Args:
        run_dir: Path to run directory
        artifacts: List of artifact names to check (default: all)
        float_tolerance: Tolerance for float comparison
        
    Returns:
        RunParityResult with overall pass/fail and per-artifact results
    """
    if artifacts is None:
        artifacts = PARITY_ARTIFACTS
    
    result = RunParityResult(
        run_dir=run_dir,
        passed=True,
    )
    
    # Check run dir exists
    if not run_dir.exists():
        result.passed = False
        result.errors.append(f"Run directory not found: {run_dir}")
        return result
    
    # Verify each artifact
    for artifact_name in artifacts:
        ar = verify_artifact_parity(run_dir, artifact_name, float_tolerance)
        result.artifact_results.append(ar)
        result.artifacts_checked += 1
        
        if ar.passed:
            result.artifacts_passed += 1
        else:
            result.passed = False
    
    return result


def find_latest_run(
    base_dir: Path,
    idea_card_id: str,
    symbol: str,
) -> Path | None:
    """
    Find the latest run directory for an idea card + symbol.
    
    Args:
        base_dir: Base backtests directory
        idea_card_id: Play ID
        symbol: Trading symbol
        
    Returns:
        Path to latest run directory, or None if not found
    """
    symbol_dir = base_dir / idea_card_id / symbol
    if not symbol_dir.exists():
        return None
    
    # Find highest run number
    max_run = 0
    latest_run = None
    
    for folder in symbol_dir.iterdir():
        if folder.is_dir() and folder.name.startswith("run-"):
            try:
                run_num = int(folder.name[4:])
                if run_num > max_run:
                    max_run = run_num
                    latest_run = folder
            except ValueError:
                pass
    
    return latest_run


def verify_idea_card_parity(
    base_dir: Path,
    idea_card_id: str,
    symbol: str,
    run_id: str | None = None,
    float_tolerance: float = 1e-12,
) -> RunParityResult:
    """
    Verify parity for a specific idea card run.
    
    Args:
        base_dir: Base backtests directory (default: Path("backtests"))
        idea_card_id: Play ID
        symbol: Trading symbol
        run_id: Specific run ID (e.g., "run-001") or None for latest
        float_tolerance: Tolerance for float comparison
        
    Returns:
        RunParityResult with verification results
    """
    if run_id:
        run_dir = base_dir / idea_card_id / symbol / run_id
    else:
        run_dir = find_latest_run(base_dir, idea_card_id, symbol)
        if run_dir is None:
            return RunParityResult(
                run_dir=base_dir / idea_card_id / symbol / "unknown",
                passed=False,
                errors=[f"No runs found for {idea_card_id}/{symbol}"],
            )
    
    return verify_run_parity(run_dir, float_tolerance=float_tolerance)

