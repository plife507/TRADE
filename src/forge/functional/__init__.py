"""
Tier 5: Functional Tests - Real Data Engine Validation.

Uses real historical data from DuckDB to validate engine functionality.
Tests strategy concepts with auto-adjusting date ranges.

Key Principle:
    If a strategy doesn't produce signals for a date range,
    change the DATE RANGE, not the strategy.
"""

from .runner import run_functional_tests, FunctionalTestResult

__all__ = ["run_functional_tests", "FunctionalTestResult"]
