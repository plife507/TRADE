"""
Functional Tests - Real Data Engine Validation.

Uses real historical data from DuckDB to validate engine functionality.
Tests strategy concepts with auto-adjusting date ranges.

Key Principle:
    If a strategy doesn't produce signals for a date range,
    change the DATE RANGE, not the strategy.
"""

from .engine_validator import EngineValidator, ValidationResult

__all__ = ["EngineValidator", "ValidationResult"]
