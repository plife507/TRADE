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

from src.config.constants import DEFAULTS


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
        max_drawdown_pct: Maximum allowed drawdown percentage (must be > 0)
    """
    starting_equity_usdt: float
    max_leverage: float
    max_drawdown_pct: float  # Required: halt trading when drawdown exceeds this %

    margin_mode: str = "isolated_usdt"
    fee_model: FeeModel | None = None
    slippage_bps: float | None = None
    min_trade_notional_usdt: float | None = None
    max_notional_usdt: float | None = None
    max_margin_usdt: float | None = None
    maintenance_margin_rate: float | None = None
    mm_deduction: float = 0.0  # Bybit mmDeduction (0 for tier 1)
    on_sl_beyond_liq: str = "reject"  # "reject", "adjust", or "warn"
    risk_per_trade_pct: float | None = None  # Override sizing without risk_model

    def __post_init__(self):
        """Validate account config."""
        if self.starting_equity_usdt <= 0:
            raise ValueError(f"starting_equity_usdt must be positive. Got: {self.starting_equity_usdt}")
        if self.max_leverage <= 0:
            raise ValueError(f"max_leverage must be positive. Got: {self.max_leverage}")
        if self.max_drawdown_pct <= 0:
            raise ValueError(
                f"max_drawdown_pct must be positive (e.g., 25.0 for 25% max drawdown). "
                f"Got: {self.max_drawdown_pct}. This is a critical risk control."
            )
        if self.margin_mode != "isolated_usdt":
            raise ValueError(
                f"margin_mode must be 'isolated_usdt'. Got: '{self.margin_mode}'. "
                "Note: 'isolated' is deprecated, use 'isolated_usdt'."
            )
        if self.on_sl_beyond_liq not in ("reject", "adjust", "warn"):
            raise ValueError(
                f"on_sl_beyond_liq must be 'reject', 'adjust', or 'warn'. "
                f"Got: '{self.on_sl_beyond_liq}'"
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        result = {
            "starting_equity_usdt": self.starting_equity_usdt,
            "max_leverage": self.max_leverage,
            "max_drawdown_pct": self.max_drawdown_pct,
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
        if self.mm_deduction != 0.0:
            result["mm_deduction"] = self.mm_deduction
        if self.on_sl_beyond_liq != "reject":
            result["on_sl_beyond_liq"] = self.on_sl_beyond_liq
        if self.risk_per_trade_pct is not None:
            result["risk_per_trade_pct"] = self.risk_per_trade_pct
        return result

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AccountConfig":
        """Create from dict, using defaults from config/defaults.yml when not specified.

        Logs a warning for each field filled from defaults (hybrid approach:
        convenient for backtest/dev, but `validate pre-live` rejects implicit defaults).
        """
        import logging
        logger = logging.getLogger(__name__)

        defaulted: list[str] = []

        # All defaults come from config/defaults.yml - single source of truth
        if "starting_equity_usdt" in d:
            starting_equity = d["starting_equity_usdt"]
        else:
            starting_equity = DEFAULTS.account.starting_equity_usdt
            defaulted.append(f"starting_equity_usdt={starting_equity}")

        if "max_leverage" in d:
            max_leverage = d["max_leverage"]
        else:
            max_leverage = DEFAULTS.risk.max_leverage
            defaulted.append(f"max_leverage={max_leverage}")

        # max_drawdown_pct in defaults.yml is 0.20 (decimal), convert to percentage if needed
        default_drawdown = DEFAULTS.risk.max_drawdown_pct
        if default_drawdown < 1.0:
            default_drawdown = default_drawdown * 100.0
        if "max_drawdown_pct" in d:
            max_drawdown = d["max_drawdown_pct"]
        else:
            max_drawdown = default_drawdown
            defaulted.append(f"max_drawdown_pct={max_drawdown}")

        # Margin mode: defaults.yml uses "isolated", we use "isolated_usdt"
        default_margin_mode = DEFAULTS.margin.mode
        if default_margin_mode == "isolated":
            default_margin_mode = "isolated_usdt"
        margin_mode = d.get("margin_mode", default_margin_mode)

        # Fee model: use defaults if not specified in Play
        fee_model = None
        if "fee_model" in d and d["fee_model"]:
            fee_model = FeeModel.from_dict(d["fee_model"])
        else:
            fee_model = FeeModel(
                taker_bps=DEFAULTS.fees.taker_bps,
                maker_bps=DEFAULTS.fees.maker_bps,
            )
            defaulted.append(f"fee_model(taker={DEFAULTS.fees.taker_bps}, maker={DEFAULTS.fees.maker_bps})")

        # Execution defaults
        if "slippage_bps" in d:
            slippage = d["slippage_bps"]
        else:
            slippage = DEFAULTS.execution.slippage_bps
            defaulted.append(f"slippage_bps={slippage}")

        if "min_trade_notional_usdt" in d:
            min_notional = d["min_trade_notional_usdt"]
        else:
            min_notional = DEFAULTS.execution.min_trade_notional_usdt
            defaulted.append(f"min_trade_notional_usdt={min_notional}")

        # Margin defaults
        if "maintenance_margin_rate" in d:
            mmr = d["maintenance_margin_rate"]
        else:
            mmr = DEFAULTS.margin.maintenance_margin_rate
            defaulted.append(f"maintenance_margin_rate={mmr}")

        mm_deduction = float(d.get("mm_deduction", DEFAULTS.margin.mm_deduction))

        if defaulted:
            logger.warning(
                "AccountConfig using defaults from defaults.yml: %s",
                ", ".join(defaulted),
            )

        return cls(
            starting_equity_usdt=float(starting_equity),
            max_leverage=float(max_leverage),
            max_drawdown_pct=float(max_drawdown),
            margin_mode=margin_mode,
            fee_model=fee_model,
            slippage_bps=float(slippage),
            min_trade_notional_usdt=float(min_notional),
            max_notional_usdt=float(d["max_notional_usdt"]) if "max_notional_usdt" in d else None,
            max_margin_usdt=float(d["max_margin_usdt"]) if "max_margin_usdt" in d else None,
            maintenance_margin_rate=float(mmr),
            mm_deduction=mm_deduction,
            on_sl_beyond_liq=str(d.get("on_sl_beyond_liq", "reject")),
            risk_per_trade_pct=float(d["risk_per_trade_pct"]) if "risk_per_trade_pct" in d else None,
        )
