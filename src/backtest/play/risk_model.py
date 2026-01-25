"""
Risk model specifications for Play configurations.

Contains:
- StopLossType, TakeProfitType, SizingModel: Enums for risk rule types
- StopLossRule, TakeProfitRule, SizingRule: Rule specifications
- RiskModel: Complete risk model specification
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class StopLossType(str, Enum):
    """Stop loss calculation method."""
    ATR_MULTIPLE = "atr_multiple"
    PERCENT = "percent"
    STRUCTURE = "structure"
    FIXED_POINTS = "fixed_points"
    # Trailing stop types (stop follows price in profitable direction)
    TRAILING_ATR = "trailing_atr"
    TRAILING_PCT = "trailing_pct"


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
class TrailingConfig:
    """
    Configuration for trailing stops.

    Trailing stops move with the price as it moves in the profitable direction,
    locking in gains. The stop never moves backwards (adverse direction).

    Examples:
        # Trail 2x ATR behind price
        TrailingConfig(atr_multiplier=2.0)

        # Trail 1.5% behind price, start trailing after 1% profit
        TrailingConfig(trail_pct=1.5, activation_pct=1.0)
    """
    # ATR-based trailing (distance = ATR × multiplier)
    atr_multiplier: float = 2.0
    atr_feature_id: str | None = None  # Required for ATR trailing

    # Percent-based trailing (distance = price × trail_pct / 100)
    trail_pct: float | None = None

    # Activation threshold (start trailing after X% profit)
    # 0.0 = trail immediately from entry
    activation_pct: float = 0.0

    def __post_init__(self):
        """Validate config."""
        if self.atr_multiplier <= 0:
            raise ValueError(f"atr_multiplier must be positive. Got: {self.atr_multiplier}")
        if self.trail_pct is not None and self.trail_pct <= 0:
            raise ValueError(f"trail_pct must be positive. Got: {self.trail_pct}")
        if self.activation_pct < 0:
            raise ValueError(f"activation_pct must be >= 0. Got: {self.activation_pct}")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        result = {
            "atr_multiplier": self.atr_multiplier,
            "activation_pct": self.activation_pct,
        }
        if self.atr_feature_id:
            result["atr_feature_id"] = self.atr_feature_id
        if self.trail_pct is not None:
            result["trail_pct"] = self.trail_pct
        return result

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TrailingConfig":
        """Create from dict."""
        return cls(
            atr_multiplier=float(d.get("atr_multiplier", 2.0)),
            atr_feature_id=d.get("atr_feature_id"),
            trail_pct=float(d["trail_pct"]) if d.get("trail_pct") else None,
            activation_pct=float(d.get("activation_pct", 0.0)),
        )


@dataclass(frozen=True)
class BreakEvenConfig:
    """
    Configuration for break-even stops.

    Moves stop to entry price (plus optional offset) after reaching
    a profit threshold. Prevents winning trades from becoming losers.

    Examples:
        # Move to BE after 1% profit, with 0.1% buffer above entry
        BreakEvenConfig(activation_pct=1.0, offset_pct=0.1)
    """
    # Profit threshold to activate break-even (as % of entry price)
    activation_pct: float = 1.0

    # Offset above/below entry to place BE stop (as % of entry price)
    # Positive offset for longs: stop slightly above entry
    # Positive offset for shorts: stop slightly below entry
    offset_pct: float = 0.1

    def __post_init__(self):
        """Validate config."""
        if self.activation_pct <= 0:
            raise ValueError(f"activation_pct must be positive. Got: {self.activation_pct}")
        if self.offset_pct < 0:
            raise ValueError(f"offset_pct must be >= 0. Got: {self.offset_pct}")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "activation_pct": self.activation_pct,
            "offset_pct": self.offset_pct,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "BreakEvenConfig":
        """Create from dict."""
        return cls(
            activation_pct=float(d.get("activation_pct", 1.0)),
            offset_pct=float(d.get("offset_pct", 0.1)),
        )


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
        # Upper bounds check: prevent unreasonable SL values
        max_value = 100.0  # 100% SL or 100x ATR
        if self.value > max_value:
            raise ValueError(
                f"Stop loss value {self.value} exceeds maximum allowed ({max_value}). "
                f"For type={self.type.value}, this would result in unreasonable risk."
            )

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
        # Upper bounds check: prevent unreasonable TP values
        # For percent: 10000% (100x return) is a sanity upper bound
        # For ATR/RR: 100x is a reasonable upper bound
        max_value = 10000.0 if self.type == TakeProfitType.PERCENT else 100.0
        if self.value > max_value:
            raise ValueError(
                f"Take profit value {self.value} exceeds maximum allowed ({max_value}). "
                f"For type={self.type.value}, this would result in unreasonable targets."
            )

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
    trailing_config: TrailingConfig | None = None
    break_even_config: BreakEvenConfig | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        result = {
            "stop_loss": self.stop_loss.to_dict(),
            "take_profit": self.take_profit.to_dict(),
            "sizing": self.sizing.to_dict(),
        }
        if self.trailing_config:
            result["trailing"] = self.trailing_config.to_dict()
        if self.break_even_config:
            result["break_even"] = self.break_even_config.to_dict()
        return result

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RiskModel":
        """Create from dict."""
        trailing = None
        if d.get("trailing"):
            trailing = TrailingConfig.from_dict(d["trailing"])

        break_even = None
        if d.get("break_even"):
            break_even = BreakEvenConfig.from_dict(d["break_even"])

        return cls(
            stop_loss=StopLossRule.from_dict(d["stop_loss"]),
            take_profit=TakeProfitRule.from_dict(d["take_profit"]),
            sizing=SizingRule.from_dict(d["sizing"]),
            trailing_config=trailing,
            break_even_config=break_even,
        )
