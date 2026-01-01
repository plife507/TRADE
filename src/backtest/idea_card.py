"""
IdeaCard: Declarative strategy specification.

An IdeaCard is a self-contained, declarative configuration that defines:
- What indicators/features the strategy needs (FeatureSpecs per TF)
- What position policy to follow (long_only, short_only, long_short)
- Entry/exit rules (signal logic)
- Risk model (stop loss, take profit, sizing)

Design principles:
- Explicit over implicit: No silent defaults
- Fail-fast: Validation at load time
- Compatible with Strategy Factory: Machine-readable, composable
- Decoupled from execution: IdeaCard declares intent, engine executes

The IdeaCard replaces ad-hoc strategy configuration with a structured,
validated specification that the backtest engine can consume directly.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any
import yaml

from .features.feature_spec import FeatureSpec, FeatureSpecSet


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
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "taker_bps": self.taker_bps,
            "maker_bps": self.maker_bps,
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "FeeModel":
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
    
    This configuration carries ALL runtime variables that were previously
    hard-coded as defaults. No defaults are allowed for required fields.
    
    Required fields (no defaults - must be explicitly provided):
        starting_equity_usdt: Starting capital in USDT
        max_leverage: Maximum leverage allowed
        
    Optional fields:
        margin_mode: Margin mode (default: "isolated_usdt")
        fee_model: Fee configuration (taker_bps, maker_bps)
        slippage_bps: Slippage in basis points
        min_trade_notional_usdt: Minimum trade size in USDT
        max_notional_usdt: Maximum single trade notional
        max_margin_usdt: Maximum margin to use
    """
    # Required fields (no defaults)
    starting_equity_usdt: float
    max_leverage: float
    
    # Optional fields with sensible defaults
    margin_mode: str = "isolated_usdt"
    fee_model: Optional[FeeModel] = None
    slippage_bps: Optional[float] = None
    min_trade_notional_usdt: Optional[float] = None
    max_notional_usdt: Optional[float] = None
    max_margin_usdt: Optional[float] = None
    maintenance_margin_rate: Optional[float] = None  # e.g., 0.005 = 0.5% (Bybit lowest tier)

    def __post_init__(self):
        """Validate account config."""
        if self.starting_equity_usdt <= 0:
            raise ValueError(
                f"starting_equity_usdt must be positive. Got: {self.starting_equity_usdt}"
            )
        if self.max_leverage <= 0:
            raise ValueError(
                f"max_leverage must be positive. Got: {self.max_leverage}"
            )
        if self.margin_mode not in ("isolated_usdt", "isolated"):
            raise ValueError(
                f"margin_mode must be 'isolated_usdt' or 'isolated' (this simulator version). "
                f"Got: {self.margin_mode}"
            )
        if self.slippage_bps is not None and self.slippage_bps < 0:
            raise ValueError(f"slippage_bps cannot be negative. Got: {self.slippage_bps}")
        if self.min_trade_notional_usdt is not None and self.min_trade_notional_usdt < 0:
            raise ValueError(
                f"min_trade_notional_usdt cannot be negative. Got: {self.min_trade_notional_usdt}"
            )
        if self.maintenance_margin_rate is not None:
            if self.maintenance_margin_rate <= 0 or self.maintenance_margin_rate >= 1:
                raise ValueError(
                    f"maintenance_margin_rate must be between 0 and 1 (e.g., 0.005 = 0.5%). "
                    f"Got: {self.maintenance_margin_rate}"
                )
    
    def to_dict(self) -> Dict[str, Any]:
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
    def from_dict(cls, d: Dict[str, Any]) -> "AccountConfig":
        """
        Create from dict.
        
        Raises:
            ValueError: If required fields are missing
        """
        # Required fields - fail loud if missing
        if "starting_equity_usdt" not in d:
            raise ValueError(
                "AccountConfig requires 'starting_equity_usdt'. "
                "IdeaCard must specify account.starting_equity_usdt (no default)."
            )
        if "max_leverage" not in d:
            raise ValueError(
                "AccountConfig requires 'max_leverage'. "
                "IdeaCard must specify account.max_leverage (no default)."
            )
        
        # Parse fee model if present
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
# Position Policy Enums
# =============================================================================

