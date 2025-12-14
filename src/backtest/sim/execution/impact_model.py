"""
Market impact model.

Estimates price impact from order size relative to volume:
- Large orders relative to volume = higher impact
- Impact is additive to slippage

Volume is used ONLY for liquidity/impact estimation,
NEVER for directional inference.

Currency model: All monetary values are in USDTT (quote currency).
All monetary values are in USDT (quote currency).
"""

from dataclasses import dataclass
from typing import Optional

from ..types import Bar


@dataclass
class ImpactConfig:
    """Configuration for impact model."""
    mode: str = "disabled"  # "disabled", "linear", "sqrt"
    
    # Impact params
    linear_factor: float = 0.1  # Impact per % of volume
    sqrt_factor: float = 0.05  # Impact sqrt scaling
    max_impact_bps: float = 100.0  # Cap on impact (1%)


class ImpactModel:
    """
    Estimates market impact from order size vs volume.
    
    Impact is expressed as a multiplier on base slippage.
    
    CRITICAL: Volume is used ONLY for liquidity/impact,
    NEVER to infer buy/sell direction.
    """
    
    def __init__(self, config: Optional[ImpactConfig] = None):
        """
        Initialize impact model.
        
        Args:
            config: Optional configuration
        """
        self._config = config or ImpactConfig()
    
    def get_impact_multiplier(
        self,
        size_usdt: float,
        bar: Bar,
    ) -> float:
        """
        Calculate impact multiplier for slippage scaling.
        
        Returns multiplier >= 1.0 (no impact = 1.0).
        
        Args:
            size_usdt: Order size in USDT
            bar: Bar with volume data
            
        Returns:
            Impact multiplier (>= 1.0)
        """
        if self._config.mode == "disabled":
            return 1.0
        
        # Estimate bar volume in USDT (volume × typical price)
        bar_volume_usdt = bar.volume * bar.close
        
        if bar_volume_usdt <= 0:
            return 1.0
        
        # Order size as fraction of bar volume
        volume_fraction = size_usdt / bar_volume_usdt
        
        if self._config.mode == "linear":
            # Linear impact: multiplier = 1 + (volume_fraction × factor)
            impact = 1.0 + (volume_fraction * self._config.linear_factor)
        elif self._config.mode == "sqrt":
            # Sqrt impact: multiplier = 1 + sqrt(volume_fraction) × factor
            import math
            impact = 1.0 + (math.sqrt(volume_fraction) * self._config.sqrt_factor)
        else:
            impact = 1.0
        
        # Cap impact
        max_multiplier = 1.0 + (self._config.max_impact_bps / 10000.0)
        return min(impact, max_multiplier)
    
    def get_impact_bps(
        self,
        size_usdt: float,
        bar: Bar,
        base_slippage_bps: float,
    ) -> float:
        """
        Calculate total impact in basis points.
        
        Total = base_slippage_bps × impact_multiplier
        
        Args:
            size_usdt: Order size in USDT
            bar: Bar with volume data
            base_slippage_bps: Base slippage in bps
            
        Returns:
            Total slippage + impact in bps
        """
        multiplier = self.get_impact_multiplier(size_usdt, bar)
        return base_slippage_bps * multiplier

