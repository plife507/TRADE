"""
Validation Runner - CLI runner for syntax validation.

This module provides the main entry point for running syntax validation tests.
Only tier0 (syntax & parse) is supported - higher tiers were removed as they
tested divergent code paths.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class TierName(Enum):
    """Validation tier identifiers."""
    TIER0 = "tier0"


@dataclass
class TestResult:
    """Result of a single test."""
    test_id: str
    passed: bool
    message: str = ""
    duration_ms: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class TierResult:
    """Result of running a validation tier."""
    tier: TierName
    passed: bool
    tests: list[TestResult] = field(default_factory=list)
    duration_ms: float = 0.0
    error: str | None = None

    @property
    def passed_count(self) -> int:
        return sum(1 for t in self.tests if t.passed)

    @property
    def failed_count(self) -> int:
        return sum(1 for t in self.tests if not t.passed)

    @property
    def total_count(self) -> int:
        return len(self.tests)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tier": self.tier.value,
            "passed": self.passed,
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "total_count": self.total_count,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "tests": [
                {
                    "test_id": t.test_id,
                    "passed": t.passed,
                    "message": t.message,
                    "duration_ms": t.duration_ms,
                }
                for t in self.tests
            ],
        }


@dataclass
class ValidationResult:
    """Result of running all validation tiers."""
    tiers: list[TierResult] = field(default_factory=list)
    total_duration_ms: float = 0.0

    @property
    def all_passed(self) -> bool:
        return all(t.passed for t in self.tiers)

    @property
    def passed_tiers(self) -> int:
        return sum(1 for t in self.tiers if t.passed)

    @property
    def total_tiers(self) -> int:
        return len(self.tiers)

    def to_dict(self) -> dict[str, Any]:
        return {
            "all_passed": self.all_passed,
            "passed_tiers": self.passed_tiers,
            "total_tiers": self.total_tiers,
            "total_duration_ms": self.total_duration_ms,
            "tiers": [t.to_dict() for t in self.tiers],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


# =============================================================================
# Tier Runners
# =============================================================================

def run_tier0() -> TierResult:
    """Run Tier 0: Syntax & Parse validation."""
    from .tier0_syntax import test_parse
    return test_parse.run_all()


TIER_RUNNERS: dict[TierName, Callable[[], TierResult]] = {
    TierName.TIER0: run_tier0,
}


def run_tier(tier: str | TierName) -> TierResult:
    """
    Run a single validation tier.

    Args:
        tier: Tier name (e.g., "tier0" or TierName enum)

    Returns:
        TierResult with test outcomes
    """
    if isinstance(tier, str):
        try:
            tier = TierName(tier.lower())
        except ValueError:
            return TierResult(
                tier=TierName.TIER0,
                passed=False,
                error=f"Unknown tier: {tier}. Valid: {[t.value for t in TierName]}",
            )

    runner = TIER_RUNNERS.get(tier)
    if runner is None:
        return TierResult(
            tier=tier,
            passed=False,
            error=f"No runner for tier: {tier.value}",
        )

    start = time.perf_counter()
    try:
        result = runner()
        result.duration_ms = (time.perf_counter() - start) * 1000
        return result
    except Exception as e:
        return TierResult(
            tier=tier,
            passed=False,
            duration_ms=(time.perf_counter() - start) * 1000,
            error=f"Tier {tier.value} failed with exception: {e}",
        )


def run_all_tiers() -> ValidationResult:
    """
    Run all validation tiers in sequence.

    Returns:
        ValidationResult with outcomes from all tiers
    """
    result = ValidationResult()
    start = time.perf_counter()

    for tier in TierName:
        tier_result = run_tier(tier)
        result.tiers.append(tier_result)

    result.total_duration_ms = (time.perf_counter() - start) * 1000
    return result


def print_results(result: ValidationResult, use_json: bool = False) -> None:
    """Print validation results to stdout."""
    if use_json:
        print(result.to_json())
        return

    print("\n" + "=" * 70)
    print("TRADE VALIDATION RESULTS")
    print("=" * 70)

    for tier_result in result.tiers:
        status = "PASS" if tier_result.passed else "FAIL"
        print(
            f"\n{tier_result.tier.value.upper()}: {status} "
            f"({tier_result.passed_count}/{tier_result.total_count} tests, "
            f"{tier_result.duration_ms:.0f}ms)"
        )

        if tier_result.error:
            print(f"  ERROR: {tier_result.error}")

        for test in tier_result.tests:
            if not test.passed:
                print(f"  FAIL: {test.test_id} - {test.message}")

    print("\n" + "-" * 70)
    overall = "PASS" if result.all_passed else "FAIL"
    print(
        f"OVERALL: {overall} "
        f"({result.passed_tiers}/{result.total_tiers} tiers, "
        f"{result.total_duration_ms:.0f}ms)"
    )
    print("=" * 70 + "\n")


def main(args: list[str] | None = None) -> int:
    """
    Main entry point for validation runner.

    Args:
        args: Command line arguments (default: sys.argv[1:])

    Returns:
        Exit code (0 = all pass, 1 = failures)
    """
    if args is None:
        args = sys.argv[1:]

    use_json = "--json" in args
    args = [a for a in args if a != "--json"]

    if not args or args[0] in ("help", "--help", "-h"):
        print("Usage: python -m tests.validation.runner <tier|all> [--json]")
        print("\nTiers:")
        print("  tier0  - Syntax & Parse (<5 sec)")
        print("  all    - Run all tiers")
        print("\nOptions:")
        print("  --json - Output results as JSON")
        return 0

    tier_arg = args[0].lower()

    if tier_arg == "all":
        result = run_all_tiers()
        print_results(result, use_json)
        return 0 if result.all_passed else 1
    else:
        tier_result = run_tier(tier_arg)
        # Wrap in ValidationResult for consistent output
        result = ValidationResult(
            tiers=[tier_result],
            total_duration_ms=tier_result.duration_ms,
        )
        print_results(result, use_json)
        return 0 if tier_result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
