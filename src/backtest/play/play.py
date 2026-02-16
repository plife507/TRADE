"""
Play: Declarative strategy specification with Feature Registry.

An Play is a self-contained, declarative configuration that defines:
- What features (indicators + structures) the strategy needs, on any timeframe
- What position policy to follow (long_only, short_only, long_short)
- Entry/exit rules (signal logic referencing features by ID)
- Risk model (stop loss, take profit, sizing)

Design principles:
- Explicit over implicit: No silent defaults
- Fail-fast: Validation at load time
- Feature-based: All features referenced by unique ID
- Any timeframe: Features can use low_tf/med_tf/high_tf (exec points to one)
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, TYPE_CHECKING
import yaml

from ..feature_registry import Feature, FeatureType, FeatureRegistry, InputSource
from ..rules.dsl_parser import _is_enum_literal
from .config_models import AccountConfig, FeeModel, ExitMode
from .risk_model import (
    RiskModel,
    StopLossRule,
    StopLossType,
    TakeProfitRule,
    TakeProfitType,
    SizingRule,
    SizingModel,
    TrailingConfig,
    BreakEvenConfig,
)

if TYPE_CHECKING:
    from ..rules.strategy_blocks import Block


# =============================================================================
# Position Policy
# =============================================================================

# =============================================================================
# Synthetic Data Config (for validation plays)
# =============================================================================

@dataclass(frozen=True)
class ValidationConfig:
    """
    Configuration for synthetic validation testing.

    When present in a Play, enables synthetic backtest mode.
    Only the pattern is specified; bars are auto-computed from
    warmup requirements of the play's indicators and structures.

    Attributes:
        pattern: Price pattern to generate (e.g., "trend_up_clean", "choppy")
    """
    pattern: str = "trend_up_clean"

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ValidationConfig":
        """Create from dict."""
        return cls(
            pattern=d.get("pattern", "trend_up_clean"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict."""
        return {
            "pattern": self.pattern,
        }


class PositionMode(str, Enum):
    """Position direction policy."""
    LONG_ONLY = "long_only"
    SHORT_ONLY = "short_only"
    LONG_SHORT = "long_short"


@dataclass(frozen=True)
class PositionPolicy:
    """
    Position policy configuration.

    Attributes:
        mode: Direction policy (long_only, short_only, long_short)
        exit_mode: How positions are closed (sl_tp_only, signal, first_hit)
        max_positions_per_symbol: Max concurrent positions (must be 1)
        allow_flip: Whether to allow position reversal (not supported)
        allow_scale_in: Whether to allow adding to position (not supported)
        allow_scale_out: Whether to allow partial exits (not supported)
    """
    mode: PositionMode = PositionMode.LONG_ONLY
    exit_mode: ExitMode = ExitMode.SL_TP_ONLY
    max_positions_per_symbol: int = 1
    allow_flip: bool = False
    allow_scale_in: bool = False
    allow_scale_out: bool = False

    def __post_init__(self):
        """Validate policy."""
        if self.max_positions_per_symbol != 1:
            raise ValueError("max_positions_per_symbol must be 1 (single position only)")
        if self.allow_scale_in:
            raise ValueError("allow_scale_in=True is not supported")
        if self.allow_scale_out:
            raise ValueError("allow_scale_out=True is not supported")

    def allows_long(self) -> bool:
        """Check if long positions are allowed."""
        return self.mode in (PositionMode.LONG_ONLY, PositionMode.LONG_SHORT)

    def allows_short(self) -> bool:
        """Check if short positions are allowed."""
        return self.mode in (PositionMode.SHORT_ONLY, PositionMode.LONG_SHORT)

    def requires_sl_tp(self) -> bool:
        """Check if SL/TP are required (sl_tp_only or first_hit mode)."""
        return self.exit_mode in (ExitMode.SL_TP_ONLY, ExitMode.FIRST_HIT)

    def allows_signal_exit(self) -> bool:
        """Check if signal-based exits are allowed."""
        return self.exit_mode in (ExitMode.SIGNAL, ExitMode.FIRST_HIT)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "mode": self.mode.value,
            "exit_mode": self.exit_mode.value,
            "max_positions_per_symbol": self.max_positions_per_symbol,
            "allow_flip": self.allow_flip,
            "allow_scale_in": self.allow_scale_in,
            "allow_scale_out": self.allow_scale_out,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PositionPolicy":
        """Create from dict."""
        return cls(
            mode=PositionMode(d.get("mode", "long_only")),
            exit_mode=ExitMode(d.get("exit_mode", "sl_tp_only")),
            max_positions_per_symbol=d.get("max_positions_per_symbol", 1),
            allow_flip=d.get("allow_flip", False),
            allow_scale_in=d.get("allow_scale_in", False),
            allow_scale_out=d.get("allow_scale_out", False),
        )


# =============================================================================
# Shorthand Conversion Helpers
# =============================================================================

