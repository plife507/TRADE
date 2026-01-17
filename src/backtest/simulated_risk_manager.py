"""
Simulated Risk Manager for backtesting.

Handles position sizing for backtest simulations.
This is NOT connected to any exchange - purely for testing.

Sizing models:
- percent_equity: Risk-based sizing using stop distance when available,
  capped by max leverage.

REQUIRES RuntimeSnapshotView — legacy RuntimeSnapshot is not supported.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..core.risk_manager import Signal
from .system_config import RiskProfileConfig
from .types import Trade

if TYPE_CHECKING:
    from .runtime.snapshot_view import RuntimeSnapshotView


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
    
    REQUIRES RuntimeSnapshotView — legacy RuntimeSnapshot is not supported.
    
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
        snapshot: "RuntimeSnapshotView",
        signal: Signal,
    ) -> SizingResult:
        """
        Compute position size for a signal.
        
        Args:
            snapshot: Current market snapshot (RuntimeSnapshotView ONLY)
            signal: Trading signal with entry price in metadata
            
        Returns:
            SizingResult with computed size and method used
            
        Raises:
            TypeError: If snapshot is not RuntimeSnapshotView
        """
        # Require RuntimeSnapshotView — fail fast if legacy snapshot passed
        if not hasattr(snapshot, 'close'):
            raise TypeError(
                f"SimulatedRiskManager requires RuntimeSnapshotView (with .close property). "
                f"Got {type(snapshot).__name__}. Legacy RuntimeSnapshot is not supported."
            )
        
        model = self._profile.sizing_model
        if model == "percent_equity":
            return self._size_percent_equity(snapshot, signal)
        elif model == "risk_based":
            return self._size_risk_based(snapshot, signal)
        elif model in ("fixed_usdt", "fixed_notional"):
            return self._size_fixed_notional(signal)
        else:
            # Default to percent_equity
            return self._size_percent_equity(snapshot, signal)
    
    def _size_percent_equity(
        self,
        snapshot: "RuntimeSnapshotView",
        signal: Signal,
    ) -> SizingResult:
        """
        Size using percentage of equity as margin, then apply leverage.

        Bybit margin model:
        - margin = equity × (risk_pct / 100)
        - position_value = margin × leverage

        Example with 10% of $10,000 equity at 10x leverage:
        - margin = $10,000 × 10% = $1,000 (what you're putting up)
        - position = $1,000 × 10 = $10,000 (your exposure)

        Example with 10% of $10,000 equity at 1x leverage:
        - margin = $10,000 × 10% = $1,000
        - position = $1,000 × 1 = $1,000

        The position is capped at equity × max_leverage (max borrowing).
        """
        equity = self._equity
        risk_pct = self._profile.risk_per_trade_pct
        max_lev = self._profile.max_leverage

        # Margin is the % of equity we're committing
        margin = equity * (risk_pct / 100.0)

        # Position size = margin × leverage (Bybit formula)
        size_usdt = margin * max_lev

        # Cap at max allowed position (equity × max_leverage)
        max_size = equity * max_lev
        was_capped = size_usdt > max_size
        size_usdt = min(size_usdt, max_size)

        return SizingResult(
            size_usdt=size_usdt,
            method="percent_equity",
            details=f"margin=${margin:.2f}, lev={max_lev:.1f}x, position=${size_usdt:.2f}, capped={was_capped}"
        )

    def _size_risk_based(
        self,
        snapshot: "RuntimeSnapshotView",
        signal: Signal,
    ) -> SizingResult:
        """
        Size using risk-based calculation.

        Computes position size based on account risk percentage and stop distance:
        - risk_dollars = equity × (risk_per_trade_pct / 100)
        - size = risk_dollars × entry_price / stop_distance

        This sizes the position so that if stopped out, you lose exactly risk_pct% of equity.

        Example:
        - $10,000 equity, 1% risk = $100 at risk
        - Entry $64,200, Stop $62,916 (2% stop) = $1,284 stop distance
        - size = $100 × $64,200 / $1,284 = $5,000 position

        If stopped out: $5,000 × 2% = $100 loss = 1% of equity

        Requires stop_loss in signal metadata. Falls back to percent_equity if missing.
        """
        equity = self._equity
        risk_pct = self._profile.risk_per_trade_pct
        max_lev = self._profile.max_leverage

        # Maximum size based on leverage
        max_size = equity * max_lev

        # Risk dollars (what we're willing to lose)
        risk_dollars = equity * (risk_pct / 100.0)

        # Get entry price from snapshot
        entry_price = snapshot.close

        # Get stop loss from signal metadata
        stop_loss = None
        if signal.metadata:
            stop_loss = signal.metadata.get("stop_loss")
            entry_price = signal.metadata.get("entry_price", entry_price)

        if stop_loss is not None and entry_price > 0:
            stop_distance = abs(entry_price - stop_loss)

            if stop_distance > 0:
                # Risk-based sizing: size = risk$ × entry / stop_distance
                size_usdt = risk_dollars * entry_price / stop_distance
                was_capped = size_usdt > max_size
                size_usdt = min(size_usdt, max_size)

                return SizingResult(
                    size_usdt=size_usdt,
                    method="risk_based",
                    details=f"risk=${risk_dollars:.2f}, stop_dist={stop_distance:.4f}, capped={was_capped}"
                )

        # Fallback to percent_equity with leverage if no valid stop
        margin = equity * (risk_pct / 100.0)
        size_usdt = margin * max_lev
        was_capped = size_usdt > max_size
        size_usdt = min(size_usdt, max_size)

        return SizingResult(
            size_usdt=size_usdt,
            method="risk_based_fallback",
            details=f"no stop_loss, using percent_equity fallback (lev={max_lev}x)"
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
