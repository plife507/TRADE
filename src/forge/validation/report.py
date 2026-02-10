"""
Validation Report Formatting - Pure functions for report generation.

Architecture Principle: Pure Math
- Input: ValidationResult or BatchValidationResult
- Output: Formatted string
- No side effects, no I/O

Usage:
    from src.forge.validation import format_validation_report, format_batch_report

    # Single play report
    print(format_validation_report(result))

    # Batch report
    print(format_batch_report(batch_result))
"""

from .play_validator import PlayValidationResult
from .batch_runner import BatchValidationResult


def format_validation_report(result: PlayValidationResult) -> str:
    """Format a single Play validation result.

    Pure function: PlayValidationResult -> str

    Args:
        result: Validation result to format

    Returns:
        Formatted string report
    """
    lines: list[str] = []

    # Header
    status = "PASS" if result.is_valid else "FAIL"
    lines.append(f"[{status}] {result.play_id}")

    if result.source_path:
        lines.append(f"  Source: {result.source_path}")

    # Errors
    if result.errors:
        lines.append("  Errors:")
        for error in result.errors:
            lines.append(f"    [{error.code.value}] {error.message}")
            if error.location:
                lines.append(f"      Location: {error.location}")
            if error.suggestions:
                lines.append(f"      Suggestions: {', '.join(error.suggestions)}")

    # Warnings
    if result.warnings:
        lines.append("  Warnings:")
        for warning in result.warnings:
            lines.append(f"    {warning}")

    return "\n".join(lines)


def format_batch_report(
    result: BatchValidationResult,
    verbose: bool = False,
    show_passed: bool = False,
) -> str:
    """Format a batch validation result.

    Pure function: BatchValidationResult -> str

    Args:
        result: Batch validation result to format
        verbose: If True, show full details for each Play
        show_passed: If True, also show passed Plays (default: only failures)

    Returns:
        Formatted string report
    """
    lines: list[str] = []

    # Header
    lines.append("=" * 70)
    lines.append("FORGE VALIDATION REPORT")
    lines.append("=" * 70)
    lines.append(f"Directory: {result.directory}")
    lines.append(f"Total: {result.total} | Passed: {result.passed} | Failed: {result.failed_count}")
    lines.append("")

    # Overall status
    if result.all_passed:
        lines.append("STATUS: ALL PASSED")
    else:
        lines.append(f"STATUS: {result.failed_count} FAILED")

    lines.append("-" * 70)

    # Failed plays (always show)
    if result.failed_results:
        lines.append("\nFAILED PLAYS:")
        lines.append("-" * 40)
        for play_result in result.failed_results:
            if verbose:
                lines.append(format_validation_report(play_result))
            else:
                lines.append(f"  [FAIL] {play_result.play_id}")
                if play_result.errors:
                    # Show first error only in non-verbose mode
                    first_error = play_result.errors[0]
                    lines.append(f"         {first_error.message[:60]}...")
        lines.append("")

    # Passed plays (optional)
    if show_passed and result.passed_results:
        lines.append("\nPASSED PLAYS:")
        lines.append("-" * 40)
        for play_result in result.passed_results:
            if verbose:
                lines.append(format_validation_report(play_result))
            else:
                lines.append(f"  [PASS] {play_result.play_id}")
        lines.append("")

    # Summary
    lines.append("=" * 70)
    if result.all_passed:
        lines.append(f"PASS: All {result.total} Plays validated successfully")
    else:
        lines.append(f"FAIL: {result.failed_count}/{result.total} Plays have errors")
    lines.append("=" * 70)

    return "\n".join(lines)


def format_summary_line(result: BatchValidationResult) -> str:
    """Format a single-line summary.

    Pure function: BatchValidationResult -> str

    Args:
        result: Batch validation result

    Returns:
        Single line summary string
    """
    status = "PASS" if result.all_passed else "FAIL"
    return f"[{status}] {result.passed}/{result.total} Plays validated ({result.directory})"