def _convert_shorthand_condition(cond: list) -> dict:
    """
    Convert shorthand condition ["a", ">", "b"] to full DSL format.

    Supports symbol operators (canonical form, refactored 2026-01-09):
        ["a", ">", "b"]           -> lhs: a, op: >, rhs: b
        ["a", "<", "b"]           -> lhs: a, op: <, rhs: b
        ["a", ">=", "b"]          -> lhs: a, op: >=, rhs: b
        ["a", "<=", "b"]          -> lhs: a, op: <=, rhs: b
        ["a", "==", 1]            -> lhs: a, op: ==, rhs: 1
        ["a", "!=", "BROKEN"]     -> lhs: a, op: !=, rhs: BROKEN
        ["a", "cross_above", "b"] -> lhs: a, op: cross_above, rhs: b
        ["a", "cross_below", "b"] -> lhs: a, op: cross_below, rhs: b
        ["a", "between", [lo, hi]] -> lhs: a, op: between, rhs: {low: lo, high: hi}
        ["a", "near_pct", "b", tol] -> lhs: a, op: near_pct, rhs: b, tolerance: tol
        ["a", "in", [1, 2]]       -> lhs: a, op: in, rhs: [1, 2]
    """
    if len(cond) < 3:
        raise ValueError(f"Condition must have at least 3 elements: {cond}")

    lhs_raw, op, rhs_raw = cond[0], cond[1], cond[2]

    # No conversion - symbols are the canonical form

    # Lazy import for bracket normalization (e.g., "level[0.618]" -> "level_0.618")
    from ..rules.dsl_parser import _normalize_bracket_syntax

    # Build lhs
    if isinstance(lhs_raw, str):
        if "." in lhs_raw:
            # Structure field: "swing.high_level"
            parts = lhs_raw.split(".", 1)
            lhs = {"feature_id": parts[0], "field": _normalize_bracket_syntax(parts[1])}
        else:
            lhs = {"feature_id": lhs_raw}
    else:
        lhs = lhs_raw

    # Build rhs
    if op == "between" and isinstance(rhs_raw, list) and len(rhs_raw) == 2:
        rhs = {"low": rhs_raw[0], "high": rhs_raw[1]}
    elif isinstance(rhs_raw, str):
        if "." in rhs_raw:
            parts = rhs_raw.split(".", 1)
            rhs = {"feature_id": parts[0], "field": _normalize_bracket_syntax(parts[1])}
        elif _is_enum_literal(rhs_raw):
            rhs = rhs_raw
        else:
            rhs = {"feature_id": rhs_raw}
    else:
        rhs = rhs_raw  # Constant value

    result = {"lhs": lhs, "op": op, "rhs": rhs}

    # Handle tolerance for near_* operators (4th element)
    if len(cond) > 3 and op in ("near_pct", "near_abs"):
        tol = cond[3]
        if op == "near_pct":
            tol = tol / 100.0  # Shorthand uses percentage, eval expects ratio (0.5 -> 0.005)
        result["tolerance"] = tol

    return result


def _convert_condition_item(item: list | dict) -> dict:
    """
    Convert a single condition item which can be either:
    - A list: shorthand condition like ["rsi_14", ">", 50]
    - A dict: window operator like {holds_for: {...}} or nested boolean logic
    """
    if isinstance(item, list):
        return _convert_shorthand_condition(item)
    elif isinstance(item, dict):
        # Dict could be window operator, nested all/any, or already-converted
        return _convert_shorthand_conditions(item)
    else:
        raise ValueError(f"Condition item must be list or dict, got: {type(item)}")


