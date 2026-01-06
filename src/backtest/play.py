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
- Any timeframe: No fixed exec/mtf/htf roles - use any TF
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
import yaml

from .feature_registry import Feature, FeatureType, FeatureRegistry, InputSource

# TYPE_CHECKING block for Block import to avoid circular import
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .rules.strategy_blocks import Block


# =============================================================================
# Fee Model
# =============================================================================

@dataclass(frozen=True)
class FeeModel:
    """
    Fee model configuration.

    Attributes:
        taker_bps: Taker fee in basis points (e.g., 6.0 = 0.06%)
        maker_bps: Maker fee in basis points (e.g., 2.0 = 0.02%)
    """
    taker_bps: float
    maker_bps: float = 0.0

    def __post_init__(self):
        """Validate fee model."""
        if self.taker_bps < 0:
            raise ValueError(f"taker_bps cannot be negative. Got: {self.taker_bps}")
        if self.maker_bps < 0:
            raise ValueError(f"maker_bps cannot be negative. Got: {self.maker_bps}")

    @property
    def taker_rate(self) -> float:
        """Get taker fee rate as decimal (e.g., 0.0006 for 6 bps)."""
        return self.taker_bps / 10000.0

    @property
    def maker_rate(self) -> float:
        """Get maker fee rate as decimal."""
        return self.maker_bps / 10000.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "taker_bps": self.taker_bps,
            "maker_bps": self.maker_bps,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "FeeModel":
        """Create from dict."""
        return cls(
            taker_bps=float(d.get("taker_bps", 0.0)),
            maker_bps=float(d.get("maker_bps", 0.0)),
        )


# =============================================================================
# Account Configuration
# =============================================================================

@dataclass(frozen=True)
class AccountConfig:
    """
    Account / capital configuration for backtest runtime.

    Required fields (no defaults - must be explicitly provided):
        starting_equity_usdt: Starting capital in USDT
        max_leverage: Maximum leverage allowed
    """
    starting_equity_usdt: float
    max_leverage: float

    margin_mode: str = "isolated_usdt"
    fee_model: FeeModel | None = None
    slippage_bps: float | None = None
    min_trade_notional_usdt: float | None = None
    max_notional_usdt: float | None = None
    max_margin_usdt: float | None = None
    maintenance_margin_rate: float | None = None

    def __post_init__(self):
        """Validate account config."""
        if self.starting_equity_usdt <= 0:
            raise ValueError(f"starting_equity_usdt must be positive. Got: {self.starting_equity_usdt}")
        if self.max_leverage <= 0:
            raise ValueError(f"max_leverage must be positive. Got: {self.max_leverage}")
        if self.margin_mode not in ("isolated_usdt", "isolated"):
            raise ValueError(f"margin_mode must be 'isolated_usdt' or 'isolated'. Got: {self.margin_mode}")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        result = {
            "starting_equity_usdt": self.starting_equity_usdt,
            "max_leverage": self.max_leverage,
            "margin_mode": self.margin_mode,
        }
        if self.fee_model:
            result["fee_model"] = self.fee_model.to_dict()
        if self.slippage_bps is not None:
            result["slippage_bps"] = self.slippage_bps
        if self.min_trade_notional_usdt is not None:
            result["min_trade_notional_usdt"] = self.min_trade_notional_usdt
        if self.max_notional_usdt is not None:
            result["max_notional_usdt"] = self.max_notional_usdt
        if self.max_margin_usdt is not None:
            result["max_margin_usdt"] = self.max_margin_usdt
        if self.maintenance_margin_rate is not None:
            result["maintenance_margin_rate"] = self.maintenance_margin_rate
        return result

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AccountConfig":
        """Create from dict."""
        if "starting_equity_usdt" not in d:
            raise ValueError("AccountConfig requires 'starting_equity_usdt'")
        if "max_leverage" not in d:
            raise ValueError("AccountConfig requires 'max_leverage'")

        fee_model = None
        if "fee_model" in d and d["fee_model"]:
            fee_model = FeeModel.from_dict(d["fee_model"])

        return cls(
            starting_equity_usdt=float(d["starting_equity_usdt"]),
            max_leverage=float(d["max_leverage"]),
            margin_mode=d.get("margin_mode", "isolated_usdt"),
            fee_model=fee_model,
            slippage_bps=float(d["slippage_bps"]) if "slippage_bps" in d else None,
            min_trade_notional_usdt=float(d["min_trade_notional_usdt"]) if "min_trade_notional_usdt" in d else None,
            max_notional_usdt=float(d["max_notional_usdt"]) if "max_notional_usdt" in d else None,
            max_margin_usdt=float(d["max_margin_usdt"]) if "max_margin_usdt" in d else None,
            maintenance_margin_rate=float(d["maintenance_margin_rate"]) if "maintenance_margin_rate" in d else None,
        )


