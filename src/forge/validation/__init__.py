"""
Forge Validation Module.

Pure function validation for Plays:
- validate_play: Single Play validation
- validate_batch: Batch validation across directory
- ValidationResult: Structured validation output

Architecture: Pure functions - input -> computation -> output.
"""

from .play_validator import (
    validate_play,
    validate_play_file,
    PlayValidationResult,
)
from .batch_runner import (
    validate_batch,
    BatchValidationResult,
)
from .report import (
    format_validation_report,
    format_batch_report,
    format_summary_line,
)

__all__ = [
    # Single validation
    "validate_play",
    "validate_play_file",
    "PlayValidationResult",
    # Batch validation
    "validate_batch",
    "BatchValidationResult",
    # Reporting
    "format_validation_report",
    "format_batch_report",
    "format_summary_line",
]