class PositionMode(str, Enum):
    """
    Position direction policy.
    
    Determines which directions the strategy is allowed to trade.
    """
    LONG_ONLY = "long_only"      # Only long positions allowed
    SHORT_ONLY = "short_only"    # Only short positions allowed
    LONG_SHORT = "long_short"    # Both directions allowed


# =============================================================================
# Position Policy
# =============================================================================

@dataclass(frozen=True)
class PositionPolicy:
    """
    Position policy configuration.
    
    Defines the constraints on position management:
    - mode: Which directions are allowed (long_only, short_only, long_short)
    - max_positions_per_symbol: Maximum concurrent positions (currently always 1)
    - allow_flip: Can flip from long to short directly (or vice versa)
    - allow_scale_in: Can add to existing positions
    - allow_scale_out: Can partially close positions
    
    Note: Current simulator only supports single position per symbol (oneway mode).
    Scale-in and scale-out are placeholders for future versions.
    """
    mode: PositionMode = PositionMode.LONG_ONLY
    max_positions_per_symbol: int = 1
    allow_flip: bool = False
    allow_scale_in: bool = False
    allow_scale_out: bool = False
    
    def __post_init__(self):
        """Validate policy."""
        if self.max_positions_per_symbol != 1:
            raise ValueError(
                f"max_positions_per_symbol must be 1 (this simulator version supports single position only). "
                f"Got: {self.max_positions_per_symbol}"
            )
        if self.allow_scale_in:
            raise ValueError(
                "allow_scale_in=True is not supported in this simulator version"
            )
        if self.allow_scale_out:
            raise ValueError(
                "allow_scale_out=True is not supported in this simulator version"
            )
    
    def allows_long(self) -> bool:
        """Check if long positions are allowed."""
        return self.mode in (PositionMode.LONG_ONLY, PositionMode.LONG_SHORT)
    
    def allows_short(self) -> bool:
        """Check if short positions are allowed."""
        return self.mode in (PositionMode.SHORT_ONLY, PositionMode.LONG_SHORT)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "mode": self.mode.value,
            "max_positions_per_symbol": self.max_positions_per_symbol,
            "allow_flip": self.allow_flip,
            "allow_scale_in": self.allow_scale_in,
            "allow_scale_out": self.allow_scale_out,
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PositionPolicy":
        """Create from dict."""
        mode_str = d.get("mode", "long_only")
        return cls(
            mode=PositionMode(mode_str),
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
    ATR_MULTIPLE = "atr_multiple"       # SL = entry ± ATR * multiplier
    PERCENT = "percent"                 # SL = entry ± entry * percent
    STRUCTURE = "structure"             # SL = recent swing low/high
    FIXED_POINTS = "fixed_points"       # SL = entry ± fixed points


class TakeProfitType(str, Enum):
    """Take profit calculation method."""
    RR_RATIO = "rr_ratio"               # TP based on risk:reward ratio
    ATR_MULTIPLE = "atr_multiple"       # TP = entry ± ATR * multiplier
    PERCENT = "percent"                 # TP = entry ± entry * percent
    FIXED_POINTS = "fixed_points"       # TP = entry ± fixed points


class SizingModel(str, Enum):
    """Position sizing method."""
    PERCENT_EQUITY = "percent_equity"   # Size based on % of equity
    FIXED_USDT = "fixed_usdt"           # Fixed USDT amount
    RISK_BASED = "risk_based"           # Size based on SL distance + risk %


@dataclass(frozen=True)
class StopLossRule:
    """
    Stop loss rule specification.
    
    Attributes:
        type: Calculation method (atr_multiple, percent, structure, fixed_points)
        value: Parameter value (multiplier, percent, points, or lookback bars)
        atr_key: Indicator key for ATR (if type=atr_multiple)
        buffer_pct: Optional buffer percent added to SL
    """
    type: StopLossType
    value: float
    atr_key: Optional[str] = None
    buffer_pct: float = 0.0
    
    def __post_init__(self):
        """Validate rule."""
        if self.type == StopLossType.ATR_MULTIPLE and not self.atr_key:
            raise ValueError("atr_key is required when type=atr_multiple")
        if self.value <= 0:
            raise ValueError(f"Stop loss value must be positive. Got: {self.value}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "type": self.type.value,
            "value": self.value,
            "atr_key": self.atr_key,
            "buffer_pct": self.buffer_pct,
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "StopLossRule":
        """Create from dict."""
        return cls(
            type=StopLossType(d["type"]),
            value=float(d["value"]),
            atr_key=d.get("atr_key"),
            buffer_pct=float(d.get("buffer_pct", 0.0)),
        )


@dataclass(frozen=True)
class TakeProfitRule:
    """
    Take profit rule specification.
    
    Attributes:
        type: Calculation method (rr_ratio, atr_multiple, percent, fixed_points)
        value: Parameter value (ratio, multiplier, percent, or points)
        atr_key: Indicator key for ATR (if type=atr_multiple)
    """
    type: TakeProfitType
    value: float
    atr_key: Optional[str] = None
    
    def __post_init__(self):
        """Validate rule."""
        if self.type == TakeProfitType.ATR_MULTIPLE and not self.atr_key:
            raise ValueError("atr_key is required when type=atr_multiple")
        if self.value <= 0:
            raise ValueError(f"Take profit value must be positive. Got: {self.value}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "type": self.type.value,
            "value": self.value,
            "atr_key": self.atr_key,
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TakeProfitRule":
        """Create from dict."""
        return cls(
            type=TakeProfitType(d["type"]),
            value=float(d["value"]),
            atr_key=d.get("atr_key"),
        )


@dataclass(frozen=True)
class SizingRule:
    """
    Position sizing rule specification.
    
    Attributes:
        model: Sizing method (percent_equity, fixed_usdt, risk_based)
        value: Parameter value (percent, USDT amount, or risk percent)
        max_leverage: Maximum leverage (capped regardless of sizing)
    """
    model: SizingModel
    value: float
    max_leverage: float = 1.0
    
    def __post_init__(self):
        """Validate rule."""
        if self.value <= 0:
            raise ValueError(f"Sizing value must be positive. Got: {self.value}")
        if self.max_leverage <= 0:
            raise ValueError(f"max_leverage must be positive. Got: {self.max_leverage}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "model": self.model.value,
            "value": self.value,
            "max_leverage": self.max_leverage,
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SizingRule":
        """Create from dict."""
        return cls(
            model=SizingModel(d["model"]),
            value=float(d["value"]),
            max_leverage=float(d.get("max_leverage", 1.0)),
        )


@dataclass(frozen=True)
class RiskModel:
    """
    Complete risk model specification.
    
    Combines stop loss, take profit, and sizing rules.
    """
    stop_loss: StopLossRule
    take_profit: TakeProfitRule
    sizing: SizingRule
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "stop_loss": self.stop_loss.to_dict(),
            "take_profit": self.take_profit.to_dict(),
            "sizing": self.sizing.to_dict(),
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RiskModel":
        """Create from dict."""
        return cls(
            stop_loss=StopLossRule.from_dict(d["stop_loss"]),
            take_profit=TakeProfitRule.from_dict(d["take_profit"]),
            sizing=SizingRule.from_dict(d["sizing"]),
        )


# =============================================================================
# Signal Rules
# =============================================================================

class RuleOperator(str, Enum):
    """Comparison operator for rules."""
    GT = "gt"           # Greater than
    GTE = "gte"         # Greater than or equal
    LT = "lt"           # Less than
    LTE = "lte"         # Less than or equal
    EQ = "eq"           # Equal
    CROSS_ABOVE = "cross_above"   # Value crosses above threshold
    CROSS_BELOW = "cross_below"   # Value crosses below threshold


@dataclass(frozen=True)
class Condition:
    """
    A single condition in a signal rule.
    
    Attributes:
        indicator_key: Key of the indicator to check (e.g., "ema_fast", "rsi_14")
        operator: Comparison operator (gt, lt, cross_above, etc.)
        value: Threshold value OR another indicator key (for crossovers)
        is_indicator_comparison: If True, value is another indicator key
        tf: Timeframe context for the indicator ("exec", "htf", "mtf")
        prev_offset: Bar offset for previous value (used in cross_above/cross_below)
    """
    indicator_key: str
    operator: RuleOperator
    value: Any  # float or str (indicator key)
    is_indicator_comparison: bool = False
    tf: str = "exec"  # "exec", "htf", or "mtf"
    prev_offset: int = 1  # For crossover detection
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "indicator_key": self.indicator_key,
            "operator": self.operator.value,
            "value": self.value,
            "is_indicator_comparison": self.is_indicator_comparison,
            "tf": self.tf,
            "prev_offset": self.prev_offset,
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Condition":
        """Create from dict."""
        return cls(
            indicator_key=d["indicator_key"],
            operator=RuleOperator(d["operator"]),
            value=d["value"],
            is_indicator_comparison=d.get("is_indicator_comparison", False),
            tf=d.get("tf", "exec"),
            prev_offset=d.get("prev_offset", 1),
        )


@dataclass(frozen=True)
class EntryRule:
    """
    Entry rule specification (all conditions must be met).
    
    Attributes:
        direction: "long" or "short"
        conditions: List of conditions (AND logic)
    """
    direction: str  # "long" or "short"
    conditions: tuple  # Tuple[Condition, ...] for immutability
    
    def __post_init__(self):
        """Validate rule."""
        if self.direction not in ("long", "short"):
            raise ValueError(f"Invalid direction: {self.direction}. Must be 'long' or 'short'")
        if not self.conditions:
            raise ValueError("Entry rule must have at least one condition")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "direction": self.direction,
            "conditions": [c.to_dict() for c in self.conditions],
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EntryRule":
        """Create from dict."""
        conditions = tuple(Condition.from_dict(c) for c in d.get("conditions", []))
        return cls(
            direction=d["direction"],
            conditions=conditions,
        )


@dataclass(frozen=True)
class ExitRule:
    """
    Exit rule specification.
    
    Attributes:
        direction: Which position direction this exit applies to ("long" or "short")
        conditions: List of conditions (AND logic)
        exit_type: Type of exit ("signal", "stop_loss", "take_profit")
    """
    direction: str  # "long" or "short"
    conditions: tuple  # Tuple[Condition, ...] for immutability
    exit_type: str = "signal"  # "signal", "stop_loss", "take_profit"
    
    def __post_init__(self):
        """Validate rule."""
        if self.direction not in ("long", "short"):
            raise ValueError(f"Invalid direction: {self.direction}. Must be 'long' or 'short'")
        if self.exit_type not in ("signal", "stop_loss", "take_profit"):
            raise ValueError(f"Invalid exit_type: {self.exit_type}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "direction": self.direction,
            "conditions": [c.to_dict() for c in self.conditions],
            "exit_type": self.exit_type,
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ExitRule":
        """Create from dict."""
        conditions = tuple(Condition.from_dict(c) for c in d.get("conditions", []))
        return cls(
            direction=d["direction"],
            conditions=conditions,
            exit_type=d.get("exit_type", "signal"),
        )


@dataclass(frozen=True)
class SignalRules:
    """
    Complete signal logic specification.
    
    Contains entry and exit rules for the strategy.
    Entry rules are checked when no position exists.
    Exit rules are checked when a position exists.
    """
    entry_rules: tuple  # Tuple[EntryRule, ...]
    exit_rules: tuple   # Tuple[ExitRule, ...]
    
    def __post_init__(self):
        """Validate rules."""
        if not self.entry_rules:
            raise ValueError("SignalRules must have at least one entry rule")
    
    def get_entry_rules_for_direction(self, direction: str) -> List[EntryRule]:
        """Get entry rules for a specific direction."""
        return [r for r in self.entry_rules if r.direction == direction]
    
    def get_exit_rules_for_direction(self, direction: str) -> List[ExitRule]:
        """Get exit rules for a specific direction."""
        return [r for r in self.exit_rules if r.direction == direction]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "entry_rules": [r.to_dict() for r in self.entry_rules],
            "exit_rules": [r.to_dict() for r in self.exit_rules],
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SignalRules":
        """Create from dict."""
        entry_rules = tuple(EntryRule.from_dict(r) for r in d.get("entry_rules", []))
        exit_rules = tuple(ExitRule.from_dict(r) for r in d.get("exit_rules", []))
        return cls(
            entry_rules=entry_rules,
            exit_rules=exit_rules,
        )


# =============================================================================
# Market Structure Configuration
# =============================================================================

@dataclass(frozen=True)
class MarketStructureConfig:
    """
    Market structure configuration for a TF role.
    
    Defines data requirements beyond indicator warmup:
    - lookback_bars: Additional bars for market structure analysis (swing highs/lows, etc.)
    - delay_bars: Bars to skip at evaluation start (no-lookahead guarantee)
    
    Semantics:
    - lookback_bars: Used for data fetch range (data_start = window_start - lookback)
    - delay_bars: Used for evaluation offset (eval_start = aligned_start + delay)
    
    Engine MUST NOT apply lookback to evaluation start (only delay applies).
    """
    lookback_bars: int = 0
    delay_bars: int = 0
    
    def __post_init__(self):
        """Validate market structure config."""
        if self.lookback_bars < 0:
            raise ValueError(f"lookback_bars cannot be negative. Got: {self.lookback_bars}")
        if self.delay_bars < 0:
            raise ValueError(f"delay_bars cannot be negative. Got: {self.delay_bars}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "lookback_bars": self.lookback_bars,
            "delay_bars": self.delay_bars,
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MarketStructureConfig":
        """Create from dict."""
        return cls(
            lookback_bars=int(d.get("lookback_bars", 0)),
            delay_bars=int(d.get("delay_bars", 0)),
        )


# =============================================================================
# Timeframe Configuration
# =============================================================================

@dataclass(frozen=True)
class TFConfig:
    """
    Configuration for a single timeframe.
    
    Attributes:
        tf: Timeframe string (e.g., "15m", "1h", "4h")
        role: Role of this TF ("exec", "htf", or "mtf")
        feature_specs: FeatureSpecs for this TF
        warmup_bars: Minimum warmup bars for this TF
        required_indicators: List of indicator keys that must exist after feature computation.
            Used by the Indicator Requirements Gate to validate before simulation.
        market_structure: Optional market structure config with lookback_bars and delay_bars.
            lookback_bars: Additional data fetch range for structure analysis.
            delay_bars: Evaluation offset (no-lookahead guarantee).
    """
    tf: str
    role: str  # "exec", "htf", "mtf"
    feature_specs: tuple  # Tuple[FeatureSpec, ...]
    warmup_bars: int = 0
    required_indicators: tuple = field(default_factory=tuple)  # Tuple[str, ...]
    market_structure: Optional[MarketStructureConfig] = None
    
    def __post_init__(self):
        """Validate config."""
        if self.role not in ("exec", "htf", "mtf"):
            raise ValueError(f"Invalid TF role: {self.role}. Must be 'exec', 'htf', or 'mtf'")
        if not self.tf:
            raise ValueError("tf is required")
        # Validate required_indicators is a sequence of strings
        if self.required_indicators:
            for key in self.required_indicators:
                if not isinstance(key, str):
                    raise ValueError(
                        f"required_indicators must be list of strings. Got: {type(key).__name__}"
                    )
    
    @property
    def indicator_keys(self) -> List[str]:
        """Get all indicator output keys for this TF."""
        return [s.output_key for s in self.feature_specs]
    
    @property
    def max_warmup_from_specs(self) -> int:
        """Get maximum warmup needed from feature specs."""
        if not self.feature_specs:
            return 0
        return max(s.warmup_bars for s in self.feature_specs)
    
    @property
    def effective_warmup_bars(self) -> int:
        """Get effective warmup bars (max of explicit and derived)."""
        return max(self.warmup_bars, self.max_warmup_from_specs)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        result = {
            "tf": self.tf,
            "role": self.role,
            "feature_specs": [s.to_dict() for s in self.feature_specs],
            "warmup_bars": self.warmup_bars,
        }
        if self.required_indicators:
            result["required_indicators"] = list(self.required_indicators)
        if self.market_structure:
            result["market_structure"] = self.market_structure.to_dict()
        return result
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TFConfig":
        """Create from dict."""
        specs = tuple(FeatureSpec.from_dict(s) for s in d.get("feature_specs", []))
        required = tuple(d.get("required_indicators", []))
        
        # Parse market_structure if present
        market_structure = None
        if "market_structure" in d and d["market_structure"]:
            market_structure = MarketStructureConfig.from_dict(d["market_structure"])
        
        return cls(
            tf=d["tf"],
            role=d["role"],
            feature_specs=specs,
            warmup_bars=d.get("warmup_bars", 0),
            required_indicators=required,
            market_structure=market_structure,
        )


# =============================================================================
# IdeaCard
# =============================================================================

@dataclass
class IdeaCard:
    """
    Complete, self-contained strategy specification.
    
    An IdeaCard declares everything the backtest engine needs:
    - Identity (id, version)
    - Account config (starting equity, leverage, fees) - REQUIRED
    - Scope (symbols, timeframes)
    - Features (indicators per TF)
    - Position policy (direction constraints)
    - Signal rules (entry/exit logic)
    - Risk model (SL/TP/sizing)
    
    The engine reads the IdeaCard and:
    1. Builds features via FeatureFrameBuilder
    2. Applies position policy constraints
    3. Evaluates signal rules at each step
    4. Computes SL/TP from risk model
    
    No additional configuration is needed - the IdeaCard is the strategy.
    All runtime variables (capital, leverage, fees) come from the IdeaCard.
    """
    # Identity
    id: str
    version: str
    name: Optional[str] = None
    description: Optional[str] = None
    
    # Account configuration (REQUIRED - no hard-coded defaults)
    account: Optional[AccountConfig] = None
    
    # Scope
    symbol_universe: tuple = field(default_factory=tuple)  # Tuple[str, ...] of symbols
    
    # Timeframes (exec TF is required, HTF/MTF optional)
    tf_configs: Dict[str, TFConfig] = field(default_factory=dict)  # role -> TFConfig
    
    # History requirements
    bars_history_required: int = 0  # Number of historical bars strategy needs
    
    # Position policy
    position_policy: PositionPolicy = field(default_factory=PositionPolicy)
    
    # Signal rules
    signal_rules: Optional[SignalRules] = None
    
    # Risk model
    risk_model: Optional[RiskModel] = None
    
    def __post_init__(self):
        """Validate the IdeaCard."""
        errors = self.validate()
        if errors:
            raise ValueError(f"Invalid IdeaCard: {'; '.join(errors)}")
    
    def validate(self) -> List[str]:
        """
        Validate the IdeaCard.
        
        Returns:
            List of error messages (empty if valid)
        """
        errors = []
        
        # Required fields
        if not self.id:
            errors.append("id is required")
        if not self.version:
            errors.append("version is required")
        if not self.symbol_universe:
            errors.append("symbol_universe is required (at least one symbol)")
        
        # Account config is REQUIRED (no hard-coded defaults)
        if self.account is None:
            errors.append(
                "account section is required. IdeaCard must specify account.starting_equity_usdt "
                "and account.max_leverage (no hard-coded defaults allowed)"
            )
        else:
            # Account validation happens in AccountConfig.__post_init__, but we double-check here
            if self.account.starting_equity_usdt <= 0:
                errors.append("account.starting_equity_usdt must be positive")
            if self.account.max_leverage <= 0:
                errors.append("account.max_leverage must be positive")
        
        # Exec TF is required
        if "exec" not in self.tf_configs:
            errors.append("exec timeframe is required in tf_configs")
        
        # Validate position policy vs signal rules
        if self.signal_rules:
            # Check entry rules match position policy
            has_long_entry = any(r.direction == "long" for r in self.signal_rules.entry_rules)
            has_short_entry = any(r.direction == "short" for r in self.signal_rules.entry_rules)
            
            if has_long_entry and not self.position_policy.allows_long():
                errors.append(
                    f"IdeaCard has LONG entry rule but position_policy.mode={self.position_policy.mode.value} "
                    "does not allow long positions"
                )
            if has_short_entry and not self.position_policy.allows_short():
                errors.append(
                    f"IdeaCard has SHORT entry rule but position_policy.mode={self.position_policy.mode.value} "
                    "does not allow short positions"
                )
        
        return errors
    
    @property
    def exec_tf(self) -> str:
        """Get execution timeframe."""
        return self.tf_configs["exec"].tf
    
    @property
    def htf(self) -> Optional[str]:
        """Get HTF timeframe if configured."""
        cfg = self.tf_configs.get("htf")
        return cfg.tf if cfg else None
    
    @property
    def mtf(self) -> Optional[str]:
        """Get MTF timeframe if configured."""
        cfg = self.tf_configs.get("mtf")
        return cfg.tf if cfg else None
    
    def get_feature_spec_set(self, role: str, symbol: str) -> Optional[FeatureSpecSet]:
        """
        Get FeatureSpecSet for a specific TF role and symbol.
        
        Args:
            role: TF role ("exec", "htf", "mtf")
            symbol: Symbol to build for
            
        Returns:
            FeatureSpecSet or None if role not configured
        """
        cfg = self.tf_configs.get(role)
        if not cfg or not cfg.feature_specs:
            return None
        
        return FeatureSpecSet(
            symbol=symbol,
            tf=cfg.tf,
            specs=list(cfg.feature_specs),
        )
    
    def get_all_indicator_keys(self) -> Dict[str, List[str]]:
        """
        Get all indicator keys by TF role.
        
        Returns:
            Dict mapping role -> list of indicator keys
        """
        return {
            role: cfg.indicator_keys
            for role, cfg in self.tf_configs.items()
        }
    
    def get_required_warmup_bars(self, role: str) -> int:
        """Get required warmup bars for a TF role."""
        cfg = self.tf_configs.get(role)
        return cfg.effective_warmup_bars if cfg else 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        result = {
            "id": self.id,
            "version": self.version,
            "name": self.name,
            "description": self.description,
            "symbol_universe": list(self.symbol_universe),
            "tf_configs": {role: cfg.to_dict() for role, cfg in self.tf_configs.items()},
            "bars_history_required": self.bars_history_required,
            "position_policy": self.position_policy.to_dict(),
            "signal_rules": self.signal_rules.to_dict() if self.signal_rules else None,
            "risk_model": self.risk_model.to_dict() if self.risk_model else None,
        }
        if self.account:
            result["account"] = self.account.to_dict()
        return result
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "IdeaCard":
        """Create from dict."""
        # Parse account config (REQUIRED - fails if missing)
        account_dict = d.get("account")
        if account_dict:
            account = AccountConfig.from_dict(account_dict)
        else:
            # This will trigger validation error in IdeaCard.__post_init__
            account = None
        
        # Parse TF configs
        tf_configs = {}
        for role, cfg_dict in d.get("tf_configs", {}).items():
            tf_configs[role] = TFConfig.from_dict(cfg_dict)
        
        # Parse position policy
        pp_dict = d.get("position_policy", {})
        position_policy = PositionPolicy.from_dict(pp_dict) if pp_dict else PositionPolicy()
        
        # Parse signal rules
        sr_dict = d.get("signal_rules")
        signal_rules = SignalRules.from_dict(sr_dict) if sr_dict else None
        
        # Parse risk model
        rm_dict = d.get("risk_model")
        risk_model = RiskModel.from_dict(rm_dict) if rm_dict else None
        
        return cls(
            id=d.get("id", ""),  # Empty string triggers validation error
            version=d.get("version", ""),  # Empty string triggers validation error
            name=d.get("name"),
            description=d.get("description"),
            account=account,
            symbol_universe=tuple(d.get("symbol_universe", [])),
            tf_configs=tf_configs,
            bars_history_required=d.get("bars_history_required", 0),
            position_policy=position_policy,
            signal_rules=signal_rules,
            risk_model=risk_model,
        )


# =============================================================================
# Loader
# =============================================================================

# Default path for idea cards (canonical location: configs/idea_cards/)
# src/strategies/idea_cards/ is for examples/templates only
IDEA_CARDS_DIR = Path(__file__).parent.parent.parent / "configs" / "idea_cards"


def load_idea_card(idea_card_id: str, base_dir: Optional[Path] = None) -> IdeaCard:
    """
    Load an IdeaCard from YAML file.
    
    Searches in base_dir and subdirectories (_validation/, strategies/).
    
    Args:
        idea_card_id: Identifier (filename without .yml, or with subdir prefix)
        base_dir: Optional base directory (defaults to IDEA_CARDS_DIR)
        
    Returns:
        Validated IdeaCard instance
        
    Raises:
        FileNotFoundError: If file not found
        ValueError: If validation fails
    """
    search_dir = base_dir or IDEA_CARDS_DIR
    
    # Search locations: root, _validation/, strategies/
    search_paths = [
        search_dir,
        search_dir / "_validation",
        search_dir / "strategies",
    ]
    
    # Try each location
    path = None
    for search_path in search_paths:
        for ext in (".yml", ".yaml"):
            candidate = search_path / f"{idea_card_id}{ext}"
            if candidate.exists():
                path = candidate
                break
        if path:
            break
    
    if not path:
        available = list_idea_cards(search_dir)
        raise FileNotFoundError(
            f"IdeaCard '{idea_card_id}' not found in {search_dir}. "
            f"Available: {available}"
        )
    
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    
    if not raw:
        raise ValueError(f"Empty or invalid YAML in {path}")
    
    return IdeaCard.from_dict(raw)


def list_idea_cards(base_dir: Optional[Path] = None) -> List[str]:
    """
    List all available IdeaCard files.
    
    Searches in base_dir and subdirectories (_validation/, strategies/).
    
    Args:
        base_dir: Optional base directory (defaults to IDEA_CARDS_DIR)
        
    Returns:
        List of IdeaCard identifiers
    """
    search_dir = base_dir or IDEA_CARDS_DIR
    
    if not search_dir.exists():
        return []
    
    # Search locations: root, _validation/, strategies/
    search_paths = [
        search_dir,
        search_dir / "_validation",
        search_dir / "strategies",
    ]
    
    cards = set()
    for search_path in search_paths:
        if not search_path.exists():
            continue
        for ext in ("*.yml", "*.yaml"):
            for path in search_path.glob(ext):
                # Skip template files (start with _ but not test__)
                if path.stem.startswith("_") and not path.stem.startswith("test__"):
                    continue
                cards.add(path.stem)
    
    return sorted(cards)
