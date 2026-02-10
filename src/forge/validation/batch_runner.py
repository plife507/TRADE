"""
Batch Validation Runner - Validate multiple Plays at once.

Architecture Principle: Pure Math
- Input: Directory path or list of paths
- Output: BatchValidationResult
- No side effects, no control flow about invocation

Usage:
    from src.forge.validation import validate_batch

    result = validate_batch("tests/functional/plays/_validation")

    print(f"Passed: {result.passed}/{result.total}")
    for fail in result.failed:
        print(f"  {fail.play_id}: {fail.format_errors()}")
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .play_validator import validate_play_file, PlayValidationResult


@dataclass
class BatchValidationResult:
    """Result of batch Play validation.

    Pure data container - no methods that modify state.
    """

    directory: Path
    total: int
    passed: int
    failed_count: int
    results: list[PlayValidationResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        """Check if all validations passed."""
        return self.failed_count == 0

    @property
    def passed_results(self) -> list[PlayValidationResult]:
        """Get only passed results."""
        return [r for r in self.results if r.is_valid]

    @property
    def failed_results(self) -> list[PlayValidationResult]:
        """Get only failed results."""
        return [r for r in self.results if not r.is_valid]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "directory": str(self.directory),
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed_count,
            "all_passed": self.all_passed,
            "results": [r.to_dict() for r in self.results],
        }


def validate_batch(
    directory: str | Path,
    pattern: str = "*.yml",
    recursive: bool = False,
) -> BatchValidationResult:
    """Validate all Plays in a directory.

    Pure function: directory -> BatchValidationResult

    Args:
        directory: Directory containing Play YAML files
        pattern: Glob pattern for files (default: "*.yml")
        recursive: If True, search subdirectories (default: False)

    Returns:
        BatchValidationResult with all validation results
    """
    dir_path = Path(directory)

    if not dir_path.exists():
        return BatchValidationResult(
            directory=dir_path,
            total=0,
            passed=0,
            failed_count=0,
            results=[],
        )

    # Find all matching files
    if recursive:
        files = sorted(dir_path.rglob(pattern))
    else:
        files = sorted(dir_path.glob(pattern))

    # Validate each file
    results: list[PlayValidationResult] = []
    for file_path in files:
        result = validate_play_file(file_path)
        results.append(result)

    # Count results
    passed = sum(1 for r in results if r.is_valid)
    failed = len(results) - passed

    return BatchValidationResult(
        directory=dir_path,
        total=len(results),
        passed=passed,
        failed_count=failed,
        results=results,
    )


def validate_files(file_paths: list[str | Path]) -> BatchValidationResult:
    """Validate a specific list of Play files.

    Pure function: list[path] -> BatchValidationResult

    Args:
        file_paths: List of paths to Play YAML files

    Returns:
        BatchValidationResult with all validation results
    """
    results: list[PlayValidationResult] = []

    for file_path in file_paths:
        result = validate_play_file(file_path)
        results.append(result)

    passed = sum(1 for r in results if r.is_valid)
    failed = len(results) - passed

    # Use first file's parent as directory, or current dir
    if file_paths:
        directory = Path(file_paths[0]).parent
    else:
        directory = Path(".")

    return BatchValidationResult(
        directory=directory,
        total=len(results),
        passed=passed,
        failed_count=failed,
        results=results,
    )
