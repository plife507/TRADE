"""
Intrabar price path generation.

Generates deterministic price paths within a bar for TP/SL checking.

Path models:
- Conservative: SL checked before TP (worst-case scenario)
- OHLC-consistent: Path respects bar OHLC bounds

Determinism:
- Same bar always produces same path (no randomness)
- Optional seed for reproducible stochastic paths (future)

Tie-break rules:
- For longs: assume price goes down first (SL before TP)
- For shorts: assume price goes up first (SL before TP)
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, List

from ..types import Bar, PricePoint, OrderSide, FillReason
from ..bar_compat import get_bar_ts_open


@dataclass
class IntrabarPathConfig:
    """Configuration for intrabar path generation."""
    mode: str = "conservative"  # "conservative" or "neutral"
    num_points: int = 4  # Number of points in path (O, H, L, C)


class IntrabarPath:
    """
    Generates deterministic intrabar price paths.
    
    Used for TP/SL checking within a bar. Path is OHLC-consistent
    and follows conservative tie-break rules.
    """
    
    def __init__(self, config: Optional[IntrabarPathConfig] = None):
        """
        Initialize intrabar path generator.
        
        Args:
            config: Optional configuration
        """
        self._config = config or IntrabarPathConfig()
    
    def generate_path(
        self,
        bar: Bar,
        seed: Optional[int] = None,
    ) -> List[PricePoint]:
        """
        Generate deterministic price path within a bar.
        
        Conservative ordering for tie-break:
        - For longs: O -> L -> H -> C (down first)
        - For shorts: O -> H -> L -> C (up first)
        
        Since we don't know position side here, we generate
        a neutral path: O -> L -> H -> C (same for all).
        The check_tp_sl method handles side-specific tie-break.
        
        Args:
            bar: OHLC bar (legacy or canonical)
            seed: Optional seed for reproducibility (not used in conservative mode)
            
        Returns:
            List of PricePoint representing intrabar path
        """
        ts = get_bar_ts_open(bar)
        
        # For time interpolation within the bar
        # Assume 1-minute increments (actual TF doesn't matter for ordering)
        delta = timedelta(seconds=15)
        
        # Conservative neutral path: O -> L -> H -> C
        # This ensures SL is checked at L for longs, H for shorts
        path = [
            PricePoint(timestamp=ts, price=bar.open, sequence=0),
            PricePoint(timestamp=ts + delta, price=bar.low, sequence=1),
            PricePoint(timestamp=ts + delta * 2, price=bar.high, sequence=2),
            PricePoint(timestamp=ts + delta * 3, price=bar.close, sequence=3),
        ]
        
        return path
    
    def generate_path_for_side(
        self,
        bar: Bar,
        side: OrderSide,
    ) -> List[PricePoint]:
        """
        Generate price path optimized for a specific position side.
        
        Conservative tie-break:
        - For longs: O -> L -> H -> C (SL at low first, then TP at high)
        - For shorts: O -> H -> L -> C (SL at high first, then TP at low)
        
        Args:
            bar: OHLC bar (legacy or canonical)
            side: Position side (for tie-break)
            
        Returns:
            List of PricePoint representing intrabar path
        """
        ts = get_bar_ts_open(bar)
        delta = timedelta(seconds=15)
        
        if side == OrderSide.LONG:
            # Long: check SL (low) before TP (high)
            # Path: O -> L -> H -> C
            path = [
                PricePoint(timestamp=ts, price=bar.open, sequence=0),
                PricePoint(timestamp=ts + delta, price=bar.low, sequence=1),
                PricePoint(timestamp=ts + delta * 2, price=bar.high, sequence=2),
                PricePoint(timestamp=ts + delta * 3, price=bar.close, sequence=3),
            ]
        else:
            # Short: check SL (high) before TP (low)
            # Path: O -> H -> L -> C
            path = [
                PricePoint(timestamp=ts, price=bar.open, sequence=0),
                PricePoint(timestamp=ts + delta, price=bar.high, sequence=1),
                PricePoint(timestamp=ts + delta * 2, price=bar.low, sequence=2),
                PricePoint(timestamp=ts + delta * 3, price=bar.close, sequence=3),
            ]
        
        return path
    
    def check_tp_sl(
        self,
        bar: Bar,
        side: OrderSide,
        entry_price: float,
        tp: Optional[float],
        sl: Optional[float],
    ) -> Optional[FillReason]:
        """
        Check if TP or SL is hit within the bar.
        
        Uses conservative tie-break: SL is checked first.
        
        Args:
            bar: OHLC bar (legacy or canonical)
            side: Position side
            entry_price: Entry price (not used in current logic)
            tp: Take profit price (or None)
            sl: Stop loss price (or None)
            
        Returns:
            FillReason.TAKE_PROFIT, FillReason.STOP_LOSS, or None
        """
        sl_hit = False
        tp_hit = False
        
        if side == OrderSide.LONG:
            # For longs: SL below entry, TP above entry
            if sl is not None and bar.low <= sl:
                sl_hit = True
            if tp is not None and bar.high >= tp:
                tp_hit = True
            
            # Conservative tie-break: SL first
            if sl_hit:
                return FillReason.STOP_LOSS
            if tp_hit:
                return FillReason.TAKE_PROFIT
        
        else:  # SHORT
            # For shorts: SL above entry, TP below entry
            if sl is not None and bar.high >= sl:
                sl_hit = True
            if tp is not None and bar.low <= tp:
                tp_hit = True
            
            # Conservative tie-break: SL first
            if sl_hit:
                return FillReason.STOP_LOSS
            if tp_hit:
                return FillReason.TAKE_PROFIT
        
        return None
    
    def get_exit_price(
        self,
        bar: Bar,
        side: OrderSide,
        reason: FillReason,
        tp: Optional[float],
        sl: Optional[float],
    ) -> float:
        """
        Get the exit price for a TP/SL fill.
        
        Args:
            bar: OHLC bar (legacy or canonical)
            side: Position side
            reason: FillReason (STOP_LOSS or TAKE_PROFIT)
            tp: Take profit price
            sl: Stop loss price
            
        Returns:
            Exit price
        """
        if reason == FillReason.STOP_LOSS:
            return sl if sl is not None else bar.close
        elif reason == FillReason.TAKE_PROFIT:
            return tp if tp is not None else bar.close
        else:
            return bar.close

