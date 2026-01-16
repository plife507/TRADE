"""
System Normalizer - Strict validation and normalization.

Pure function that validates System configurations against:
- Required fields (id, version, plays)
- Play references must exist in strategies/plays/
- Risk profile validation
- Regime features validation (if used)

Returns NormalizationResult with errors/warnings.

Hierarchy: Block → Play → System
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..blocks import NormalizationResult, NormalizationError
from .system import System


# Default plays directory for reference validation
DEFAULT_PLAYS_DIR = Path("strategies/plays")

# Valid modes
VALID_MODES = {"backtest", "demo", "live"}


def normalize_system_strict(
    raw: dict[str, Any],
    fail_on_error: bool = True,
    plays_dir: Path | str | None = None,
) -> tuple[System | None, NormalizationResult]:
    """
    Normalize and validate a System configuration.

    Pure function. No side effects. Fail-loud on invalid input.

    Validation rules:
    - Required fields: id, version, plays (≥1)
    - All play_id references must exist in strategies/plays/
    - risk_profile.initial_capital_usdt must be positive (if provided)
    - risk_profile.max_drawdown_pct must be 0-100 (if provided)
    - mode must be one of: backtest, demo, live
    - regime_features indicators must exist in registry (if used)
    - base_weight must be 0.0-1.0

    Args:
        raw: Raw dictionary from YAML
        fail_on_error: If True, raise NormalizationError on errors
        plays_dir: Directory for play references (default: strategies/plays/)

    Returns:
        Tuple of (System or None, NormalizationResult)

    Raises:
        NormalizationError: If fail_on_error=True and validation fails
    """
    result = NormalizationResult()

    if plays_dir is None:
        plays_dir = DEFAULT_PLAYS_DIR
    else:
        plays_dir = Path(plays_dir)

    # Required fields
    if not raw.get("id"):
        result.add_error("Missing required field: id")

    if not raw.get("version"):
        result.add_error("Missing required field: version")

    # Accept both 'plays' (new) and 'playbooks' (legacy migration)
    plays = raw.get("plays") or raw.get("playbooks")
    if not plays:
        result.add_error("Missing required field: plays (must have at least one)")
    elif not isinstance(plays, list):
        result.add_error("Field 'plays' must be a list")
    elif len(plays) == 0:
        result.add_error("Field 'plays' must have at least one entry")

    # Validate mode
    mode = raw.get("mode", "backtest")
    if mode not in VALID_MODES:
        result.add_error(f"Invalid mode '{mode}'. Valid modes: {sorted(VALID_MODES)}")

    # If we have critical errors, stop here
    if not result.valid:
        if fail_on_error:
            raise NormalizationError(result.errors)
        return None, result

    # Validate play references
    total_weight = 0.0
    seen_play_ids: set[str] = set()

    for i, entry in enumerate(plays):
        if not isinstance(entry, dict):
            result.add_error(f"plays[{i}]: must be a dict")
            continue

        # Accept both 'play_id' (new) and 'playbook_id' (legacy)
        play_id = entry.get("play_id") or entry.get("playbook_id")
        if not play_id:
            result.add_error(f"plays[{i}]: missing 'play_id' field")
            continue

        # Check for duplicates
        if play_id in seen_play_ids:
            result.add_error(f"plays[{i}]: duplicate play_id '{play_id}'")
        seen_play_ids.add(play_id)

        # Check play exists (search main dir, _validation, _stress_test)
        play_found = False
        search_paths = [
            plays_dir,
            plays_dir / "_validation",
            plays_dir / "_stress_test",
        ]
        for search_path in search_paths:
            play_path = search_path / f"{play_id}.yml"
            if play_path.exists():
                play_found = True
                break

        if not play_found:
            result.add_error(
                f"plays[{i}]: play_id '{play_id}' not found in {plays_dir}"
            )

        # Validate base_weight (accept both 'base_weight' and 'weight')
        weight = entry.get("base_weight", entry.get("weight", 1.0))
        if not isinstance(weight, (int, float)):
            result.add_error(f"plays[{i}]: base_weight must be a number")
        elif not (0.0 <= weight <= 1.0):
            result.add_error(
                f"plays[{i}]: base_weight must be 0.0-1.0, got {weight}"
            )
        else:
            enabled = entry.get("enabled", True)
            if enabled:
                total_weight += weight

        # Validate regime_weight if provided
        regime_weight = entry.get("regime_weight")
        if regime_weight:
            if not isinstance(regime_weight, dict):
                result.add_error(f"plays[{i}].regime_weight: must be a dict")
            else:
                if "condition" not in regime_weight:
                    result.add_error(f"plays[{i}].regime_weight: missing 'condition'")
                multiplier = regime_weight.get("multiplier", 1.0)
                if not isinstance(multiplier, (int, float)):
                    result.add_error(f"plays[{i}].regime_weight: multiplier must be a number")
                elif multiplier <= 0:
                    result.add_error(f"plays[{i}].regime_weight: multiplier must be positive")

    # Validate risk profile if provided
    risk_profile = raw.get("risk_profile", {})
    if risk_profile:
        initial_capital = risk_profile.get("initial_capital_usdt") or risk_profile.get("initial_capital")
        if initial_capital is not None:
            if not isinstance(initial_capital, (int, float)):
                result.add_error("risk_profile.initial_capital must be a number")
            elif initial_capital <= 0:
                result.add_error(
                    f"risk_profile.initial_capital must be positive, got {initial_capital}"
                )

        max_dd = risk_profile.get("max_drawdown_pct")
        if max_dd is not None:
            if not isinstance(max_dd, (int, float)):
                result.add_error("risk_profile.max_drawdown_pct must be a number")
            elif not (0 < max_dd <= 100):
                result.add_error(
                    f"risk_profile.max_drawdown_pct must be 0-100, got {max_dd}"
                )

    # Validate regime_features if provided
    regime_features = raw.get("regime_features", {})
    if regime_features:
        from src.indicators import get_registry
        registry = get_registry()

        for feature_id, feature_config in regime_features.items():
            if not isinstance(feature_config, dict):
                result.add_error(f"regime_features.{feature_id}: must be a dict")
                continue

            indicator_type = feature_config.get("indicator")
            if not indicator_type:
                result.add_error(f"regime_features.{feature_id}: missing 'indicator' field")
                continue

            if not registry.is_supported(indicator_type):
                result.add_error(
                    f"regime_features.{feature_id}: indicator '{indicator_type}' "
                    f"not found in INDICATOR_REGISTRY"
                )

    # If there are errors and fail_on_error, raise
    if not result.valid and fail_on_error:
        raise NormalizationError(result.errors)

    # Create System if valid
    if result.valid:
        try:
            system = System.from_dict(raw)
            return system, result
        except Exception as e:
            result.add_error(f"Failed to create System: {e}")
            if fail_on_error:
                raise NormalizationError(result.errors)

    return None, result
