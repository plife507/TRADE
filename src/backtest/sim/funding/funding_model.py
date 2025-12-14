"""
Funding rate application model.

Applies funding events to open positions:
- Positive rate: longs pay shorts
- Negative rate: shorts pay longs

Funding calculation:
  funding_pnl = position_size × entry_price × funding_rate × direction
  where direction = -1 for longs, +1 for shorts

Note: No ADL (auto-deleveraging) in this implementation.

Bybit reference:
- Funding: reference/exchanges/bybit/docs/v5/market/history-fund-rate.mdx
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List

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
    
    def __init__(self, config: Optional[FundingModelConfig] = None):
        """
        Initialize funding model.
        
        Args:
            config: Optional configuration
        """
        self._config = config or FundingModelConfig()
    
    def apply_events(
        self,
        events: List[FundingEvent],
        prev_ts: Optional[datetime],
        ts: datetime,
        position: Optional[Position],
    ) -> FundingResult:
        """
        Apply funding events to a position.
        
        Only events in the time window (prev_ts, ts] are applied.
        
        Args:
            events: List of funding events (should be pre-filtered to window)
            prev_ts: Previous bar timestamp (exclusive bound)
            ts: Current bar timestamp (inclusive bound)
            position: Current open position (or None)
            
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
            funding_pnl = self._calculate_funding(position, event)
            total_funding += funding_pnl
            result.events_applied.append(event)
        
        result.funding_pnl = total_funding
        
        return result
    
    def _calculate_funding(
        self,
        position: Position,
        event: FundingEvent,
    ) -> float:
        """
        Calculate funding payment for a single event.
        
        Funding calculation:
        - Position value = size × entry_price
        - Funding payment = position_value × funding_rate × direction
        - Direction: longs pay positive rates (-1), shorts receive (+1)
        
        Args:
            position: Open position
            event: Funding event
            
        Returns:
            Funding PnL (positive = received, negative = paid)
        """
        # Position value at entry
        position_value = position.size * position.entry_price
        
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
        events: List[FundingEvent],
        prev_ts: Optional[datetime],
        ts: datetime,
    ) -> List[FundingEvent]:
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

