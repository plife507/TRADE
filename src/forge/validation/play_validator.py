"""
Play Validator - Pure function validation for Play configs.

Architecture Principle: Pure Math
- Input: Play dict or file path
- Output: PlayValidationResult
- No side effects, no control flow about invocation

Usage:
    from src.forge.validation import validate_play, validate_play_file

    # From dict
    result = validate_play(play_dict)

    # From file
    result = validate_play_file("tests/functional/plays/my_play.yml")

    if not result.is_valid:
        print(result.format_errors())
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from src.backtest.play_yaml_builder import (
    validate_play_yaml,
    normalize_play_yaml,
    ValidationResult as YamlValidationResult,
    ValidationError,
    ValidationErrorCode,
    format_validation_errors,
)


@dataclass
class PlayValidationResult:
    """Result of Play validation.

    Pure data container - no methods that modify state.
    """

    play_id: str
    is_valid: bool
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    normalized_play: dict[str, Any] | None = None
    source_path: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "play_id": self.play_id,
            "is_valid": self.is_valid,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": self.warnings,
            "source_path": str(self.source_path) if self.source_path else None,
        }

    def format_errors(self) -> str:
        """Format errors for display."""
        if not self.errors:
            return ""
        return format_validation_errors(self.errors)


def validate_play(play_dict: dict[str, Any]) -> PlayValidationResult:
    """Validate a Play config dict.

    Pure function: dict -> PlayValidationResult

    Args:
        play_dict: Play configuration as dict

    Returns:
        PlayValidationResult with validation status and any errors
    """
    play_id = play_dict.get("id", "<unknown>")

    # Run YAML validation (checks indicator types, params, references)
    yaml_result = validate_play_yaml(play_dict)

    if not yaml_result.is_valid:
        return PlayValidationResult(
            play_id=play_id,
            is_valid=False,
            errors=yaml_result.errors,
            warnings=yaml_result.warnings,
        )

    # Try normalization (expands defaults, validates blocks)
    try:
        normalized = normalize_play_yaml(play_dict)
        return PlayValidationResult(
            play_id=play_id,
            is_valid=True,
            errors=[],
            warnings=yaml_result.warnings,
            normalized_play=normalized,
        )
    except Exception as e:
        return PlayValidationResult(
            play_id=play_id,
            is_valid=False,
            errors=[
                ValidationError(
                    code=ValidationErrorCode.MISSING_REQUIRED_FIELD,
                    message=f"Normalization failed: {e}",
                )
            ],
            warnings=yaml_result.warnings,
        )


def validate_play_file(file_path: str | Path) -> PlayValidationResult:
    """Validate a Play from a YAML file.

    Pure function: path -> PlayValidationResult

    Args:
        file_path: Path to Play YAML file

    Returns:
        PlayValidationResult with validation status and any errors
    """
    path = Path(file_path)

    if not path.exists():
        return PlayValidationResult(
            play_id=path.stem,
            is_valid=False,
            errors=[
                ValidationError(
                    code=ValidationErrorCode.MISSING_REQUIRED_FIELD,
                    message=f"File not found: {path}",
                )
            ],
            source_path=path,
        )

    try:
        with open(path, "r", encoding="utf-8") as f:
            play_dict = yaml.safe_load(f)
    except yaml.YAMLError as e:
        return PlayValidationResult(
            play_id=path.stem,
            is_valid=False,
            errors=[
                ValidationError(
                    code=ValidationErrorCode.MISSING_REQUIRED_FIELD,
                    message=f"YAML parse error: {e}",
                )
            ],
            source_path=path,
        )

    if not isinstance(play_dict, dict):
        return PlayValidationResult(
            play_id=path.stem,
            is_valid=False,
            errors=[
                ValidationError(
                    code=ValidationErrorCode.MISSING_REQUIRED_FIELD,
                    message="YAML file must contain a dict at root level",
                )
            ],
            source_path=path,
        )

    result = validate_play(play_dict)
    result.source_path = path
    return result
