"""
Play Normalizer - Strict validation and normalization.

Pure function that validates Play configurations (modern v3.0.0 format) against:
- Required fields (id, version, symbol, tf, features, actions, risk)
- Feature registry (indicators must exist in INDICATOR_REGISTRY)
- DSL actions syntax (must be parseable)
- Symbol validation (USDT-quoted only)
- Block references (must exist in configs/blocks/)

Returns NormalizationResult with errors/warnings.

Schema Requirements (v3.0.0 simplified format):
    version: "3.0.0"
    name: "Strategy Name"
    symbol: "BTCUSDT"               # REQUIRED, USDT-quoted
    tf: "15m"                       # REQUIRED, execution timeframe

    features:                       # REQUIRED (at least one)
      ema_fast:
        indicator: ema
        params: { length: 9 }

    actions:                        # REQUIRED (at least one entry action)
      entry_long:
        all:
          - ["ema_fast", ">", 0]

    risk:                           # REQUIRED (all fields)
      stop_loss_pct: 2.0
      take_profit_pct: 4.0
      max_position_pct: 5.0
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.backtest.indicator_registry import get_registry
from src.backtest.play import Play

from ..blocks import NormalizationResult, NormalizationError


# Valid timeframes
VALID_TIMEFRAMES = {
    "1m", "3m", "5m", "15m", "30m",
    "1h", "2h", "4h", "6h", "8h", "12h", "1D"
}

# Required risk fields
REQUIRED_RISK_FIELDS = {
    "stop_loss_pct",
    "take_profit_pct",
    "max_position_pct",
}

# Required account fields (for full account mode)
REQUIRED_ACCOUNT_FIELDS = {
    "starting_equity_usdt",
    "max_leverage",
}

# Valid entry/exit action names
VALID_ACTIONS = {
    "entry_long", "entry_short",
    "exit_long", "exit_short",
    "exit_all", "no_action"
}


def normalize_play_strict(
    raw: dict[str, Any],
    fail_on_error: bool = True,
    blocks_dir: Path | str | None = None,
) -> tuple[Play | None, NormalizationResult]:
    """
    Normalize and validate a Play configuration (v3.0.0 format).

    Pure function. No side effects. Fail-loud on invalid input.

    Validation rules:
    - Required fields: version, symbol (USDT-quoted), tf, features (≥1), actions (≥1), risk.*
    - All feature indicators must exist in INDICATOR_REGISTRY
    - Actions DSL must be parseable
    - Block references must exist in configs/blocks/
    - Symbol must end with 'USDT'

    Args:
        raw: Raw dictionary from YAML
        fail_on_error: If True, raise NormalizationError on errors
        blocks_dir: Directory for block references (default: configs/blocks/)

    Returns:
        Tuple of (Play or None, NormalizationResult)

    Raises:
        NormalizationError: If fail_on_error=True and validation fails
    """
    result = NormalizationResult()

    if blocks_dir is None:
        blocks_dir = Path("configs/blocks")
    else:
        blocks_dir = Path(blocks_dir)

    # Required fields
    if not raw.get("version"):
        result.add_error("Missing required field: version")

    # Symbol validation
    symbol = raw.get("symbol")
    if not symbol:
        result.add_error("Missing required field: symbol")
    elif not symbol.endswith("USDT"):
        result.add_error(f"Symbol must be USDT-quoted, got '{symbol}'")

    # Timeframe validation
    tf = raw.get("tf")
    if not tf:
        result.add_error("Missing required field: tf")
    elif tf not in VALID_TIMEFRAMES:
        result.add_error(
            f"Invalid timeframe '{tf}'. Valid: {sorted(VALID_TIMEFRAMES)}"
        )

    # Features validation
    features = raw.get("features")
    if not features:
        result.add_error("Missing required field: features (must have at least one)")
    elif not isinstance(features, dict):
        result.add_error("Field 'features' must be a dict")
    elif len(features) == 0:
        result.add_error("Field 'features' must have at least one entry")

    # Actions validation
    actions = raw.get("actions")
    if not actions:
        result.add_error("Missing required field: actions (must have at least one entry action)")
    elif not isinstance(actions, (dict, list)):
        result.add_error("Field 'actions' must be a dict or list")

    # Account validation (required for backtest)
    account = raw.get("account")
    if not account:
        result.add_error("Missing required field: account")
    elif isinstance(account, dict):
        for req_field in REQUIRED_ACCOUNT_FIELDS:
            if req_field not in account:
                result.add_error(f"Missing required account field: {req_field}")

    # Risk validation
    risk = raw.get("risk")
    if not risk:
        result.add_error("Missing required field: risk")
    elif isinstance(risk, dict):
        for req_field in REQUIRED_RISK_FIELDS:
            if req_field not in risk:
                result.add_error(f"Missing required risk field: {req_field}")

    # If we have critical errors, stop here
    if not result.valid:
        if fail_on_error:
            raise NormalizationError(result.errors)
        return None, result

    # Validate features against registry
    registry = get_registry()
    declared_feature_ids: set[str] = set()

    for feature_id, feature_spec in features.items():
        declared_feature_ids.add(feature_id)

        if not isinstance(feature_spec, dict):
            result.add_error(f"features.{feature_id}: must be a dict")
            continue

        indicator_type = feature_spec.get("indicator")
        if not indicator_type:
            result.add_error(f"features.{feature_id}: missing 'indicator' field")
            continue

        # Check indicator exists in registry
        if not registry.is_supported(indicator_type):
            result.add_error(
                f"features.{feature_id}: indicator '{indicator_type}' "
                f"not found in INDICATOR_REGISTRY"
            )
            continue

        # Validate params if provided
        params = feature_spec.get("params", {})
        if params:
            try:
                registry.validate_params(indicator_type, params)
            except ValueError as e:
                result.add_error(f"features.{feature_id}: {e}")

    # Validate actions
    _validate_actions(actions, declared_feature_ids, blocks_dir, result)

    # If there are errors and fail_on_error, raise
    if not result.valid and fail_on_error:
        raise NormalizationError(result.errors)

    # Create Play if valid
    if result.valid:
        try:
            play = Play.from_dict(raw)
            return play, result
        except Exception as e:
            result.add_error(f"Failed to create Play: {e}")
            if fail_on_error:
                raise NormalizationError(result.errors)

    return None, result


def _validate_actions(
    actions: dict[str, Any] | list[Any],
    declared_ids: set[str],
    blocks_dir: Path,
    result: NormalizationResult,
) -> None:
    """
    Validate actions structure.

    Supports two formats:
    1. Dict format (simplified):
       actions:
         entry_long:
           all:
             - ["ema_fast", ">", "ema_slow"]

    2. List format (full DSL):
       actions:
         - id: entry
           cases:
             - when: ...
               emit: ...

    Args:
        actions: Actions dict or list
        declared_ids: Set of declared feature IDs
        blocks_dir: Directory for block references
        result: NormalizationResult to add errors to
    """
    # Built-in features
    builtin_features = {"open", "high", "low", "close", "volume", "mark_price"}
    all_valid_ids = declared_ids | builtin_features

    if isinstance(actions, dict):
        # Dict format: action_name -> condition
        has_entry = False
        for action_name, condition in actions.items():
            if action_name.startswith("entry_"):
                has_entry = True

            if action_name not in VALID_ACTIONS:
                result.add_warning(f"actions.{action_name}: unknown action name")

            # Validate condition references
            _validate_condition_refs(
                condition, all_valid_ids, blocks_dir, result, f"actions.{action_name}"
            )

        if not has_entry:
            result.add_error(
                "actions must have at least one entry action (entry_long or entry_short)"
            )

    elif isinstance(actions, list):
        # List format: full DSL blocks
        has_entry = False
        for i, block in enumerate(actions):
            if not isinstance(block, dict):
                result.add_error(f"actions[{i}]: must be a dict")
                continue

            block_id = block.get("id", "")
            if block_id == "entry":
                has_entry = True

            cases = block.get("cases", [])
            for j, case in enumerate(cases):
                if "when" in case:
                    _validate_condition_refs(
                        case["when"],
                        all_valid_ids,
                        blocks_dir,
                        result,
                        f"actions[{i}].cases[{j}].when"
                    )

        if not has_entry:
            result.add_error(
                "actions must have at least one entry block (id: 'entry')"
            )


def _validate_condition_refs(
    condition: Any,
    declared_ids: set[str],
    blocks_dir: Path,
    result: NormalizationResult,
    path: str = "condition",
) -> None:
    """
    Recursively validate that condition references only declared features.

    Also validates block references point to existing configs.

    Args:
        condition: DSL condition (various formats)
        declared_ids: Set of declared feature IDs + builtins
        blocks_dir: Directory for block references
        result: NormalizationResult to add errors/warnings to
        path: Current path for error messages
    """
    if not condition:
        return

    # Handle list format: ["ema_fast", ">", "ema_slow"]
    if isinstance(condition, list):
        if len(condition) >= 3:
            lhs = condition[0]
            rhs = condition[2]

            if isinstance(lhs, str) and lhs not in declared_ids:
                result.add_warning(f"{path}[0]: references undeclared feature '{lhs}'")
            if isinstance(rhs, str) and rhs not in declared_ids and not _is_scalar(rhs):
                result.add_warning(f"{path}[2]: references undeclared feature '{rhs}'")
        return

    if not isinstance(condition, dict):
        return

    # Check for block reference
    if "block" in condition:
        block_id = condition["block"]
        block_path = blocks_dir / f"{block_id}.yml"
        if not block_path.exists():
            result.add_error(
                f"{path}.block: referenced block '{block_id}' not found at {block_path}"
            )
        return

    # Check for feature_id references in lhs/rhs
    for key in ("lhs", "rhs"):
        ref = condition.get(key)
        if isinstance(ref, dict) and "feature_id" in ref:
            feature_id = ref["feature_id"]
            if feature_id not in declared_ids:
                result.add_warning(
                    f"{path}.{key}: references undeclared feature '{feature_id}'"
                )
        elif isinstance(ref, str) and ref not in declared_ids and not _is_scalar(ref):
            result.add_warning(
                f"{path}.{key}: references undeclared feature '{ref}'"
            )

    # Recurse into all/any/not
    if "all" in condition:
        items = condition["all"]
        if isinstance(items, list):
            for i, item in enumerate(items):
                _validate_condition_refs(
                    item, declared_ids, blocks_dir, result, f"{path}.all[{i}]"
                )

    if "any" in condition:
        items = condition["any"]
        if isinstance(items, list):
            for i, item in enumerate(items):
                _validate_condition_refs(
                    item, declared_ids, blocks_dir, result, f"{path}.any[{i}]"
                )

    if "not" in condition:
        _validate_condition_refs(
            condition["not"], declared_ids, blocks_dir, result, f"{path}.not"
        )

    # Window operators
    for window_op in ("holds_for", "occurred_within", "count_true"):
        if window_op in condition:
            window_data = condition[window_op]
            if isinstance(window_data, dict) and "expr" in window_data:
                _validate_condition_refs(
                    window_data["expr"],
                    declared_ids,
                    blocks_dir,
                    result,
                    f"{path}.{window_op}.expr"
                )


def _is_scalar(value: Any) -> bool:
    """Check if value is a scalar (number, bool) rather than a feature reference."""
    return isinstance(value, (int, float, bool))