def _convert_shorthand_conditions(block_content: dict | list) -> dict:
    """
    Convert shorthand block content to full DSL "when" clause.

    Input formats:
        {"all": [conditions...]}
        {"any": [conditions...]}
        [condition_list, ...]  # List of conditions (implicit all)
        Single condition list

    Output:
        Full DSL when clause dict.
    """
    # Handle list input (e.g., expr: [["ema_9", "cross_above", "ema_21"]])
    if isinstance(block_content, list):
        if len(block_content) == 0:
            return {}
        elif len(block_content) == 1:
            # Single condition - convert and wrap in all
            return {"all": [_convert_condition_item(block_content[0])]}
        else:
            # Multiple conditions - implicit all
            return {"all": [_convert_condition_item(c) for c in block_content]}

    if "all" in block_content:
        conditions = block_content["all"]
        return {"all": [_convert_condition_item(c) for c in conditions]}
    elif "any" in block_content:
        conditions = block_content["any"]
        return {"any": [_convert_condition_item(c) for c in conditions]}
    elif "not" in block_content:
        inner = block_content["not"]
        if isinstance(inner, list) and len(inner) > 0 and isinstance(inner[0], list):
            # YAML block sequence wraps conditions in a list: not: [["rsi", ">", 70]]
            if len(inner) == 1:
                return {"not": _convert_condition_item(inner[0])}
            else:
                # Multiple conditions under not: wrap in implicit all
                return {"not": {"all": [_convert_condition_item(c) for c in inner]}}
        return {"not": _convert_condition_item(inner)}
    elif "holds_for" in block_content:
        hf = block_content["holds_for"]
        result = {
            "holds_for": {
                "bars": hf["bars"],
                "expr": _convert_shorthand_conditions(hf.get("expr", {})),
            }
        }
        if "anchor_tf" in hf:
            result["holds_for"]["anchor_tf"] = hf["anchor_tf"]
        return result
    elif "occurred_within" in block_content:
        ow = block_content["occurred_within"]
        result = {
            "occurred_within": {
                "bars": ow["bars"],
                "expr": _convert_shorthand_conditions(ow.get("expr", {})),
            }
        }
        if "anchor_tf" in ow:
            result["occurred_within"]["anchor_tf"] = ow["anchor_tf"]
        return result
    elif "count_true" in block_content:
        ct = block_content["count_true"]
        result = {
            "count_true": {
                "bars": ct["bars"],
                "min_true": ct["min_true"],
                "expr": _convert_shorthand_conditions(ct.get("expr", {})),
            }
        }
        if "anchor_tf" in ct:
            result["count_true"]["anchor_tf"] = ct["anchor_tf"]
        return result
    elif "holds_for_duration" in block_content:
        hfd = block_content["holds_for_duration"]
        return {
            "holds_for_duration": {
                "duration": hfd["duration"],
                "expr": _convert_shorthand_conditions(hfd.get("expr", {})),
            }
        }
    elif "occurred_within_duration" in block_content:
        owd = block_content["occurred_within_duration"]
        return {
            "occurred_within_duration": {
                "duration": owd["duration"],
                "expr": _convert_shorthand_conditions(owd.get("expr", {})),
            }
        }
    elif "count_true_duration" in block_content:
        ctd = block_content["count_true_duration"]
        return {
            "count_true_duration": {
                "duration": ctd["duration"],
                "min_true": ctd["min_true"],
                "expr": _convert_shorthand_conditions(ctd.get("expr", {})),
            }
        }

    # Fallback: return as-is (might already be full format)
    # Warn about unrecognized keys that aren't standard DSL keys
    _KNOWN_CONDITION_KEYS = {
        "lhs", "op", "rhs", "tolerance",
        "all", "any", "not",
        "holds_for", "occurred_within", "count_true",
        "holds_for_duration", "occurred_within_duration", "count_true_duration",
        "setup",
    }
    if isinstance(block_content, dict):
        unknown = set(block_content.keys()) - _KNOWN_CONDITION_KEYS
        if unknown:
            import logging
            logging.getLogger(__name__).warning(
                f"Unrecognized keys in condition block (passed through): {sorted(unknown)}"
            )
    return block_content


# =============================================================================
# Play
# =============================================================================

