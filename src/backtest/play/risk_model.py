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
