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
from typing import TYPE_CHECKING, Literal

from ..core.risk_manager import Signal
from .system_config import RiskProfileConfig
from .types import Trade

if TYPE_CHECKING:
    from .runtime.snapshot_view import RuntimeSnapshotView


@dataclass
class StopLiqValidationResult:
    """Result of SL vs liquidation validation."""
    valid: bool
    reason: str | None = None
    adjusted_stop: float | None = None  # Set if auto-adjusted
    liq_price: float | None = None
    sl_distance_pct: float | None = None
    liq_distance_pct: float | None = None


def calculate_liquidation_price_simple(
    entry_price: float,
    leverage: float,
    direction: int,  # 1 for long, -1 for short
    mmr: float = 0.004,  # Bybit maintenance margin rate (0.4%)
) -> float:
    """
    Calculate liquidation price for a leveraged position.

    Uses simplified formula assuming isolated margin where
    initial margin = entry × size / leverage = entry / leverage (for size=1).

    Derivation (long): cash + (liq - entry) = liq × MMR
      → cash = entry/leverage, so entry/leverage + liq - entry = liq × MMR
      → liq × (1 - MMR) = entry × (1 - 1/leverage)
      → liq = entry × (1 - 1/leverage) / (1 - MMR)

    Derivation (short): cash + (entry - liq) = liq × MMR
      → entry/leverage + entry - liq = liq × MMR
      → liq × (1 + MMR) = entry × (1 + 1/leverage)
      → liq = entry × (1 + 1/leverage) / (1 + MMR)

    Args:
        entry_price: Entry fill price
        leverage: Position leverage (e.g., 50 for 50x)
        direction: 1 for long, -1 for short
        mmr: Maintenance margin rate (default 0.4% for Bybit)

    Returns:
        Estimated liquidation price
    """
    if leverage <= 0:
        return 0.0

    imr = 1.0 / leverage  # Initial margin rate

    if direction == 1:  # Long
        denominator = 1.0 - mmr
        if denominator <= 0:
            return 0.0
        liq_price = entry_price * (1.0 - imr) / denominator
    else:  # Short
        denominator = 1.0 + mmr
        liq_price = entry_price * (1.0 + imr) / denominator

    return max(0.0, liq_price)