@dataclass
class Play:
    """
    Complete, self-contained strategy specification with Feature Registry.

    A Play declares:
    - Identity (id, version)
    - Account config (starting equity, leverage, fees) - REQUIRED
    - Scope (symbols)
    - exec_tf: The timeframe for bar-by-bar stepping
    - features: List of Feature instances (indicators + structures on any TF)
    - Position policy (direction constraints)
    - actions: Entry/exit rules (DSL with nested boolean logic)
    - Risk model (SL/TP/sizing)
    """
    # Identity
    id: str
    version: str
    name: str | None = None
    description: str | None = None

    # Account configuration (REQUIRED)
    account: AccountConfig | None = None

    # Scope
    symbol_universe: tuple = field(default_factory=tuple)

    # Execution timeframe (bar stepping granularity)
    exec_tf: str = ""

    # Timeframe mapping (3-feed + exec role system)
    # Keys: low_tf, med_tf, high_tf, exec (role pointer)
    tf_mapping: dict[str, str] = field(default_factory=dict)

    # Features (indicators + structures on any TF)
    features: tuple = field(default_factory=tuple)  # Tuple[Feature, ...]

    # Position policy
    position_policy: PositionPolicy = field(default_factory=PositionPolicy)

    # Strategy actions (DSL format with nested all/any/not for entry/exit rules)
    actions: list = field(default_factory=list)  # list["Block"] - entry_long, exit_long, etc.

    # Risk model
    risk_model: RiskModel | None = None

    # Variables for template resolution
    variables: dict[str, Any] = field(default_factory=dict)

    # Structures flag (True if Play defines structures: section)
    # Used to allow structure-only Plays with empty features
    has_structures: bool = False

    # Structure keys (list of structure block keys from structures: section)
    # Used for auto-resolving structure references without "structure." prefix
    structure_keys: tuple = field(default_factory=tuple)

    # Reusable condition blocks (parsed from setups: section)
    # Values are Expr objects (typed as Any to avoid TYPE_CHECKING import at field level)
    setups: dict[str, Any] = field(default_factory=dict)

    # Validation config (for synthetic validation plays)
    # When set, enables synthetic backtest mode with auto-computed warmup
    validation: ValidationConfig | None = None

    # Entry order configuration
    entry_order_type: str = "MARKET"       # "MARKET" | "LIMIT"
    limit_offset_pct: float = 0.0          # % offset from close (e.g., 0.05 = 0.05%)
    time_in_force: str = "GTC"             # "GTC" | "IOC" | "FOK" | "PostOnly"
    expire_after_bars: int = 0             # 0 = no expiry
    tp_order_type: str = "Market"          # "Market" | "Limit" (Bybit convention)
    sl_order_type: str = "Market"          # "Market" | "Limit"

    # Cached feature registry
    _registry: FeatureRegistry | None = field(default=None, repr=False)

    def __post_init__(self):
        """Validate the Play."""
        errors = self.validate()
        if errors:
            raise ValueError(f"Invalid Play: {'; '.join(errors)}")

    def validate(self) -> list[str]:
        """Validate the Play."""
        errors = []

        if not self.id:
            errors.append("id is required")
        if not self.version:
            errors.append("version is required")
        if not self.symbol_universe:
            errors.append("symbol_universe is required (at least one symbol)")

        if self.account is None:
            errors.append("account section is required")

        if not self.exec_tf:
            errors.append("exec_tf is required")

        # Allow structure-only Plays (empty features if structures exist)
        if not self.features and not self.has_structures:
            errors.append("features list is required (at least one feature or structure)")

        # Must have actions for signal generation
        if not self.actions:
            errors.append("actions is required for signal generation")

        # Validate entry order type fields
        valid_order_types = {"MARKET", "LIMIT"}
        if self.entry_order_type not in valid_order_types:
            errors.append(f"entry_order_type must be one of {valid_order_types}, got: {self.entry_order_type!r}")

        valid_tifs = {"GTC", "IOC", "FOK", "PostOnly"}
        if self.time_in_force not in valid_tifs:
            errors.append(f"time_in_force must be one of {valid_tifs}, got: {self.time_in_force!r}")

        if self.limit_offset_pct < 0:
            errors.append(f"limit_offset_pct must be >= 0, got: {self.limit_offset_pct}")

        if self.expire_after_bars < 0:
            errors.append(f"expire_after_bars must be >= 0, got: {self.expire_after_bars}")

        valid_tp_sl_types = {"Market", "Limit"}
        if self.tp_order_type not in valid_tp_sl_types:
            errors.append(f"tp_order_type must be one of {valid_tp_sl_types}, got: {self.tp_order_type!r}")
        if self.sl_order_type not in valid_tp_sl_types:
            errors.append(f"sl_order_type must be one of {valid_tp_sl_types}, got: {self.sl_order_type!r}")

        # Validate operator/type compatibility in actions
        # Only run if we have features and actions (otherwise skip - above errors cover it)
        if self.features and self.actions:
            type_errors = self._validate_action_types()
            errors.extend(type_errors)

            ref_errors = self._validate_action_references()
            errors.extend(ref_errors)

        return errors

    def _validate_action_types(self) -> list[str]:
        """
        Validate operator/type compatibility for all actions.

        Checks that operators are compatible with feature output types:
        - 'eq' cannot be used with FLOAT types (use near_abs/near_pct)
        - Numeric operators (gt, lt, etc.) cannot be used with ENUM/BOOL types

        Returns:
            List of error messages (empty if valid).
        """
        from ..rules.dsl_parser import validate_blocks_types

        try:
            registry = self.feature_registry
            return validate_blocks_types(self.actions, registry.get_output_type)
        except Exception as exc:
            return [f"Type validation failed: {exc}"]

    def _validate_action_references(self) -> list[str]:
        """
        Validate that all FeatureRef/SetupRef nodes reference declared features/setups.

        Returns:
            List of error messages (empty if valid).
        """
        from ..rules.dsl_validator import validate_dsl_references

        try:
            registry = self.feature_registry
            return validate_dsl_references(
                self.actions, registry, self.setups if self.setups else None,
            )
        except Exception as exc:
            return [f"Reference validation failed: {exc}"]

    @property
    def feature_registry(self) -> FeatureRegistry:
        """Get or build the feature registry."""
        if self._registry is None:
            self._registry = FeatureRegistry.from_features(
                exec_tf=self.exec_tf,
                features=list(self.features),
            )
            self._registry.expand_indicator_outputs()
        return self._registry

    @property
    def low_tf(self) -> str | None:
        """Get low timeframe from tf_mapping."""
        return self.tf_mapping.get("low_tf")

    @property
    def med_tf(self) -> str | None:
        """Get medium timeframe from tf_mapping."""
        return self.tf_mapping.get("med_tf")

    @property
    def high_tf(self) -> str | None:
        """Get high timeframe from tf_mapping."""
        return self.tf_mapping.get("high_tf")

    @property
    def exec_role(self) -> str | None:
        """Get exec role pointer (low_tf, med_tf, or high_tf)."""
        return self.tf_mapping.get("exec")

    def get_all_tfs(self) -> set[str]:
        """Get all unique timeframes from features."""
        return self.feature_registry.get_all_tfs()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        result = {
            "id": self.id,
            "version": self.version,
            "name": self.name,
            "description": self.description,
            "symbol_universe": list(self.symbol_universe),
            "exec_tf": self.exec_tf,
            "features": [f.to_dict() for f in self.features],
            "position_policy": self.position_policy.to_dict(),
            "risk_model": self.risk_model.to_dict() if self.risk_model else None,
        }
        if self.tf_mapping:
            result["tf_mapping"] = dict(self.tf_mapping)
        if self.account:
            result["account"] = self.account.to_dict()
        if self.variables:
            result["variables"] = dict(self.variables)
        # Serialize actions
        if self.actions:
            result["actions"] = [b.to_dict() for b in self.actions]
        # Entry order configuration (only serialize non-defaults)
        if self.entry_order_type != "MARKET" or self.limit_offset_pct != 0.0 or self.time_in_force != "GTC" or self.expire_after_bars != 0:
            result["entry"] = {
                "order_type": self.entry_order_type,
                "limit_offset_pct": self.limit_offset_pct,
                "time_in_force": self.time_in_force,
                "expire_after_bars": self.expire_after_bars,
            }
        if self.tp_order_type != "Market" or self.sl_order_type != "Market":
            risk = result.get("risk_model") or {}
            risk["tp_order_type"] = self.tp_order_type
            risk["sl_order_type"] = self.sl_order_type
            if "risk_model" not in result:
                result["risk_model"] = risk
        return result

    # =========================================================================
    # from_dict() helper methods (G4.2 Refactor)
    # =========================================================================

    @staticmethod
    def _parse_timeframes(
        d: dict[str, Any]
    ) -> tuple[str, dict[str, str], str]:
        """
        Parse timeframes section.

        Returns:
            (exec_tf, tf_mapping, exec_role)
        """
        exec_tf = d.get("exec_tf")
        tf_mapping: dict[str, str] = d.get("tf_mapping", {})
        timeframes_section = d.get("timeframes")
        exec_role = "low_tf"  # Default

        if not exec_tf:
            if not timeframes_section:
                raise ValueError(
                    "Missing 'timeframes' section. Example:\n"
                    "timeframes:\n"
                    "  low_tf: \"15m\"\n"
                    "  med_tf: \"15m\"\n"
                    "  high_tf: \"15m\"\n"
                    "  exec: \"low_tf\""
                )

            low_tf = timeframes_section.get("low_tf")
            med_tf = timeframes_section.get("med_tf")
            high_tf = timeframes_section.get("high_tf")
            exec_role = timeframes_section.get("exec")

            missing = []
            if not low_tf:
                missing.append("low_tf")
            if not med_tf:
                missing.append("med_tf")
            if not high_tf:
                missing.append("high_tf")
            if not exec_role:
                missing.append("exec")
            if missing:
                raise ValueError(f"timeframes section missing required keys: {missing}")

            if exec_role not in ("low_tf", "med_tf", "high_tf"):
                raise ValueError(
                    f"timeframes.exec must be 'low_tf', 'med_tf', or 'high_tf', got: {exec_role}"
                )

            tf_mapping = {
                "low_tf": low_tf,
                "med_tf": med_tf,
                "high_tf": high_tf,
                "exec": exec_role,
            }

            if exec_role == "low_tf":
                exec_tf = low_tf
            elif exec_role == "med_tf":
                exec_tf = med_tf
            else:
                exec_tf = high_tf

        return exec_tf, tf_mapping, exec_role

    @staticmethod
    def _parse_features(
        features_raw: dict | list,
        exec_tf: str,
        tf_mapping: dict[str, str] | None = None,
    ) -> tuple[Feature, ...]:
        """
        Parse features section.

        Handles both:
        - YAML dict format: {feature_id: {indicator: ..., params: ...}}
        - Internal list format: list of Feature dicts
        """
        if isinstance(features_raw, dict):
            from ..indicator_registry import get_registry
            registry = get_registry()

            features_list = []
            for feature_id, spec in features_raw.items():
                indicator_type = spec.get("indicator", "")
                params = spec.get("params", {})
                feature_tf = spec.get("tf", exec_tf)
                # Resolve role names (low_tf, med_tf, high_tf) to concrete TFs
                if tf_mapping and feature_tf in tf_mapping and feature_tf != "exec":
                    feature_tf = tf_mapping[feature_tf]

                # Parse input source (e.g. source: volume)
                source_str = spec.get("source", "close")
                try:
                    input_source = InputSource(source_str)
                except ValueError:
                    input_source = InputSource.CLOSE

                output_keys = ()
                if registry.is_supported(indicator_type):
                    if registry.is_multi_output(indicator_type):
                        output_keys = tuple(registry.get_expanded_keys(indicator_type, feature_id))
                    else:
                        output_keys = (feature_id,)

                feature = Feature(
                    id=feature_id,
                    tf=feature_tf,
                    type=FeatureType.INDICATOR,
                    indicator_type=indicator_type,
                    params=params,
                    input_source=input_source,
                    output_keys=output_keys,
                )
                features_list.append(feature)
            return tuple(features_list)
        else:
            return tuple(Feature.from_dict(f) for f in features_raw)

    @staticmethod
    def _parse_setups(setups_data: dict[str, Any]) -> dict[str, Any]:
        """Parse setups: section into {setup_id: Expr} dict.

        Each setup is a condition tree using the same format as action conditions.
        Uses _convert_shorthand_conditions() + parse_expr() for parsing.
        """
        if not setups_data:
            return {}

        from ..rules.dsl_parser import parse_expr

        parsed: dict[str, Any] = {}
        for setup_id, setup_content in setups_data.items():
            converted = _convert_shorthand_conditions(setup_content)
            expr = parse_expr(converted)
            parsed[setup_id] = expr

        return parsed

    @staticmethod
    def _parse_actions(actions_data: dict | list) -> list:
        """
        Parse actions section (DSL format).

        Handles both shorthand dict format and full list format.
        """
        if not actions_data:
            return []

        from ..rules.dsl_parser import parse_blocks

        if isinstance(actions_data, dict):
            # Shorthand: {action_id: {all/any: [conditions]}}
            actions_list = []
            for action_id, action_content in actions_data.items():
                cases = []
                if isinstance(action_content, dict):
                    when_clause = _convert_shorthand_conditions(action_content)
                    action = action_id
                    cases.append({
                        "when": when_clause,
                        "emit": [{"action": action}],
                    })
                actions_list.append({
                    "id": action_id,
                    "cases": cases,
                })
            actions_data = actions_list

        return parse_blocks(actions_data)

    @staticmethod
    def _parse_risk_model(
        d: dict[str, Any],
        account: AccountConfig | None,
    ) -> RiskModel | None:
        """
        Parse risk model from risk: or risk_model: sections.

        Handles both full risk_model dict and YAML shorthand.
        """
        rm_dict = d.get("risk_model")
        risk_dict = d.get("risk", {})

        if rm_dict:
            return RiskModel.from_dict(rm_dict)

        if not risk_dict:
            return None

        max_position_pct = risk_dict.get("max_position_pct", 10.0)
        account_max_lev = account.max_leverage if account else 10.0

        # Parse stop_loss
        stop_loss_dict = risk_dict.get("stop_loss")
        stop_loss_pct = risk_dict.get("stop_loss_pct")
        trailing_config = None
        stop_loss_rule = None

        if stop_loss_dict and isinstance(stop_loss_dict, dict):
            sl_type_str = stop_loss_dict.get("type", "percent")
            sl_type = StopLossType(sl_type_str)

            if sl_type in (StopLossType.TRAILING_ATR, StopLossType.TRAILING_PCT):
                trailing_config = TrailingConfig(
                    atr_multiplier=float(stop_loss_dict.get("atr_multiplier", 2.0)),
                    atr_feature_id=stop_loss_dict.get("atr_feature_id"),
                    trail_pct=float(stop_loss_dict["trail_pct"]) if stop_loss_dict.get("trail_pct") else None,
                    activation_pct=float(stop_loss_dict.get("activation_pct", 0.0)),
                )
                sl_value = float(stop_loss_dict.get("atr_multiplier", stop_loss_dict.get("trail_pct", 2.0)))
            else:
                sl_value = float(stop_loss_dict.get("value", 2.0))

            stop_loss_rule = StopLossRule(
                type=sl_type,
                value=sl_value,
                atr_feature_id=stop_loss_dict.get("atr_feature_id"),
                buffer_pct=float(stop_loss_dict.get("buffer_pct", 0.0)),
            )
        elif stop_loss_pct is not None:
            stop_loss_rule = StopLossRule(
                type=StopLossType.PERCENT,
                value=float(stop_loss_pct),
            )

        # Parse take_profit
        take_profit_pct = risk_dict.get("take_profit_pct")
        take_profit_rule = None
        if take_profit_pct is not None:
            take_profit_rule = TakeProfitRule(
                type=TakeProfitType.PERCENT,
                value=float(take_profit_pct),
            )

        # Parse break_even config
        break_even_dict = risk_dict.get("break_even")
        break_even_config = None
        if break_even_dict and isinstance(break_even_dict, dict):
            break_even_config = BreakEvenConfig(
                activation_pct=float(break_even_dict.get("activation_pct", 1.0)),
                offset_pct=float(break_even_dict.get("offset_pct", 0.1)),
            )

        if stop_loss_rule is not None and take_profit_rule is not None:
            return RiskModel(
                stop_loss=stop_loss_rule,
                take_profit=take_profit_rule,
                sizing=SizingRule(
                    model=SizingModel.PERCENT_EQUITY,
                    value=float(max_position_pct),
                    max_leverage=float(account_max_lev),
                ),
                trailing_config=trailing_config,
                break_even_config=break_even_config,
            )

        return None

    @staticmethod
    def _parse_structures(
        structures_dict: dict[str, Any],
        exec_tf: str,
        tf_mapping: dict[str, str] | None = None,
    ) -> tuple[list[str], list[Feature]]:
        """
        Parse structures section.

        Returns:
            (structure_keys, structure_features)
        """
        if not structures_dict:
            return [], []

        VALID_TF_ROLES = {"exec", "low_tf", "med_tf", "high_tf"}
        structure_keys: list[str] = []
        structure_features: list[Feature] = []

        def _resolve_tf_for_role(role: str) -> str:
            """Resolve a role key to its concrete timeframe."""
            if role == "exec":
                return exec_tf
            if tf_mapping and role in tf_mapping:
                return tf_mapping[role]
            return exec_tf

        for tf_role, specs in structures_dict.items():
            if tf_role not in VALID_TF_ROLES:
                raise ValueError(
                    f"Invalid structures tf_role '{tf_role}'. "
                    f"Must be one of: {sorted(VALID_TF_ROLES)}. "
                    f"Example: structures: {{exec: [{{type: swing, key: swing, params: ...}}]}}"
                )

            if isinstance(specs, list):
                resolved_tf = _resolve_tf_for_role(tf_role)
                for spec in specs:
                    if isinstance(spec, dict) and "key" in spec:
                        if "type" not in spec:
                            raise ValueError(
                                f"Structure spec '{spec['key']}' missing required 'type' field. "
                                f"Example: {{type: swing, key: {spec['key']}, params: {{left: 5, right: 5}}}}"
                            )
                        structure_keys.append(spec["key"])
                        uses_raw = spec.get("uses", [])
                        if isinstance(uses_raw, str):
                            uses = (uses_raw,)
                        else:
                            uses = tuple(uses_raw) if uses_raw else ()
                        structure_features.append(Feature(
                            id=spec["key"],
                            tf=resolved_tf,
                            type=FeatureType.STRUCTURE,
                            structure_type=spec["type"],
                            params=spec.get("params", {}),
                            uses=uses,
                        ))
            elif isinstance(specs, dict):
                # high_tf: {"1h": [{type: swing, key: swing_1h}, ...]}
                for tf, tf_specs in specs.items():
                    if isinstance(tf_specs, list):
                        for spec in tf_specs:
                            if isinstance(spec, dict) and "key" in spec:
                                if "type" not in spec:
                                    raise ValueError(
                                        f"Structure spec '{spec['key']}' missing required 'type' field. "
                                        f"Example: {{type: swing, key: {spec['key']}, params: {{left: 3, right: 3}}}}"
                                    )
                                structure_keys.append(spec["key"])
                                uses_raw = spec.get("uses", [])
                                if isinstance(uses_raw, str):
                                    uses = (uses_raw,)
                                else:
                                    uses = tuple(uses_raw) if uses_raw else ()
                                structure_features.append(Feature(
                                    id=spec["key"],
                                    tf=tf,
                                    type=FeatureType.STRUCTURE,
                                    structure_type=spec["type"],
                                    params=spec.get("params", {}),
                                    uses=uses,
                                ))

        return structure_keys, structure_features

    # =========================================================================
    # from_dict() main method
    # =========================================================================

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Play":
        """Create from dict.

        Handles two formats:
        1. Internal format (from to_dict): features as list, symbol_universe, exec_tf
        2. YAML format: features as dict, symbol, tf
        """
        # Parse account config
        account_dict = d.get("account")
        account = AccountConfig.from_dict(account_dict) if account_dict else None

        # Parse timeframes
        exec_tf, tf_mapping, _ = cls._parse_timeframes(d)

        # Parse features
        features_raw = d.get("features", [])
        features = cls._parse_features(features_raw, exec_tf, tf_mapping)

        # Parse position policy
        pp_dict = d.get("position_policy", {})
        position_policy = PositionPolicy.from_dict(pp_dict) if pp_dict else PositionPolicy()

        # Parse setups (before actions, so setup refs can be validated)
        setups = cls._parse_setups(d.get("setups", {}))

        # Parse actions
        actions = cls._parse_actions(d.get("actions", {}))

        # Parse risk model
        risk_model = cls._parse_risk_model(d, account)

        # Parse variables
        variables = d.get("variables", {})

        # Parse structures
        structures_dict = d.get("structures", {})
        has_structures = bool(structures_dict)
        structure_keys, structure_features = cls._parse_structures(structures_dict, exec_tf, tf_mapping)

        # Combine indicator features with structure features
        if structure_features:
            features = tuple(list(features) + structure_features)

        # Handle symbol formats
        symbol_universe = d.get("symbol_universe", [])
        if not symbol_universe:
            symbol = d.get("symbol", "")
            if symbol:
                symbol_universe = [symbol]

        # Parse validation config (for synthetic validation plays)
        validation_dict = d.get("validation")
        validation = ValidationConfig.from_dict(validation_dict) if validation_dict else None

        # Parse entry order configuration
        entry_cfg = d.get("entry", {})
        entry_order_type = str(entry_cfg.get("order_type", "MARKET")).upper()
        limit_offset_pct = float(entry_cfg.get("limit_offset_pct", 0.0))
        time_in_force = str(entry_cfg.get("time_in_force", "GTC"))
        expire_after_bars = int(entry_cfg.get("expire_after_bars", 0))

        # Parse TP/SL order types from risk section
        risk_section = d.get("risk", {})
        tp_order_type = str(risk_section.get("tp_order_type", "Market"))
        sl_order_type = str(risk_section.get("sl_order_type", "Market"))

        return cls(
            id=d.get("id") or d.get("name", ""),
            version=d.get("version", ""),
            name=d.get("name"),
            description=d.get("description"),
            account=account,
            symbol_universe=tuple(symbol_universe),
            exec_tf=exec_tf,
            tf_mapping=tf_mapping,
            features=features,
            position_policy=position_policy,
            actions=actions,
            risk_model=risk_model,
            variables=variables,
            has_structures=has_structures,
            structure_keys=tuple(structure_keys),
            setups=setups,
            validation=validation,
            entry_order_type=entry_order_type,
            limit_offset_pct=limit_offset_pct,
            time_in_force=time_in_force,
            expire_after_bars=expire_after_bars,
            tp_order_type=tp_order_type,
            sl_order_type=sl_order_type,
        )


