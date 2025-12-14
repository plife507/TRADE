"""
Simulated Risk Manager for backtesting.

Handles position sizing for backtest simulations.
This is NOT connected to any exchange - purely for testing.

Sizing models:
- percent_equity: Risk-based sizing using stop distance when available,
  capped by max leverage.
"""

from dataclasses import dataclass
from typing import Optional

from ..core.risk_manager import Signal
from .system_config import RiskProfileConfig
from .types import Trade
from .runtime.types import RuntimeSnapshot


@dataclass
class SizingResult:
    """Result of a sizing calculation."""
    size_usdt: float
    method: str  # "stop_based", "fallback_notional"
    details: str


class SimulatedRiskManager:
    """
    Simulated risk manager for backtesting position sizing.
    
    Does NOT connect to any exchange. Tracks equity internally
    and computes position sizes based on the risk profile.
    
    Sizing model (percent_equity):
    1. Compute risk dollars: risk$ = equity * (risk_per_trade_pct / 100)
    2. If stop distance available:
       size_usdt = risk$ * entry_price / abs(entry_price - stop_loss)
    3. Cap: size_usdt <= equity * max_leverage
    4. Fallback if stop missing: conservative notional sizing
    """
    
    def __init__(self, risk_profile: RiskProfileConfig):
        """
        Initialize with a resolved risk profile.
        
        Args:
            risk_profile: Resolved risk profile (YAML + any CLI overrides)
        """
        self._profile = risk_profile
        self._equity = risk_profile.initial_equity
    
    @property
    def equity(self) -> float:
        """Current tracked equity."""
        return self._equity
    
    @property
    def profile(self) -> RiskProfileConfig:
        """Risk profile used for sizing."""
        return self._profile
    
    def size_order(
        self,
        snapshot: RuntimeSnapshot,
        signal: Signal,
    ) -> SizingResult:
        """
        Compute position size for a signal.
        
        Args:
            snapshot: Current market snapshot (RuntimeSnapshot)
            signal: Trading signal with entry price in metadata
            
        Returns:
            SizingResult with computed size and method used
        """
        if self._profile.sizing_model == "percent_equity":
            return self._size_percent_equity(snapshot, signal)
        elif self._profile.sizing_model == "fixed_notional":
            return self._size_fixed_notional(signal)
        else:
            # Default to percent_equity
            return self._size_percent_equity(snapshot, signal)
    
    def _size_percent_equity(
        self,
        snapshot: RuntimeSnapshot,
        signal: Signal,
    ) -> SizingResult:
        """
        Size using percent of equity at risk.
        
        Uses stop distance for proper risk-based sizing when available.
        """
        equity = self._equity
        risk_pct = self._profile.risk_per_trade_pct
        max_lev = self._profile.max_leverage
        
        # Maximum size based on leverage
        max_size = equity * max_lev
        
        # Risk dollars
        risk_dollars = equity * (risk_pct / 100.0)
        
        # Try to get stop distance from signal metadata
        stop_loss = None
        # Get close price from RuntimeSnapshot
        entry_price = snapshot.bar_ltf.close
        
        if signal.metadata:
            stop_loss = signal.metadata.get("stop_loss")
            entry_price = signal.metadata.get("entry_price", entry_price)
        
        if stop_loss is not None and entry_price > 0:
            stop_distance = abs(entry_price - stop_loss)
            
            if stop_distance > 0:
                # Risk-based sizing: size_usdt = risk$ * entry / stop_distance
                size_usdt = risk_dollars * entry_price / stop_distance
                size_usdt = min(size_usdt, max_size)
                
                return SizingResult(
                    size_usdt=size_usdt,
                    method="stop_based",
                    details=f"risk=${risk_dollars:.2f}, stop_dist={stop_distance:.4f}, capped={size_usdt < max_size}"
                )
        
        # Fallback: conservative notional sizing (10% of max leverage)
        fallback_size = min(signal.size_usdt, max_size * 0.1)
        
        return SizingResult(
            size_usdt=fallback_size,
            method="fallback_notional",
            details=f"no valid stop, using fallback={fallback_size:.2f}"
        )
    
    def _size_fixed_notional(self, signal: Signal) -> SizingResult:
        """
        Size using fixed notional from signal.
        
        Still capped by max leverage.
        """
        equity = self._equity
        max_lev = self._profile.max_leverage
        max_size = equity * max_lev
        
        size_usdt = min(signal.size_usdt, max_size)
        
        return SizingResult(
            size_usdt=size_usdt,
            method="fixed_notional",
            details=f"requested={signal.size_usdt:.2f}, capped={size_usdt < signal.size_usdt}"
        )
    
    def update_equity(self, trade: Trade) -> None:
        """
        Update internal equity after a trade closes.
        
        Args:
            trade: Closed trade with net_pnl
        """
        if trade.is_closed:
            self._equity += trade.net_pnl
    
    def sync_equity(self, exchange_equity: float) -> None:
        """
        Sync internal equity with simulated exchange.
        
        Call this to ensure equity stays in sync with the exchange state.
        
        Args:
            exchange_equity: Current equity from SimulatedExchange
        """
        self._equity = exchange_equity
    
    def reset(self) -> None:
        """Reset equity to initial value."""
        self._equity = self._profile.initial_equity
