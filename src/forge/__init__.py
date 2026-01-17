"""
The Forge - Validation environment for Plays.

Provides:
- Play validation and batch validation
- Audit tools for parity and correctness
- Stress test suite for engine validation
"""

from src.forge.validation import (
    validate_play_file,
    validate_batch,
    format_validation_report,
    BatchValidationResult,
    generate_synthetic_candles,
    SyntheticCandles,
)

from src.forge.audits import (
    run_stress_test_suite,
    StressTestReport,
)

__all__ = [
    "validate_play_file",
    "validate_batch",
    "format_validation_report",
    "BatchValidationResult",
    "generate_synthetic_candles",
    "SyntheticCandles",
    "run_stress_test_suite",
    "StressTestReport",
]