# =============================================================================
# Loader
# =============================================================================

# Default Play directory -- all plays live under plays/ (including plays/validation/)
_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
PLAYS_DIR = _PROJECT_ROOT / "plays"


def load_play(play_id: str, base_dir: Path | None = None) -> Play:
    """
    Load an Play from YAML file.

    Args:
        play_id: Identifier (filename without .yml)
        base_dir: Optional base directory

    Returns:
        Validated Play instance
    """
    # Search all known Play directories
    if base_dir:
        search_paths = [base_dir]
    else:
        search_paths = [PLAYS_DIR]

    path = None
    for search_path in search_paths:
        if not search_path.exists():
            continue
        for ext in (".yml", ".yaml"):
            # First try direct match (flat directories)
            candidate = search_path / f"{play_id}{ext}"
            if candidate.exists():
                path = candidate
                break
            # Then try recursive search (tier subdirectories)
            matches = list(search_path.rglob(f"{play_id}{ext}"))
            if matches:
                path = matches[0]
                break
        if path:
            break

    if not path:
        available = list_plays()
        raise FileNotFoundError(
            f"Play '{play_id}' not found in plays/. Available: {available[:20]}..."
        )

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not raw:
        raise ValueError(f"Empty or invalid YAML in {path}")

    return Play.from_dict(raw)


