"""
Configuration models for Play specifications.

Contains:
- FeeModel: Trading fee configuration
- AccountConfig: Account/capital configuration
- ExitMode: Position exit mode enum
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ExitMode(str, Enum):
    """
    Exit mode defines how positions are closed.

    SL_TP_ONLY: Positions exit ONLY via stop loss or take profit.
               No signal-based exits allowed. Pure mechanical trading.
               Requires risk_model with stop_loss and take_profit defined.

    SIGNAL: Positions exit via signal (exit_long, exit_short, exit_all).
            SL/TP in risk_model act as emergency stops only.
            Requires exit actions defined in the actions block.

    FIRST_HIT: Hybrid mode - position exits on whichever triggers first:
               signal-based exit OR SL/TP hit. Explicitly allows both.
    """
    SL_TP_ONLY = "sl_tp_only"
    SIGNAL = "signal"
    FIRST_HIT = "first_hit"


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
        if self.margin_mode != "isolated_usdt":
            raise ValueError(
                f"margin_mode must be 'isolated_usdt'. Got: '{self.margin_mode}'. "
                "Note: 'isolated' is deprecated, use 'isolated_usdt'."
            )

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
