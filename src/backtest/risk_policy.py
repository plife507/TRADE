"""
Risk policy abstraction for backtesting.

Provides pluggable risk policies:
- NoneRiskPolicy: Always allow signals (pure strategy backtest)
- RulesRiskPolicy: Apply RiskManager checks (production-faithful)

Usage:
    policy = create_risk_policy(config.risk_mode, config.risk_profile)
    decision = policy.check(signal, portfolio_state)
    if decision.allowed:
        # Execute trade
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..core.risk_manager import Signal, RiskCheckResult, RiskManager, RiskConfig
from ..core.position_manager import PortfolioSnapshot
from .system_config import RiskProfileConfig


@dataclass
class RiskDecision:
    """
    Result of a risk policy check.

    Mirrors RiskCheckResult but decoupled from core RiskManager.
    """
    allowed: bool
    reason: str
    adjusted_size: float | None = None
    
    @classmethod
    def allow(cls, reason: str = "Allowed", adjusted_size: float | None = None) -> "RiskDecision":
        return cls(allowed=True, reason=reason, adjusted_size=adjusted_size)
    
    @classmethod
    def deny(cls, reason: str) -> "RiskDecision":
        return cls(allowed=False, reason=reason)


class RiskPolicy(ABC):
    """
    Abstract base class for risk policies.
    
    Strategies generate Signals, the risk policy decides if they execute.
    """
    
    @abstractmethod
    def check(
        self,
        signal: Signal,
        equity: float,
        available_balance: float,
        total_exposure: float,
        unrealized_pnl: float = 0.0,
        position_count: int = 0,
    ) -> RiskDecision:
        """
        Check if a signal should be allowed.

        Args:
            signal: Trading signal to evaluate
            equity: Current portfolio equity
            available_balance: Available balance for new trades
            total_exposure: Current total position exposure
            unrealized_pnl: Unrealized PnL from open positions
            position_count: Number of open positions

        Returns:
            RiskDecision with allowed/denied status
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Policy name for logging."""
        pass


class NoneRiskPolicy(RiskPolicy):
    """
    Always-allow risk policy.

    Used for pure strategy backtesting without risk constraints.
    Signals pass through unchanged.
    """

    def __init__(self, risk_profile: RiskProfileConfig | None = None):
        """
        Initialize with optional risk profile (for reference only).
        
        Args:
            risk_profile: Optional profile (not used for filtering)
        """
        self._risk_profile = risk_profile
    
    def check(
        self,
        signal: Signal,
        equity: float,
        available_balance: float,
        total_exposure: float,
        unrealized_pnl: float = 0.0,
        position_count: int = 0,
    ) -> RiskDecision:
        """Always allow signals (ignores portfolio state)."""
        return RiskDecision.allow(
            reason="NoneRiskPolicy: all signals allowed",
        )
    
    @property
    def name(self) -> str:
        return "none"


class RulesRiskPolicy(RiskPolicy):
    """
    Rule-based risk policy using RiskManager.

    Wraps the core RiskManager for production-faithful backtesting.

    NOTE: Daily loss limit is set to infinity by default for determinism.
    This is intentional - backtests should not halt mid-run due to
    cumulative losses, as this would make results non-reproducible
    across different starting points. Live trading enforces real
    daily limits via the live RiskManager.
    """

    def __init__(
        self,
        risk_profile: RiskProfileConfig,
        enforce_daily_loss: bool = False,
    ):
        """
        Initialize with risk profile.

        Creates a RiskManager configured for backtesting:
        - Global risk disabled (no WebSocket dependency)
        - Uses risk profile values for limits
        - Daily loss disabled by default for determinism

        Args:
            risk_profile: Risk profile from system config
            enforce_daily_loss: If True, use risk_profile.max_daily_loss_usdt.
                               If False (default), daily loss is infinite.
        """
        self._risk_profile = risk_profile
        self._enforce_daily_loss = enforce_daily_loss

        # Derive limits from the new canonical fields
        # max_position_size_usdt: use initial_equity * max_leverage as upper bound
        max_position = risk_profile.initial_equity * risk_profile.max_leverage

        # Determine daily loss limit
        if enforce_daily_loss:
            # Use max_daily_loss_usdt if available, otherwise default to 10% of equity
            daily_loss_usdt = getattr(
                risk_profile, 'max_daily_loss_usdt',
                risk_profile.initial_equity * 0.10,  # 10% default
            )
            daily_loss_pct = 100.0  # Use the USDT limit, not percent
        else:
            daily_loss_usdt = float('inf')
            daily_loss_pct = 100.0

        # Create a RiskConfig from the profile
        self._risk_config = RiskConfig(
            max_leverage=int(risk_profile.max_leverage),
            max_position_size_usdt=max_position,
            max_total_exposure_usd=max_position,
            min_balance_usd=risk_profile.initial_equity * 0.1,  # 10% floor
            max_risk_per_trade_percent=risk_profile.risk_per_trade_pct,
            max_daily_loss_usd=daily_loss_usdt,
            max_daily_loss_percent=daily_loss_pct,
        )
        
        # Create RiskManager with global risk disabled
        self._risk_manager = RiskManager(
            config=self._risk_config,
            enable_global_risk=False,
        )
    
    def check(
        self,
        signal: Signal,
        equity: float,
        available_balance: float,
        total_exposure: float,
        unrealized_pnl: float = 0.0,
        position_count: int = 0,
    ) -> RiskDecision:
        """
        Check signal against risk rules.

        Builds a PortfolioSnapshot and delegates to RiskManager.

        Args:
            signal: Signal to check
            equity: Current equity (balance + unrealized PnL)
            available_balance: Available balance for new positions
            total_exposure: Total position exposure in USDT
            unrealized_pnl: Unrealized PnL from open positions (P1-004 fix)
            position_count: Number of open positions (P1-004 fix)
        """
        from datetime import datetime

        # P1-004 FIX: Include unrealized_pnl and position count from exchange
        # PortfolioSnapshot.positions expects list[Position] but we only need the count
        # Create placeholder Position objects to represent position count
        from ..core.exchange_manager import Position as CorePosition
        placeholder_positions: list[CorePosition] = []
        if position_count > 0:
            placeholder_positions = [
                CorePosition(
                    symbol="", exchange="backtest", position_type="linear",
                    side="", size=0.0, size_usdt=0.0, entry_price=0.0,
                    current_price=0.0, unrealized_pnl=0.0,
                    unrealized_pnl_percent=0.0, leverage=1.0, margin_mode="isolated",
                )
            ] * position_count
        portfolio = PortfolioSnapshot(
            timestamp=datetime.now(),
            balance=equity,
            available=available_balance,
            total_exposure=total_exposure,
            unrealized_pnl=unrealized_pnl,
            positions=placeholder_positions,
            source="backtest",
        )
        
        # Delegate to RiskManager
        result: RiskCheckResult = self._risk_manager.check(signal, portfolio)
        
        return RiskDecision(
            allowed=result.allowed,
            reason=result.reason,
            adjusted_size=result.adjusted_size,
        )
    
    @property
    def name(self) -> str:
        return "rules"


def create_risk_policy(
    risk_mode: str,
    risk_profile: RiskProfileConfig | None = None,
    enforce_daily_loss: bool = False,
) -> RiskPolicy:
    """
    Factory function to create the appropriate risk policy.

    Args:
        risk_mode: "none" or "rules"
        risk_profile: Risk profile from system config
        enforce_daily_loss: If True and risk_mode="rules", use daily loss limit.
                           Default False for deterministic backtests.

    Returns:
        Appropriate RiskPolicy instance

    Raises:
        ValueError: If risk_mode is invalid
    """
    if risk_mode == "none":
        return NoneRiskPolicy(risk_profile)
    elif risk_mode == "rules":
        if risk_profile is None:
            risk_profile = RiskProfileConfig(initial_equity=10000.0)
        return RulesRiskPolicy(risk_profile, enforce_daily_loss=enforce_daily_loss)
    else:
        raise ValueError(
            f"Invalid risk_mode: '{risk_mode}'. Must be 'none' or 'rules'."
        )