def list_plays(base_dir: Path | None = None, recursive: bool = True) -> list[str]:
    """List all available Play files from plays/ directory.

    Args:
        base_dir: Optional base directory to search
        recursive: If True, search subdirectories (default: True for tier support)

    Returns:
        Sorted list of Play IDs (filenames without extension)
    """
    if base_dir:
        search_paths = [base_dir]
    else:
        search_paths = [PLAYS_DIR]

    cards = set()
    for search_path in search_paths:
        if not search_path.exists():
            continue
        for ext in ("*.yml", "*.yaml"):
            # Use rglob for recursive search (tier subdirectories)
            glob_fn = search_path.rglob if recursive else search_path.glob
            for path in glob_fn(ext):
                if path.stem.startswith("_") and not path.stem.startswith("_V"):
                    continue
                cards.add(path.stem)

    return sorted(cards)


@dataclass
class PlayInfo:
    """Lightweight play metadata for browsing without full parse."""
    id: str
    name: str
    description: str
    symbol: str
    exec_tf: str
    direction: str
    path: Path


def list_play_dirs(exclude_validation: bool = True) -> dict[str, list[Path]]:
    """List play directories grouped by folder.

    Args:
        exclude_validation: If True (default), skip plays/validation/ entirely.

    Returns:
        Dict mapping folder label to sorted list of play file paths.
        Root-level plays use "." as key.
    """
    if not PLAYS_DIR.exists():
        return {}

    groups: dict[str, list[Path]] = {}

    for ext in ("*.yml", "*.yaml"):
        for path in PLAYS_DIR.rglob(ext):
            if path.stem.startswith("_") and not path.stem.startswith("_V"):
                continue

            # Relative path from plays/ root
            rel = path.relative_to(PLAYS_DIR)
            parts = rel.parts

            # Skip validation tree
            if exclude_validation and len(parts) > 1 and parts[0] == "validation":
                continue

            # Group key = parent folder relative to plays/ ("." for root)
            folder = str(rel.parent) if len(parts) > 1 else "."
            groups.setdefault(folder, []).append(path)

    # Sort each group
    for key in groups:
        groups[key] = sorted(groups[key], key=lambda p: p.stem)

    return groups