# =============================================================================
# Position Policy
# =============================================================================

class PositionMode(str, Enum):
    """Position direction policy."""
    LONG_ONLY = "long_only"
    SHORT_ONLY = "short_only"
    LONG_SHORT = "long_short"


@dataclass(frozen=True)
class PositionPolicy:
    """Position policy configuration."""
    mode: PositionMode = PositionMode.LONG_ONLY
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

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "mode": self.mode.value,
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
            max_positions_per_symbol=d.get("max_positions_per_symbol", 1),
            allow_flip=d.get("allow_flip", False),
            allow_scale_in=d.get("allow_scale_in", False),
            allow_scale_out=d.get("allow_scale_out", False),
        )


# =============================================================================
# Risk Model
# =============================================================================

class StopLossType(str, Enum):
    """Stop loss calculation method."""
    ATR_MULTIPLE = "atr_multiple"
    PERCENT = "percent"
    STRUCTURE = "structure"
    FIXED_POINTS = "fixed_points"


class TakeProfitType(str, Enum):
    """Take profit calculation method."""
    RR_RATIO = "rr_ratio"
    ATR_MULTIPLE = "atr_multiple"
    PERCENT = "percent"
    FIXED_POINTS = "fixed_points"


class SizingModel(str, Enum):
    """Position sizing method."""
    PERCENT_EQUITY = "percent_equity"
    FIXED_USDT = "fixed_usdt"
    RISK_BASED = "risk_based"


@dataclass(frozen=True)
class StopLossRule:
    """Stop loss rule specification."""
    type: StopLossType
    value: float
    atr_feature_id: str | None = None  # Feature ID for ATR (if type=atr_multiple)
    buffer_pct: float = 0.0

    def __post_init__(self):
        """Validate rule."""
        if self.type == StopLossType.ATR_MULTIPLE and not self.atr_feature_id:
            raise ValueError("atr_feature_id is required when type=atr_multiple")
        if self.value <= 0:
            raise ValueError(f"Stop loss value must be positive. Got: {self.value}")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        result = {
            "type": self.type.value,
            "value": self.value,
            "buffer_pct": self.buffer_pct,
        }
        if self.atr_feature_id:
            result["atr_feature_id"] = self.atr_feature_id
        return result

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "StopLossRule":
        """Create from dict."""
        return cls(
            type=StopLossType(d["type"]),
            value=float(d["value"]),
            atr_feature_id=d.get("atr_feature_id") or d.get("atr_key"),  # Support old key name
            buffer_pct=float(d.get("buffer_pct", 0.0)),
        )


@dataclass(frozen=True)
class TakeProfitRule:
    """Take profit rule specification."""
    type: TakeProfitType
    value: float
    atr_feature_id: str | None = None

    def __post_init__(self):
        """Validate rule."""
        if self.type == TakeProfitType.ATR_MULTIPLE and not self.atr_feature_id:
            raise ValueError("atr_feature_id is required when type=atr_multiple")
        if self.value <= 0:
            raise ValueError(f"Take profit value must be positive. Got: {self.value}")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        result = {
            "type": self.type.value,
            "value": self.value,
        }
        if self.atr_feature_id:
            result["atr_feature_id"] = self.atr_feature_id
        return result

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TakeProfitRule":
        """Create from dict."""
        return cls(
            type=TakeProfitType(d["type"]),
            value=float(d["value"]),
            atr_feature_id=d.get("atr_feature_id") or d.get("atr_key"),
        )


@dataclass(frozen=True)
class SizingRule:
    """Position sizing rule specification."""
    model: SizingModel
    value: float
    max_leverage: float = 1.0

    def __post_init__(self):
        """Validate rule."""
        if self.value <= 0:
            raise ValueError(f"Sizing value must be positive. Got: {self.value}")
        if self.max_leverage <= 0:
            raise ValueError(f"max_leverage must be positive. Got: {self.max_leverage}")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "model": self.model.value,
            "value": self.value,
            "max_leverage": self.max_leverage,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SizingRule":
        """Create from dict."""
        return cls(
            model=SizingModel(d["model"]),
            value=float(d["value"]),
            max_leverage=float(d.get("max_leverage", 1.0)),
        )


