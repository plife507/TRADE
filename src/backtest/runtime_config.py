"""
RuntimeConfig: Unified configuration for backtest execution.

RuntimeConfig is the bridge between IdeaCard and the backtest engine.
It carries all runtime variables explicitly - no defaults are assumed.

Design principles:
- All values come from IdeaCard.account or CLI overrides
- No hard-coded defaults for capital/account fields
- Validation at construction time
- Immutable after creation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .idea_card import IdeaCard

from .idea_card import AccountConfig, FeeModel


@dataclass(frozen=True)
class RuntimeConfig:
    """
    Unified runtime configuration for backtest execution.
    
    Carries all runtime variables needed by the backtest engine.
    Constructed from IdeaCard + optional CLI overrides.
    
    All capital/account fields are REQUIRED (from IdeaCard.account).
    No hard-coded defaults - fail loud if missing.
    """
    # Identity (from IdeaCard)
    idea_card_id: str
    idea_card_version: str
    
    # Account/capital config (from IdeaCard.account - REQUIRED)
    starting_equity_usdt: float
    max_leverage: float
    margin_mode: str
    
    # Fee model (from IdeaCard.account.fee_model - optional)
    taker_fee_rate: float = 0.0006  # Default Bybit rate
    maker_fee_rate: float = 0.0002  # Default Bybit rate
    
    # Slippage (from IdeaCard.account.slippage_bps - optional)
    slippage_bps: float | None = None
    
    # Trade size constraints (from IdeaCard.account - optional)
    min_trade_notional_usdt: float = 1.0
    max_notional_usdt: float | None = None
    max_margin_usdt: float | None = None
    
    # Symbol and timeframe config (from IdeaCard)
    symbol: str = ""
    exec_tf: str = ""
    htf: str | None = None
    mtf: str | None = None
    
    # Warmup requirements (from IdeaCard tf_configs)
    warmup_bars_exec: int = 0
    warmup_bars_htf: int = 0
    warmup_bars_mtf: int = 0
    
    # Window dates (from CLI/runner)
    window_start: datetime | None = None
    window_end: datetime | None = None
    
    # Data environment (from CLI)
    data_env: str = "live"
    
    # Risk model sizing (from IdeaCard.risk_model)
    sizing_model: str = "percent_equity"
    sizing_value: float = 1.0
    
    # Required indicators by role (from IdeaCard.tf_configs[role].required_indicators)
    required_indicators_exec: tuple = field(default_factory=tuple)
    required_indicators_htf: tuple = field(default_factory=tuple)
    required_indicators_mtf: tuple = field(default_factory=tuple)
    
    def __post_init__(self):
        """Validate runtime config."""
        if self.starting_equity_usdt <= 0:
            raise ValueError(
                f"starting_equity_usdt must be positive. Got: {self.starting_equity_usdt}"
            )
        if self.max_leverage <= 0:
            raise ValueError(
                f"max_leverage must be positive. Got: {self.max_leverage}"
            )
    
    @classmethod
    def from_idea_card(
        cls,
        idea_card: IdeaCard,
        symbol_override: str | None = None,
        starting_equity_override: float | None = None,
        max_leverage_override: float | None = None,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        data_env: str = "live",
    ) -> RuntimeConfig:
        """
        Create RuntimeConfig from IdeaCard with optional overrides.
        
        Args:
            idea_card: Source IdeaCard (must have account section)
            symbol_override: Override symbol (default: first in symbol_universe)
            starting_equity_override: Override starting equity
            max_leverage_override: Override max leverage
            window_start: Window start datetime
            window_end: Window end datetime
            data_env: Data environment ("live" or "demo")
            
        Returns:
            RuntimeConfig with all values resolved
            
        Raises:
            ValueError: If IdeaCard is missing required account section
        """
        # Validate account config is present
        if idea_card.account is None:
            raise ValueError(
                f"IdeaCard '{idea_card.id}' is missing account section. "
                "account.starting_equity_usdt and account.max_leverage are required."
            )
        
        account = idea_card.account
        
        # Resolve capital/account values (IdeaCard is source of truth, overrides win)
        starting_equity = (
            starting_equity_override 
            if starting_equity_override is not None 
            else account.starting_equity_usdt
        )
        max_leverage = (
            max_leverage_override 
            if max_leverage_override is not None 
            else account.max_leverage
        )
        
        # Extract fee rates from fee model
        taker_fee_rate = 0.0006  # Default
        maker_fee_rate = 0.0002  # Default
        if account.fee_model:
            taker_fee_rate = account.fee_model.taker_rate
            maker_fee_rate = account.fee_model.maker_rate
        
        # Resolve symbol
        symbol = symbol_override
        if symbol is None:
            if not idea_card.symbol_universe:
                raise ValueError("IdeaCard has no symbols in symbol_universe")
            symbol = idea_card.symbol_universe[0]
        
        # Extract sizing from risk model
        sizing_model = "percent_equity"
        sizing_value = 1.0
        if idea_card.risk_model:
            sizing_model = idea_card.risk_model.sizing.model.value
            sizing_value = idea_card.risk_model.sizing.value
            # risk_model.sizing.max_leverage can override
            if idea_card.risk_model.sizing.max_leverage:
                max_leverage = idea_card.risk_model.sizing.max_leverage
        
        # Extract warmup requirements
        warmup_exec = idea_card.get_required_warmup_bars("exec")
        warmup_htf = idea_card.get_required_warmup_bars("htf")
        warmup_mtf = idea_card.get_required_warmup_bars("mtf")
        
        # Extract required indicators
        required_exec = tuple(idea_card.tf_configs.get("exec", None).required_indicators) if "exec" in idea_card.tf_configs else ()
        required_htf = tuple(idea_card.tf_configs.get("htf", None).required_indicators) if "htf" in idea_card.tf_configs else ()
        required_mtf = tuple(idea_card.tf_configs.get("mtf", None).required_indicators) if "mtf" in idea_card.tf_configs else ()
        
        return cls(
            idea_card_id=idea_card.id,
            idea_card_version=idea_card.version,
            starting_equity_usdt=starting_equity,
            max_leverage=max_leverage,
            margin_mode=account.margin_mode,
            taker_fee_rate=taker_fee_rate,
            maker_fee_rate=maker_fee_rate,
            slippage_bps=account.slippage_bps,
            min_trade_notional_usdt=account.min_trade_notional_usdt or 1.0,
            max_notional_usdt=account.max_notional_usdt,
            max_margin_usdt=account.max_margin_usdt,
            symbol=symbol,
            exec_tf=idea_card.exec_tf,
            htf=idea_card.htf,
            mtf=idea_card.mtf,
            warmup_bars_exec=warmup_exec,
            warmup_bars_htf=warmup_htf,
            warmup_bars_mtf=warmup_mtf,
            window_start=window_start,
            window_end=window_end,
            data_env=data_env,
            sizing_model=sizing_model,
            sizing_value=sizing_value,
            required_indicators_exec=required_exec,
            required_indicators_htf=required_htf,
            required_indicators_mtf=required_mtf,
        )
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization/logging."""
        return {
            "idea_card_id": self.idea_card_id,
            "idea_card_version": self.idea_card_version,
            "starting_equity_usdt": self.starting_equity_usdt,
            "max_leverage": self.max_leverage,
            "margin_mode": self.margin_mode,
            "taker_fee_rate": self.taker_fee_rate,
            "maker_fee_rate": self.maker_fee_rate,
            "slippage_bps": self.slippage_bps,
            "min_trade_notional_usdt": self.min_trade_notional_usdt,
            "max_notional_usdt": self.max_notional_usdt,
            "max_margin_usdt": self.max_margin_usdt,
            "symbol": self.symbol,
            "exec_tf": self.exec_tf,
            "htf": self.htf,
            "mtf": self.mtf,
            "warmup_bars_exec": self.warmup_bars_exec,
            "warmup_bars_htf": self.warmup_bars_htf,
            "warmup_bars_mtf": self.warmup_bars_mtf,
            "window_start": self.window_start.isoformat() if self.window_start else None,
            "window_end": self.window_end.isoformat() if self.window_end else None,
            "data_env": self.data_env,
            "sizing_model": self.sizing_model,
            "sizing_value": self.sizing_value,
            "required_indicators_exec": list(self.required_indicators_exec),
            "required_indicators_htf": list(self.required_indicators_htf),
            "required_indicators_mtf": list(self.required_indicators_mtf),
        }
    
    def get_required_indicators_by_role(self) -> dict[str, list[str]]:
        """Get required indicators grouped by TF role."""
        result = {}
        if self.required_indicators_exec:
            result["exec"] = list(self.required_indicators_exec)
        if self.required_indicators_htf:
            result["htf"] = list(self.required_indicators_htf)
        if self.required_indicators_mtf:
            result["mtf"] = list(self.required_indicators_mtf)
        return result
    
    def print_summary(self, logger=None) -> None:
        """Print resolved config summary."""
        lines = [
            "=" * 60,
            "RESOLVED CONFIG SUMMARY",
            "=" * 60,
            f"  idea_card: {self.idea_card_id} v{self.idea_card_version}",
            f"  symbol: {self.symbol}",
            f"  tf_exec: {self.exec_tf}",
        ]
        if self.htf:
            lines.append(f"  tf_htf: {self.htf}")
        if self.mtf:
            lines.append(f"  tf_mtf: {self.mtf}")
        lines.append("-" * 40)
        lines.append(f"  starting_equity_usdt: {self.starting_equity_usdt:,.2f}")
        lines.append(f"  max_leverage: {self.max_leverage:.1f}x")
        lines.append(f"  min_trade_notional_usdt: {self.min_trade_notional_usdt:.2f}")
        lines.append(f"  taker_fee_rate: {self.taker_fee_rate:.4f} ({self.taker_fee_rate * 10000:.1f} bps)")
        if self.slippage_bps:
            lines.append(f"  slippage_bps: {self.slippage_bps}")
        lines.append("-" * 40)
        lines.append(f"  warmup_exec: {self.warmup_bars_exec} bars")
        if self.warmup_bars_htf:
            lines.append(f"  warmup_htf: {self.warmup_bars_htf} bars")
        if self.warmup_bars_mtf:
            lines.append(f"  warmup_mtf: {self.warmup_bars_mtf} bars")
        lines.append("=" * 60)
        
        text = "\n".join(lines)
        if logger:
            for line in lines:
                logger.info(line)
        else:
            print(text)

