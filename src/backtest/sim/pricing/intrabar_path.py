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

from ..types import Bar, PricePoint, PriceSnapshot, OrderSide, FillReason, TriggerSource


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
    
    def __init__(self, config: IntrabarPathConfig | None = None):
        """
        Initialize intrabar path generator.
        
        Args:
            config: Optional configuration
        """
        self._config = config or IntrabarPathConfig()
    
    def generate_path(
        self,
        bar: Bar,
        seed: int | None = None,
    ) -> list[PricePoint]:
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
        ts = bar.ts_open
        
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
    ) -> list[PricePoint]:
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
        ts = bar.ts_open
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
        tp: float | None,
        sl: float | None,
        tp_trigger_by: TriggerSource = TriggerSource.LAST_PRICE,
        sl_trigger_by: TriggerSource = TriggerSource.LAST_PRICE,
        prices: PriceSnapshot | None = None,
    ) -> FillReason | None:
        """
        Check if TP or SL is hit within the bar.

        Uses conservative tie-break: SL is checked first.

        Trigger source behavior:
        - LAST_PRICE: check bar.high/bar.low (full intrabar range)
        - MARK_PRICE: check prices.mark_price (single point, smoother)
        - INDEX_PRICE: check prices.index_price (single point)

        For MARK/INDEX, only a single price point is available per bar,
        so the check is whether that point crosses the level. This is
        conservative: mark/index never wick as far as last price.

        Args:
            bar: OHLC bar
            side: Position side
            entry_price: Entry price (not used in current logic)
            tp: Take profit price (or None)
            sl: Stop loss price (or None)
            tp_trigger_by: Price source for TP evaluation
            sl_trigger_by: Price source for SL evaluation
            prices: PriceSnapshot with mark/index (needed for non-LAST triggers)

        Returns:
            FillReason.TAKE_PROFIT, FillReason.STOP_LOSS, or None
        """
        # Resolve price ranges for each trigger source
        sl_high, sl_low = self._resolve_trigger_range(bar, sl_trigger_by, prices)
        tp_high, tp_low = self._resolve_trigger_range(bar, tp_trigger_by, prices)

        sl_hit = False
        tp_hit = False

        if side == OrderSide.LONG:
            # For longs: SL below entry, TP above entry
            if sl is not None and sl_low <= sl:
                sl_hit = True
            if tp is not None and tp_high >= tp:
                tp_hit = True

            # Conservative tie-break: SL first
            if sl_hit:
                return FillReason.STOP_LOSS
            if tp_hit:
                return FillReason.TAKE_PROFIT

        else:  # SHORT
            # For shorts: SL above entry, TP below entry
            if sl is not None and sl_high >= sl:
                sl_hit = True
            if tp is not None and tp_low <= tp:
                tp_hit = True

            # Conservative tie-break: SL first
            if sl_hit:
                return FillReason.STOP_LOSS
            if tp_hit:
                return FillReason.TAKE_PROFIT

        return None

    @staticmethod
    def _resolve_trigger_range(
        bar: Bar,
        trigger_by: TriggerSource,
        prices: PriceSnapshot | None,
    ) -> tuple[float, float]:
        """Resolve the (high, low) price range for a trigger source.

        - LAST_PRICE: full bar range (bar.high, bar.low)
        - MARK_PRICE: single point (mark, mark)
        - INDEX_PRICE: single point (index, index)

        Returns:
            (high, low) tuple for trigger comparison
        """
        if trigger_by == TriggerSource.LAST_PRICE:
            return bar.high, bar.low

        if prices is None:
            # No external prices available — fall back to bar OHLC
            return bar.high, bar.low

        if trigger_by == TriggerSource.MARK_PRICE:
            return prices.mark_price, prices.mark_price

        if trigger_by == TriggerSource.INDEX_PRICE:
            return prices.index_price, prices.index_price

        # Unreachable with current enum, but defensive
        return bar.high, bar.low
    
    def get_exit_price(
        self,
        bar: Bar,
        side: OrderSide,
        reason: FillReason,
        tp: float | None,
        sl: float | None,
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


def check_tp_sl_1m(
    position_side: str,
    entry_price: float,
    take_profit: float | None,
    stop_loss: float | None,
    bars_1m: list[tuple[float, float, float, float]],  # List of (open, high, low, close)
    tp_trigger_by: TriggerSource = TriggerSource.LAST_PRICE,
    sl_trigger_by: TriggerSource = TriggerSource.LAST_PRICE,
    prices: PriceSnapshot | None = None,
) -> tuple[str, int, float] | None:
    """Check TP/SL against each 1m bar in order.

    Iterates through 1m bars chronologically and checks if TP or SL
    is triggered. Uses conservative tie-break (SL checked before TP).

    For LAST_PRICE triggers: checks each 1m bar's high/low (granular).
    For MARK_PRICE/INDEX_PRICE triggers: only a single price point is
    available per exec bar (not per 1m bar), so we check that single
    point and report it as hitting on the first 1m bar (conservative
    timing). The caller should prefer the exec-bar-level check for
    non-LAST triggers when possible.

    Args:
        position_side: "long" or "short"
        entry_price: Position entry price
        take_profit: TP level or None
        stop_loss: SL level or None
        bars_1m: List of 1m bars as (open, high, low, close) tuples
        tp_trigger_by: Price source for TP evaluation
        sl_trigger_by: Price source for SL evaluation
        prices: PriceSnapshot with mark/index (for non-LAST triggers)

    Returns:
        Tuple of (reason, hit_bar_idx, exit_price) or None if no hit
        - reason: "stop_loss" or "take_profit"
        - hit_bar_idx: Index in bars_1m where hit occurred
        - exit_price: The TP or SL level that was hit
    """
    if take_profit is None and stop_loss is None:
        return None

    is_long = position_side.lower() == "long"

    # For non-LAST triggers, check the single mark/index point first.
    # If triggered, report as bar_idx=0 (earliest possible timing).
    sl_uses_last = sl_trigger_by == TriggerSource.LAST_PRICE
    tp_uses_last = tp_trigger_by == TriggerSource.LAST_PRICE

    if prices is not None:
        # Check SL on mark/index (single point, not per-1m)
        if not sl_uses_last and stop_loss is not None:
            sl_price = (prices.mark_price if sl_trigger_by == TriggerSource.MARK_PRICE
                        else prices.index_price)
            if is_long and sl_price <= stop_loss:
                return ("stop_loss", 0, stop_loss)
            if not is_long and sl_price >= stop_loss:
                return ("stop_loss", 0, stop_loss)

        # Check TP on mark/index (single point, not per-1m)
        if not tp_uses_last and take_profit is not None:
            tp_price = (prices.mark_price if tp_trigger_by == TriggerSource.MARK_PRICE
                        else prices.index_price)
            if is_long and tp_price >= take_profit:
                return ("take_profit", 0, take_profit)
            if not is_long and tp_price <= take_profit:
                return ("take_profit", 0, take_profit)

    # For LAST_PRICE triggers (or fallback), iterate 1m bars
    if not sl_uses_last and not tp_uses_last:
        # Both triggers already checked above via prices
        return None

    for idx, (_bar_open, bar_high, bar_low, _bar_close) in enumerate(bars_1m):
        # Conservative tie-break: check SL before TP
        if sl_uses_last and stop_loss is not None:
            if is_long and bar_low <= stop_loss:
                return ("stop_loss", idx, stop_loss)
            if not is_long and bar_high >= stop_loss:
                return ("stop_loss", idx, stop_loss)

        if tp_uses_last and take_profit is not None:
            if is_long and bar_high >= take_profit:
                return ("take_profit", idx, take_profit)
            if not is_long and bar_low <= take_profit:
                return ("take_profit", idx, take_profit)

    return None