@dataclass(frozen=True)
class RiskModel:
    """Complete risk model specification."""
    stop_loss: StopLossRule
    take_profit: TakeProfitRule
    sizing: SizingRule

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "stop_loss": self.stop_loss.to_dict(),
            "take_profit": self.take_profit.to_dict(),
            "sizing": self.sizing.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RiskModel":
        """Create from dict."""
        return cls(
            stop_loss=StopLossRule.from_dict(d["stop_loss"]),
            take_profit=TakeProfitRule.from_dict(d["take_profit"]),
            sizing=SizingRule.from_dict(d["sizing"]),
        )


# =============================================================================
# Shorthand Conversion Helpers
# =============================================================================

def _convert_shorthand_condition(cond: list) -> dict:
    """
    Convert shorthand condition ["a", ">", "b"] to full DSL format.

    Supports:
        ["a", ">", "b"]           -> lhs: a, op: gt, rhs: b
        ["a", "cross_above", "b"] -> lhs: a, op: cross_above, rhs: b
        ["a", "between", [lo, hi]] -> lhs: a, op: between, rhs: {low: lo, high: hi}
        ["a", "near_pct", "b", tol] -> lhs: a, op: near_pct, rhs: b, tolerance: tol
        ["a", "==", 1]            -> lhs: a, op: eq, rhs: 1
        ["a", "in", [1, 2]]       -> lhs: a, op: in, rhs: [1, 2]
    """
    if len(cond) < 3:
        raise ValueError(f"Condition must have at least 3 elements: {cond}")

    lhs_raw, op_raw, rhs_raw = cond[0], cond[1], cond[2]

    # Map operator symbols to DSL names
    op_map = {
        ">": "gt", "<": "lt", ">=": "gte", "<=": "lte",
        "==": "eq", "!=": "neq", "=": "eq",
        "cross_above": "cross_above", "cross_below": "cross_below",
        "between": "between", "near_pct": "near_pct", "near_abs": "near_abs",
        "in": "in",
    }
    op = op_map.get(op_raw, op_raw)

    # Build lhs
    if isinstance(lhs_raw, str):
        if "." in lhs_raw:
            # Structure field: "swing.high_level"
            parts = lhs_raw.split(".", 1)
            lhs = {"feature_id": parts[0], "field": parts[1]}
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
            rhs = {"feature_id": parts[0], "field": parts[1]}
        else:
            rhs = {"feature_id": rhs_raw}
    else:
        rhs = rhs_raw  # Constant value

    result = {"lhs": lhs, "op": op, "rhs": rhs}

    # Handle tolerance for near_* operators (4th element)
    if len(cond) > 3 and op in ("near_pct", "near_abs"):
        result["tolerance"] = cond[3]

    return result


