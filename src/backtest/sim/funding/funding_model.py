"""
Funding rate application model.

Applies funding events to open positions:
- Positive rate: longs pay shorts
- Negative rate: shorts pay longs

Funding calculation (Bybit-aligned):
  funding_pnl = position_size × mark_price × funding_rate × direction
  where direction = -1 for longs, +1 for shorts

Note: Bybit uses mark price at funding time, NOT entry price.
Note: No ADL (auto-deleveraging) in this implementation.

Bybit reference:
- Funding: reference/exchanges/bybit/docs/v5/market/history-fund-rate.mdx
"""

from dataclasses import dataclass
from datetime import datetime

from ..types import (
    Position,
    FundingEvent,
    FundingResult,
    OrderSide,
)


@dataclass
class FundingModelConfig:
    """Configuration for funding model."""
    enabled: bool = True
    # No ADL in Phase 1


class FundingModel:
    """
    Applies funding rate events to positions.
    
    Funding direction:
    - Positive rate: longs pay, shorts receive
    - Negative rate: shorts pay, longs receive
    """
    
    def __init__(self, config: FundingModelConfig | None = None):
        """
        Initialize funding model.
        
        Args:
            config: Optional configuration
        """
        self._config = config or FundingModelConfig()
    
    def apply_events(
        self,
        events: list[FundingEvent],
        prev_ts: datetime | None,
        ts: datetime,
        position: Position | None,
        mark_price: float,
    ) -> FundingResult:
        """
        Apply funding events to a position.

        Only events in the time window (prev_ts, ts] are applied.

        Args:
            events: List of funding events (should be pre-filtered to window)
            prev_ts: Previous bar timestamp (exclusive bound)
            ts: Current bar timestamp (inclusive bound)
            position: Current open position (or None)
            mark_price: Mark price at funding time (Bybit uses this, not entry price)

        Returns:
            FundingResult with total funding PnL
        """
        result = FundingResult()

        if not self._config.enabled:
            return result

        if position is None:
            return result

        if not events:
            return result

        total_funding = 0.0

        for event in events:
            # Filter to time window (should already be filtered, but double-check)
            if prev_ts is not None and event.timestamp <= prev_ts:
                continue
            if event.timestamp > ts:
                continue

            # Calculate funding payment
            funding_pnl = self._calculate_funding(position, event, mark_price)
            total_funding += funding_pnl
            result.events_applied.append(event)

        result.funding_pnl = total_funding

        return result
    
    def _calculate_funding(
        self,
        position: Position,
        event: FundingEvent,
        mark_price: float,
    ) -> float:
        """
        Calculate funding payment for a single event.

        Funding calculation (Bybit-aligned):
        - Position value = size × mark_price (NOT entry_price)
        - Funding payment = position_value × funding_rate × direction
        - Direction: longs pay positive rates (-1), shorts receive (+1)

        Args:
            position: Open position
            event: Funding event
            mark_price: Mark price at funding time

        Returns:
            Funding PnL (positive = received, negative = paid)
        """
        # Position value at mark price (Bybit uses mark price, not entry price)
        price = mark_price
        position_value = position.size * price

        # Direction: longs pay positive funding, shorts receive
        if position.side == OrderSide.LONG:
            direction = -1.0  # Longs pay on positive rate
        else:
            direction = 1.0  # Shorts receive on positive rate

        # Funding PnL
        funding_pnl = position_value * event.funding_rate * direction

        return funding_pnl
    
    def filter_events_for_window(
        self,
        events: list[FundingEvent],
        prev_ts: datetime | None,
        ts: datetime,
    ) -> list[FundingEvent]:
        """
        Filter funding events to time window (prev_ts, ts].
        
        Args:
            events: All funding events
            prev_ts: Previous timestamp (exclusive)
            ts: Current timestamp (inclusive)
            
        Returns:
            Events within the time window
        """
        filtered = []
        
        for event in events:
            if prev_ts is not None and event.timestamp <= prev_ts:
                continue
            if event.timestamp > ts:
                continue
            filtered.append(event)
        
        return filtered