def validate_stop_vs_liquidation(
    entry_price: float,
    stop_price: float,
    direction: int,  # 1 for long, -1 for short
    leverage: float,
    mmr: float = 0.004,
    safety_buffer_pct: float = 0.1,  # 0.1% safety buffer
) -> StopLiqValidationResult:
    """
    Validate that stop-loss triggers before liquidation price.

    High leverage positions can get liquidated before SL fires if the
    stop distance exceeds the liquidation distance.

    Example: 50x leverage, 2% SL on long
    - Liquidation at ~1.6% (1/50 = 2% - 0.4% mmr)
    - 2% SL is BEYOND liquidation -> position liquidates first

    Args:
        entry_price: Entry fill price
        stop_price: Stop-loss price
        direction: 1 for long, -1 for short
        leverage: Position leverage
        mmr: Maintenance margin rate
        safety_buffer_pct: Extra buffer to ensure SL fires before liq

    Returns:
        StopLiqValidationResult with validation status
    """
    if entry_price <= 0 or stop_price <= 0:
        return StopLiqValidationResult(
            valid=False,
            reason="Invalid entry or stop price (must be > 0)",
        )

    liq_price = calculate_liquidation_price_simple(
        entry_price=entry_price,
        leverage=leverage,
        direction=direction,
        mmr=mmr,
    )

    # Calculate distances as percentages
    if direction == 1:  # Long
        sl_dist = entry_price - stop_price
        liq_dist = entry_price - liq_price
        sl_dist_pct = (sl_dist / entry_price) * 100
        liq_dist_pct = (liq_dist / entry_price) * 100

        # Check if SL is beyond (or at) liquidation
        # Add safety buffer to liquidation distance
        safe_liq_dist = liq_dist * (1 - safety_buffer_pct / 100)

        if sl_dist >= safe_liq_dist:
            # Calculate safe stop price (with buffer)
            safe_stop = entry_price - safe_liq_dist
            return StopLiqValidationResult(
                valid=False,
                reason=f"SL ${stop_price:.2f} ({sl_dist_pct:.2f}%) beyond liq ${liq_price:.2f} ({liq_dist_pct:.2f}%)",
                adjusted_stop=safe_stop,
                liq_price=liq_price,
                sl_distance_pct=sl_dist_pct,
                liq_distance_pct=liq_dist_pct,
            )
    else:  # Short
        sl_dist = stop_price - entry_price
        liq_dist = liq_price - entry_price
        sl_dist_pct = (sl_dist / entry_price) * 100
        liq_dist_pct = (liq_dist / entry_price) * 100

        # Check if SL is beyond (or at) liquidation
        safe_liq_dist = liq_dist * (1 - safety_buffer_pct / 100)

        if sl_dist >= safe_liq_dist:
            # Calculate safe stop price (with buffer)
            safe_stop = entry_price + safe_liq_dist
            return StopLiqValidationResult(
                valid=False,
                reason=f"SL ${stop_price:.2f} ({sl_dist_pct:.2f}%) beyond liq ${liq_price:.2f} ({liq_dist_pct:.2f}%)",
                adjusted_stop=safe_stop,
                liq_price=liq_price,
                sl_distance_pct=sl_dist_pct,
                liq_distance_pct=liq_dist_pct,
            )

    return StopLiqValidationResult(
        valid=True,
        liq_price=liq_price,
        sl_distance_pct=sl_dist_pct if direction == 1 else (stop_price - entry_price) / entry_price * 100,
        liq_distance_pct=liq_dist_pct if direction == 1 else (liq_price - entry_price) / entry_price * 100,
    )


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

        IMPORTANT: Position is capped by:
            1. max_position_equity_pct (default 95%) of equity
            2. Fee buffer reservation (entry + exit fees)
            3. equity × max_leverage (max borrowing)
        """
        equity = self._equity
        risk_pct = self._profile.risk_per_trade_pct
        max_lev = self._profile.max_leverage

        # Get caps from profile (with defaults)
        max_pos_pct = getattr(self._profile, "max_position_equity_pct", 95.0)
        reserve_fees = getattr(self._profile, "reserve_fee_buffer", True)
        taker_fee = self._profile.taker_fee_rate or 0.00055  # Default 5.5 bps

        # Cap 1: Maximum MARGIN as % of equity, then × leverage for notional
        # Matches SizingModel (Bybit isolated margin model)
        max_by_equity_pct = equity * (max_pos_pct / 100.0) * max_lev

        # Cap 2: Fee reservation
        # Reserve balance for entry fee + potential exit fee
        if reserve_fees:
            fee_factor = 1.0 + 2.0 * taker_fee  # Entry + exit fees
            max_by_fees = equity * max_lev / fee_factor
        else:
            max_by_fees = float("inf")

        # Cap 3: Leverage-based max
        max_by_leverage = equity * max_lev

        # Final max is the minimum of all caps
        max_size = min(max_by_equity_pct, max_by_fees, max_by_leverage)

        # Margin is the % of equity we're committing
        margin = equity * (risk_pct / 100.0)

        # Position size = margin × leverage (Bybit formula)
        size_usdt = margin * max_lev

        # Apply the cap
        was_capped = size_usdt > max_size
        size_usdt = min(size_usdt, max_size)

        # Build details string
        cap_reason = ""
        if was_capped:
            if max_size == max_by_equity_pct:
                cap_reason = f" (capped by {max_pos_pct}% equity)"
            elif max_size == max_by_fees:
                cap_reason = " (capped by fee reserve)"
            else:
                cap_reason = " (capped by leverage)"

        return SizingResult(
            size_usdt=size_usdt,
            method="percent_equity",
            details=f"margin=${margin:.2f}, lev={max_lev:.1f}x, position=${size_usdt:.2f}{cap_reason}"
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

        # Get caps from profile (with defaults)
        max_pos_pct = getattr(self._profile, "max_position_equity_pct", 95.0)
        reserve_fees = getattr(self._profile, "reserve_fee_buffer", True)
        taker_fee = self._profile.taker_fee_rate or 0.00055

        # Calculate max size with all caps
        max_by_equity_pct = equity * (max_pos_pct / 100.0)
        if reserve_fees:
            fee_factor = 1.0 + 2.0 * taker_fee
            max_by_fees = equity * max_lev / fee_factor
        else:
            max_by_fees = float("inf")
        max_by_leverage = equity * max_lev
        max_size = min(max_by_equity_pct, max_by_fees, max_by_leverage)

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

                cap_reason = ""
                if was_capped:
                    if max_size == max_by_equity_pct:
                        cap_reason = f" (capped by {max_pos_pct}% equity)"
                    elif max_size == max_by_fees:
                        cap_reason = " (capped by fee reserve)"
                    else:
                        cap_reason = " (capped by leverage)"

                return SizingResult(
                    size_usdt=size_usdt,
                    method="risk_based",
                    details=f"risk=${risk_dollars:.2f}, stop_dist={stop_distance:.4f}{cap_reason}"
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