def _convert_shorthand_conditions(block_content: dict) -> dict:
    """
    Convert shorthand block content to full DSL "when" clause.

    Input formats:
        {"all": [conditions...]}
        {"any": [conditions...]}
        Single condition list

    Output:
        Full DSL when clause dict.
    """
    if "all" in block_content:
        conditions = block_content["all"]
        return {"all": [_convert_shorthand_condition(c) for c in conditions]}
    elif "any" in block_content:
        conditions = block_content["any"]
        return {"any": [_convert_shorthand_condition(c) for c in conditions]}
    elif "not" in block_content:
        inner = block_content["not"]
        if isinstance(inner, dict):
            return {"not": _convert_shorthand_conditions(inner)}
        elif isinstance(inner, list):
            return {"not": _convert_shorthand_condition(inner)}
    elif "holds_for" in block_content:
        hf = block_content["holds_for"]
        return {
            "holds_for": {
                "bars": hf["bars"],
                "condition": _convert_shorthand_conditions(hf.get("condition", {})),
            }
        }
    elif "occurred_within" in block_content:
        ow = block_content["occurred_within"]
        return {
            "occurred_within": {
                "bars": ow["bars"],
                "condition": _convert_shorthand_conditions(ow.get("condition", {})),
            }
        }
    elif "count_true" in block_content:
        ct = block_content["count_true"]
        return {
            "count_true": {
                "bars": ct["bars"],
                "min_true": ct["min_true"],
                "condition": _convert_shorthand_conditions(ct.get("condition", {})),
            }
        }

    # Fallback: return as-is (might already be full format)
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
    - execution_tf: The timeframe for bar-by-bar stepping
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
    execution_tf: str = ""

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

        if not self.execution_tf:
            errors.append("execution_tf is required")

        # Allow structure-only Plays (empty features if structures exist)
        if not self.features and not self.has_structures:
            errors.append("features list is required (at least one feature or structure)")

        # Must have actions for signal generation
        if not self.actions:
            errors.append("actions is required for signal generation")

        # Validate operator/type compatibility in actions
        # Only run if we have features and actions (otherwise skip - above errors cover it)
        if self.features and self.actions:
            type_errors = self._validate_action_types()
            errors.extend(type_errors)

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
        from .rules.dsl_parser import validate_blocks_types

        try:
            registry = self.feature_registry
            return validate_blocks_types(self.actions, registry.get_output_type)
        except Exception:
            # If registry building fails, skip type validation
            # (other validation will catch the root cause)
            return []

    @property
    def feature_registry(self) -> FeatureRegistry:
        """Get or build the feature registry."""
        if self._registry is None:
            self._registry = FeatureRegistry.from_features(
                execution_tf=self.execution_tf,
                features=list(self.features),
            )
            self._registry.expand_indicator_outputs()
        return self._registry

    @property
    def exec_tf(self) -> str:
        """Get execution timeframe (alias for compatibility)."""
        return self.execution_tf

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
            "execution_tf": self.execution_tf,
            "features": [f.to_dict() for f in self.features],
            "position_policy": self.position_policy.to_dict(),
            "risk_model": self.risk_model.to_dict() if self.risk_model else None,
        }
        if self.account:
            result["account"] = self.account.to_dict()
        if self.variables:
            result["variables"] = dict(self.variables)
        # Serialize actions
        if self.actions:
            result["actions"] = [b.to_dict() for b in self.actions]
        return result

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Play":
        """Create from dict.

        Handles two formats:
        1. Internal format (from to_dict): features as list, symbol_universe, execution_tf
        2. YAML format: features as dict, symbol, tf
        """
        # Parse account config
        account_dict = d.get("account")
        account = AccountConfig.from_dict(account_dict) if account_dict else None

        # Parse features - handle both dict (YAML) and list (internal) formats
        features_raw = d.get("features", [])
        execution_tf = d.get("execution_tf") or d.get("tf", "")

        if isinstance(features_raw, dict):
            # YAML format: {feature_id: {indicator: ..., params: ...}}
            # Note: Feature and FeatureType are imported at module level (line 23)
            from .indicator_registry import get_registry
            registry = get_registry()

            features_list = []
            for feature_id, spec in features_raw.items():
                indicator_type = spec.get("indicator", "")
                params = spec.get("params", {})
                feature_tf = spec.get("tf", execution_tf)

                # Get output keys from registry
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
                    output_keys=output_keys,
                )
                features_list.append(feature)
            features = tuple(features_list)
        else:
            # Internal format: list of Feature dicts
            features = tuple(Feature.from_dict(f) for f in features_raw)

        # Parse position policy
        pp_dict = d.get("position_policy", {})
        position_policy = PositionPolicy.from_dict(pp_dict) if pp_dict else PositionPolicy()

        # Parse actions (DSL format) - handle both shorthand and full formats
        # Support both 'actions' (new) and 'blocks' (legacy) field names
        actions_data = d.get("actions") or d.get("blocks", {})
        if actions_data:
            from .rules.dsl_parser import parse_blocks

            # Convert shorthand dict format to list format if needed
            if isinstance(actions_data, dict):
                # Shorthand: {action_id: {all/any: [conditions]}}
                actions_list = []
                for action_id, action_content in actions_data.items():
                    # Convert shorthand conditions to full format
                    cases = []
                    if isinstance(action_content, dict):
                        # Build the "when" clause from the action content
                        when_clause = _convert_shorthand_conditions(action_content)
                        # Infer action from action_id
                        action = action_id  # e.g., "entry_long", "exit_long"
                        cases.append({
                            "when": when_clause,
                            "emit": [{"action": action}],
                        })
                    actions_list.append({
                        "id": action_id,
                        "cases": cases,
                    })
                actions_data = actions_list

            actions = parse_blocks(actions_data)
        else:
            actions = []

        # Parse risk model - handle both formats
        rm_dict = d.get("risk_model")
        risk_dict = d.get("risk", {})
        if rm_dict:
            risk_model = RiskModel.from_dict(rm_dict)
        elif risk_dict:
            # YAML shorthand: risk.stop_loss_pct, risk.take_profit_pct, max_position_pct
            # Convert to proper RiskModel
            stop_loss_pct = risk_dict.get("stop_loss_pct")
            take_profit_pct = risk_dict.get("take_profit_pct")
            max_position_pct = risk_dict.get("max_position_pct", 10.0)

            if stop_loss_pct is not None and take_profit_pct is not None:
                # Get max_leverage from account config (defaults to 10.0 if not set)
                account_max_lev = account.max_leverage if account else 10.0
                risk_model = RiskModel(
                    stop_loss=StopLossRule(
                        type=StopLossType.PERCENT,
                        value=float(stop_loss_pct),
                    ),
                    take_profit=TakeProfitRule(
                        type=TakeProfitType.PERCENT,
                        value=float(take_profit_pct),
                    ),
                    sizing=SizingRule(
                        model=SizingModel.PERCENT_EQUITY,
                        value=float(max_position_pct),
                        max_leverage=float(account_max_lev),
                    ),
                )
            else:
                risk_model = None
        else:
            risk_model = None

        # Parse variables
        variables = d.get("variables", {})

        # Check if structures are defined (allows structure-only Plays)
        structures_dict = d.get("structures", {})
        has_structures = bool(structures_dict)

        # Extract structure keys for auto-resolving references
        structure_keys: list[str] = []
        if has_structures:
            # structures: {exec: [...], htf: {...}}
            for tf_role, specs in structures_dict.items():
                if isinstance(specs, list):
                    # exec: [{type: swing, key: swing}, ...]
                    for spec in specs:
                        if isinstance(spec, dict) and "key" in spec:
                            structure_keys.append(spec["key"])
                elif isinstance(specs, dict):
                    # htf: {"1h": [{type: swing, key: swing_1h}, ...]}
                    for tf, tf_specs in specs.items():
                        if isinstance(tf_specs, list):
                            for spec in tf_specs:
                                if isinstance(spec, dict) and "key" in spec:
                                    structure_keys.append(spec["key"])

        # Handle symbol formats
        symbol_universe = d.get("symbol_universe", [])
        if not symbol_universe:
            symbol = d.get("symbol", "")
            if symbol:
                symbol_universe = [symbol]

        return cls(
            id=d.get("id") or d.get("name", ""),
            version=d.get("version", ""),
            name=d.get("name"),
            description=d.get("description"),
            account=account,
            symbol_universe=tuple(symbol_universe),
            execution_tf=execution_tf,
            features=features,
            position_policy=position_policy,
            actions=actions,
            risk_model=risk_model,
            variables=variables,
            has_structures=has_structures,
            structure_keys=tuple(structure_keys),
        )


