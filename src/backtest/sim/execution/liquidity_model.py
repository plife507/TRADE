"""
Liquidity model for partial fill constraints.

Caps order fills based on available liquidity:
- Max fillable = fraction of bar volume
- Orders larger than liquidity get partially filled

Volume is used ONLY for liquidity estimation,
NEVER for directional inference.

Currency model: All monetary values are in USDTT (quote currency).
All monetary values are in USDT (quote currency).
"""

from dataclasses import dataclass
from typing import Optional

from ..types import Bar


@dataclass
class LiquidityConfig:
    """Configuration for liquidity model."""
    mode: str = "disabled"  # "disabled", "volume_fraction"
    
    # Volume fraction params
    max_volume_fraction: float = 0.10  # Max 10% of bar volume per order
    min_fill_usdt: float = 1.0  # Minimum fill size


class LiquidityModel:
    """
    Estimates maximum fillable size based on liquidity.
    
    CRITICAL: Volume is used ONLY for liquidity estimation,
    NEVER to infer buy/sell direction.
    """
    
    def __init__(self, config: Optional[LiquidityConfig] = None):
        """
        Initialize liquidity model.
        
        Args:
            config: Optional configuration
        """
        self._config = config or LiquidityConfig()
    
    def get_max_fillable(
        self,
        size_usdt: float,
        bar: Bar,
    ) -> float:
        """
        Calculate maximum fillable size for an order.
        
        Returns min(size_usdt, max_liquidity).
        
        Args:
            size_usdt: Requested order size in USDT
            bar: Bar with volume data
            
        Returns:
            Maximum fillable size in USDT
        """
        if self._config.mode == "disabled":
            return size_usdt
        
        # Estimate bar volume in USDT
        bar_volume_usdt = bar.volume * bar.close
        
        if bar_volume_usdt <= 0:
            # No volume data: allow full fill
            return size_usdt
        
        # Max fillable = bar_volume × fraction
        max_liquidity = bar_volume_usdt * self._config.max_volume_fraction
        
        # Ensure minimum fill size
        max_liquidity = max(max_liquidity, self._config.min_fill_usdt)
        
        # Return min of requested and available
        return min(size_usdt, max_liquidity)
    
    def would_be_partial_fill(
        self,
        size_usdt: float,
        bar: Bar,
    ) -> bool:
        """
        Check if order would be partially filled.
        
        Args:
            size_usdt: Order size in USDT
            bar: Bar with volume data
            
        Returns:
            True if order would be partially filled
        """
        if self._config.mode == "disabled":
            return False
        
        max_fillable = self.get_max_fillable(size_usdt, bar)
        return max_fillable < size_usdt
    
    def get_unfilled_amount(
        self,
        size_usdt: float,
        bar: Bar,
    ) -> float:
        """
        Calculate unfilled amount for an order.
        
        Args:
            size_usdt: Order size in USDT
            bar: Bar with volume data
            
        Returns:
            Unfilled amount in USDT (0 if fully filled)
        """
        max_fillable = self.get_max_fillable(size_usdt, bar)
        return max(0.0, size_usdt - max_fillable)

