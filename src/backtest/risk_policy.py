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

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Any

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
    adjusted_size: Optional[float] = None
    
    @classmethod
    def allow(cls, reason: str = "Allowed", adjusted_size: float = None) -> "RiskDecision":
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
    ) -> RiskDecision:
        """
        Check if a signal should be allowed.
        
        Args:
            signal: Trading signal to evaluate
            equity: Current portfolio equity
            available_balance: Available balance for new trades
            total_exposure: Current total position exposure
            
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
    
    def __init__(self, risk_profile: RiskProfileConfig = None):
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
    ) -> RiskDecision:
        """Always allow signals."""
        return RiskDecision.allow(
            reason="NoneRiskPolicy: all signals allowed",
            adjusted_size=None,  # No adjustment
        )
    
    @property
    def name(self) -> str:
        return "none"


class RulesRiskPolicy(RiskPolicy):
    """
    Rule-based risk policy using RiskManager.
    
    Wraps the core RiskManager for production-faithful backtesting.
    Daily-loss enforcement is disabled for determinism.
    """
    
    def __init__(self, risk_profile: RiskProfileConfig):
        """
        Initialize with risk profile.
        
        Creates a RiskManager configured for backtesting:
        - Global risk disabled (no WebSocket dependency)
        - Uses risk profile values for limits
        
        Args:
            risk_profile: Risk profile from system config
        """
        self._risk_profile = risk_profile
        
        # Derive limits from the new canonical fields
        # max_position_size_usdt: use initial_equity * max_leverage as upper bound
        max_position = risk_profile.initial_equity * risk_profile.max_leverage
        
        # Create a RiskConfig from the profile
        self._risk_config = RiskConfig(
            max_leverage=risk_profile.max_leverage,
            max_position_size_usdt=max_position,
            max_total_exposure_usdt=max_position,
            min_balance_usdt=risk_profile.initial_equity * 0.1,  # 10% floor
            max_risk_per_trade_percent=risk_profile.risk_per_trade_pct,
            # Disable daily loss tracking for determinism
            max_daily_loss_usdt=float('inf'),
            max_daily_loss_percent=100.0,
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
    ) -> RiskDecision:
        """
        Check signal against risk rules.
        
        Builds a minimal PortfolioSnapshot and delegates to RiskManager.
        """
        # Build a minimal portfolio snapshot for the check
        # We don't have full position objects, but RiskManager.check() only
        # needs balance, available, and total_exposure
        from datetime import datetime
        
        portfolio = PortfolioSnapshot(
            timestamp=datetime.now(),
            balance=equity,
            available=available_balance,
            total_exposure=total_exposure,
            unrealized_pnl=0.0,
            positions=[],
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
    risk_profile: RiskProfileConfig = None,
) -> RiskPolicy:
    """
    Factory function to create the appropriate risk policy.
    
    Args:
        risk_mode: "none" or "rules"
        risk_profile: Risk profile from system config
        
    Returns:
        Appropriate RiskPolicy instance
        
    Raises:
        ValueError: If risk_mode is invalid
    """
    if risk_mode == "none":
        return NoneRiskPolicy(risk_profile)
    elif risk_mode == "rules":
        if risk_profile is None:
            risk_profile = RiskProfileConfig()
        return RulesRiskPolicy(risk_profile)
    else:
        raise ValueError(
            f"Invalid risk_mode: '{risk_mode}'. Must be 'none' or 'rules'."
        )