# =============================================================================
# Loader
# =============================================================================

PLAYS_DIR = Path(__file__).parent.parent.parent / "strategies" / "plays"


def load_play(play_id: str, base_dir: Path | None = None) -> Play:
    """
    Load an Play from YAML file.

    Args:
        play_id: Identifier (filename without .yml)
        base_dir: Optional base directory

    Returns:
        Validated Play instance
    """
    search_dir = base_dir or PLAYS_DIR
    search_paths = [
        search_dir,
        search_dir / "_validation",
        search_dir / "_stress_test",
        search_dir / "strategies",
    ]

    path = None
    for search_path in search_paths:
        for ext in (".yml", ".yaml"):
            candidate = search_path / f"{play_id}{ext}"
            if candidate.exists():
                path = candidate
                break
        if path:
            break

    if not path:
        available = list_plays(search_dir)
        raise FileNotFoundError(
            f"Play '{play_id}' not found in {search_dir}. Available: {available}"
        )

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not raw:
        raise ValueError(f"Empty or invalid YAML in {path}")

    return Play.from_dict(raw)


def list_plays(base_dir: Path | None = None) -> list[str]:
    """List all available Play files."""
    search_dir = base_dir or PLAYS_DIR

    if not search_dir.exists():
        return []

    search_paths = [
        search_dir,
        search_dir / "_validation",
        search_dir / "_stress_test",
        search_dir / "strategies",
    ]

    cards = set()
    for search_path in search_paths:
        if not search_path.exists():
            continue
        for ext in ("*.yml", "*.yaml"):
            for path in search_path.glob(ext):
                if path.stem.startswith("_") and not path.stem.startswith("_V"):
                    continue
                cards.add(path.stem)

    return sorted(cards)