def peek_play_yaml(path: Path) -> PlayInfo:
    """Read just the header metadata from a play YAML without full parsing.

    Fast -- only reads the YAML dict, does not construct a Play object.
    """
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not raw or not isinstance(raw, dict):
        return PlayInfo(
            id=path.stem, name=path.stem, description="(invalid YAML)",
            symbol="?", exec_tf="?", direction="?", path=path,
        )

    # Determine direction from actions
    actions = raw.get("actions", {})
    has_long = "entry_long" in actions
    has_short = "entry_short" in actions
    if has_long and has_short:
        direction = "long/short"
    elif has_long:
        direction = "long"
    elif has_short:
        direction = "short"
    else:
        direction = "?"

    # Resolve exec TF
    tfs = raw.get("timeframes", {})
    exec_pointer = tfs.get("exec", "low_tf")
    exec_tf = tfs.get(exec_pointer, tfs.get("low_tf", "?"))

    symbol = raw.get("symbol", "?")
    if isinstance(symbol, list):
        symbol = symbol[0] if symbol else "?"

    return PlayInfo(
        id=raw.get("name", path.stem),
        name=raw.get("name", path.stem),
        description=(raw.get("description") or "").strip().split("\n")[0][:80],
        symbol=symbol,
        exec_tf=exec_tf,
        direction=direction,
        path=path,
    )
