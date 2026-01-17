"""
RuntimeConfig: Unified configuration for backtest execution.

RuntimeConfig is the bridge between Play and the backtest engine.
It carries all runtime variables explicitly - no defaults are assumed.

Design principles:
- All values come from Play.account or CLI overrides
- No hard-coded defaults for capital/account fields
- Validation at construction time
- Immutable after creation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .play import Play

from .play import AccountConfig, FeeModel


@dataclass(frozen=True)
class RuntimeConfig:
    """
    Unified runtime configuration for backtest execution.
    
    Carries all runtime variables needed by the backtest engine.
    Constructed from Play + optional CLI overrides.
    
    All capital/account fields are REQUIRED (from Play.account).
    No hard-coded defaults - fail loud if missing.
    """
    # Identity (from Play)
    play_id: str
    play_version: str
    
    # Account/capital config (from Play.account - REQUIRED)
    starting_equity_usdt: float
    max_leverage: float
    margin_mode: str
    
    # Fee model (from Play.account.fee_model - loaded from DEFAULTS if not specified)
    taker_fee_rate: float | None = None
    maker_fee_rate: float | None = None
    
    # Slippage (from Play.account.slippage_bps - optional)
    slippage_bps: float | None = None
    
    # Trade size constraints (from Play.account - optional)
    min_trade_notional_usdt: float = 1.0
    max_notional_usdt: float | None = None
    max_margin_usdt: float | None = None
    
    # Symbol and timeframe config (from Play)
    symbol: str = ""
    exec_tf: str = ""
    high_tf: str | None = None
    med_tf: str | None = None

    # Warmup requirements (from Play tf_configs)
    warmup_bars_exec: int = 0
    warmup_bars_high_tf: int = 0
    warmup_bars_med_tf: int = 0
    
    # Window dates (from CLI/runner)
    window_start: datetime | None = None
    window_end: datetime | None = None
    
    # Data environment (from CLI)
    data_env: str = "live"
    
    # Risk model sizing (from Play.risk_model)
    sizing_model: str = "percent_equity"
    sizing_value: float = 1.0
    
    # Required indicators by role (from Play.tf_configs[role].required_indicators)
    required_indicators_exec: tuple = field(default_factory=tuple)
    required_indicators_high_tf: tuple = field(default_factory=tuple)
    required_indicators_med_tf: tuple = field(default_factory=tuple)
    
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
    def from_play(
        cls,
        play: Play,
        symbol_override: str | None = None,
        starting_equity_override: float | None = None,
        max_leverage_override: float | None = None,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        data_env: str = "live",
    ) -> RuntimeConfig:
        """
        Create RuntimeConfig from Play with optional overrides.
        
        Args:
            play: Source Play (must have account section)
            symbol_override: Override symbol (default: first in symbol_universe)
            starting_equity_override: Override starting equity
            max_leverage_override: Override max leverage
            window_start: Window start datetime
            window_end: Window end datetime
            data_env: Data environment ("live" or "demo")
            
        Returns:
            RuntimeConfig with all values resolved
            
        Raises:
            ValueError: If Play is missing required account section
        """
        # Validate account config is present
        if play.account is None:
            raise ValueError(
                f"Play '{play.id}' is missing account section. "
                "account.starting_equity_usdt and account.max_leverage are required."
            )
        
        account = play.account
        
        # Resolve capital/account values (Play is source of truth, overrides win)
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
        
        # Extract fee rates from fee model (use DEFAULTS if not specified)
        from src.config.constants import DEFAULTS
        taker_fee_rate = DEFAULTS.fees.taker_rate
        maker_fee_rate = DEFAULTS.fees.maker_rate
        if account.fee_model:
            taker_fee_rate = account.fee_model.taker_rate
            maker_fee_rate = account.fee_model.maker_rate
        
        # Resolve symbol
        symbol = symbol_override
        if symbol is None:
            if not play.symbol_universe:
                raise ValueError("Play has no symbols in symbol_universe")
            symbol = play.symbol_universe[0]
        
        # Extract sizing from risk model
        sizing_model = "percent_equity"
        sizing_value = 1.0
        if play.risk_model:
            sizing_model = play.risk_model.sizing.model.value
            sizing_value = play.risk_model.sizing.value
            # risk_model.sizing.max_leverage can override
            if play.risk_model.sizing.max_leverage:
                max_leverage = play.risk_model.sizing.max_leverage
        
        # Warmup is calculated elsewhere - Play doesn't have these methods
        # The backtest engine calculates warmup based on indicator requirements
        warmup_exec = 0
        warmup_high_tf = 0
        warmup_med_tf = 0

        # Required indicators are extracted from features, not tf_configs
        # Play uses feature_registry to track indicators per timeframe
        required_exec = ()
        required_high_tf = ()
        required_med_tf = ()

        return cls(
            play_id=play.id,
            play_version=play.version,
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
            exec_tf=play.exec_tf,
            high_tf=play.high_tf,
            med_tf=play.med_tf,
            warmup_bars_exec=warmup_exec,
            warmup_bars_high_tf=warmup_high_tf,
            warmup_bars_med_tf=warmup_med_tf,
            window_start=window_start,
            window_end=window_end,
            data_env=data_env,
            sizing_model=sizing_model,
            sizing_value=sizing_value,
            required_indicators_exec=required_exec,
            required_indicators_high_tf=required_high_tf,
            required_indicators_med_tf=required_med_tf,
        )
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization/logging."""
        return {
            "play_id": self.play_id,
            "play_version": self.play_version,
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
            "high_tf": self.high_tf,
            "med_tf": self.med_tf,
            "warmup_bars_exec": self.warmup_bars_exec,
            "warmup_bars_high_tf": self.warmup_bars_high_tf,
            "warmup_bars_med_tf": self.warmup_bars_med_tf,
            "window_start": self.window_start.isoformat() if self.window_start else None,
            "window_end": self.window_end.isoformat() if self.window_end else None,
            "data_env": self.data_env,
            "sizing_model": self.sizing_model,
            "sizing_value": self.sizing_value,
            "required_indicators_exec": list(self.required_indicators_exec),
            "required_indicators_high_tf": list(self.required_indicators_high_tf),
            "required_indicators_med_tf": list(self.required_indicators_med_tf),
        }

    def get_required_indicators_by_role(self) -> dict[str, list[str]]:
        """Get required indicators grouped by TF role."""
        result = {}
        if self.required_indicators_exec:
            result["exec"] = list(self.required_indicators_exec)
        if self.required_indicators_high_tf:
            result["high_tf"] = list(self.required_indicators_high_tf)
        if self.required_indicators_med_tf:
            result["med_tf"] = list(self.required_indicators_med_tf)
        return result
    
    def print_summary(self, logger=None) -> None:
        """Print resolved config summary."""
        lines = [
            "=" * 60,
            "RESOLVED CONFIG SUMMARY",
            "=" * 60,
            f"  play: {self.play_id} v{self.play_version}",
            f"  symbol: {self.symbol}",
            f"  tf_exec: {self.exec_tf}",
        ]
        if self.high_tf:
            lines.append(f"  tf_high: {self.high_tf}")
        if self.med_tf:
            lines.append(f"  tf_med: {self.med_tf}")
        lines.append("-" * 40)
        lines.append(f"  starting_equity_usdt: {self.starting_equity_usdt:,.2f}")
        lines.append(f"  max_leverage: {self.max_leverage:.1f}x")
        lines.append(f"  min_trade_notional_usdt: {self.min_trade_notional_usdt:.2f}")
        lines.append(f"  taker_fee_rate: {self.taker_fee_rate:.4f} ({self.taker_fee_rate * 10000:.1f} bps)")
        if self.slippage_bps:
            lines.append(f"  slippage_bps: {self.slippage_bps}")
        lines.append("-" * 40)
        lines.append(f"  warmup_exec: {self.warmup_bars_exec} bars")
        if self.warmup_bars_high_tf:
            lines.append(f"  warmup_high_tf: {self.warmup_bars_high_tf} bars")
        if self.warmup_bars_med_tf:
            lines.append(f"  warmup_med_tf: {self.warmup_bars_med_tf} bars")
        lines.append("=" * 60)
        
        text = "\n".join(lines)
        if logger:
            for line in lines:
                logger.info(line)
        else:
            print(text)

