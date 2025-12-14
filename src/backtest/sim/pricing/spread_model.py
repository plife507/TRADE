"""
Spread model for bid-ask spread estimation.

Provides fixed or volume-based spread proxy:
- Fixed: Configurable constant spread
- Dynamic: Volume-based spread (future enhancement)

Spread is expressed in price units (not percentage).
"""

from dataclasses import dataclass
from typing import Optional, Tuple

from ..types import Bar


@dataclass
class SpreadConfig:
    """Configuration for spread model."""
    mode: str = "fixed"  # "fixed" or "dynamic"
    fixed_spread_bps: float = 2.0  # Fixed spread in basis points
    
    # Dynamic mode params (future)
    volume_multiplier: float = 1.0
    min_spread_bps: float = 1.0
    max_spread_bps: float = 20.0


class SpreadModel:
    """
    Estimates bid-ask spread from bar data.
    
    Phase 1 supports fixed spread only.
    """
    
    def __init__(self, config: Optional[SpreadConfig] = None):
        """
        Initialize spread model.
        
        Args:
            config: Optional configuration
        """
        self._config = config or SpreadConfig()
    
    def get_spread(self, bar: Bar) -> float:
        """
        Get spread for a bar in price units.
        
        Args:
            bar: OHLC bar
            
        Returns:
            Spread in price units
        """
        if self._config.mode == "fixed":
            return self._fixed_spread(bar)
        elif self._config.mode == "dynamic":
            return self._dynamic_spread(bar)
        else:
            # Default to fixed
            return self._fixed_spread(bar)
    
    def _fixed_spread(self, bar: Bar) -> float:
        """
        Calculate fixed spread based on config.
        
        Spread = mid_price × (spread_bps / 10000)
        
        Args:
            bar: OHLC bar
            
        Returns:
            Fixed spread in price units
        """
        mid = bar.close  # Use close as mid proxy
        return mid * (self._config.fixed_spread_bps / 10000.0)
    
    def _dynamic_spread(self, bar: Bar) -> float:
        """
        Calculate dynamic spread based on volume.
        
        Higher volume = tighter spread (more liquidity).
        
        Future enhancement - currently returns fixed spread.
        
        Args:
            bar: OHLC bar
            
        Returns:
            Dynamic spread in price units
        """
        # Placeholder: return fixed spread for now
        # Future: implement volume-based spread model
        return self._fixed_spread(bar)
    
    def get_bid_ask(self, mid: float, spread: float) -> Tuple[float, float]:
        """
        Derive bid and ask prices from mid and spread.
        
        Args:
            mid: Mid price
            spread: Spread in price units
            
        Returns:
            Tuple of (bid_price, ask_price)
        """
        half_spread = spread / 2.0
        bid = mid - half_spread
        ask = mid + half_spread
        return (bid, ask)

