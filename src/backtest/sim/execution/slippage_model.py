"""
Slippage model for market order execution.

Applies price slippage based on:
- Fixed slippage (bps)
- Volume-based slippage (future enhancement)

Slippage direction:
- Buys (longs): pay more (price increases)
- Sells (shorts): receive less (price decreases)

Currency model: All monetary values are in USDTT (quote currency).
All monetary values are in USDT (quote currency).
"""

from dataclasses import dataclass
from typing import Optional

from ..types import Bar, OrderSide


@dataclass
class SlippageConfig:
    """Configuration for slippage model."""
    mode: str = "fixed"  # "fixed" or "volume_based"
    fixed_bps: float = 5.0  # Fixed slippage in basis points (0.05%)
    
    # Volume-based params (future)
    volume_scale_factor: float = 0.1
    min_bps: float = 1.0
    max_bps: float = 50.0


class SlippageModel:
    """
    Estimates execution slippage for market orders.
    
    Phase 1 supports fixed slippage only.
    """
    
    def __init__(self, config: Optional[SlippageConfig] = None):
        """
        Initialize slippage model.
        
        Args:
            config: Optional configuration
        """
        self._config = config or SlippageConfig()
    
    @property
    def slippage_rate(self) -> float:
        """Get slippage rate as decimal (e.g., 0.0005 for 5 bps)."""
        return self._config.fixed_bps / 10000.0
    
    def apply_slippage(
        self,
        price: float,
        side: OrderSide,
        size_usdt: Optional[float] = None,
        bar: Optional[Bar] = None,
    ) -> float:
        """
        Apply slippage to execution price.
        
        Slippage direction:
        - LONG (buy): price increases (pay more)
        - SHORT (sell entry) or LONG exit: price decreases (receive less)
        
        Args:
            price: Base execution price
            side: Order side
            size_usdt: Order size in USDT (for volume-based)
            bar: Bar data (for volume-based)
            
        Returns:
            Adjusted execution price with slippage
        """
        slippage_amount = self._calculate_slippage(price, size_usdt, bar)
        
        if side == OrderSide.LONG:
            # Buying: pay more
            return price + slippage_amount
        else:
            # Selling: receive less
            return price - slippage_amount
    
    def apply_exit_slippage(
        self,
        price: float,
        position_side: OrderSide,
        size_usdt: Optional[float] = None,
        bar: Optional[Bar] = None,
    ) -> float:
        """
        Apply slippage to exit price.
        
        Exit slippage is opposite to entry slippage:
        - Exiting LONG (selling): receive less
        - Exiting SHORT (buying to cover): pay more
        
        Args:
            price: Base exit price
            position_side: Position side being exited
            size_usdt: Position size in USDT
            bar: Bar data
            
        Returns:
            Adjusted exit price with slippage
        """
        slippage_amount = self._calculate_slippage(price, size_usdt, bar)
        
        if position_side == OrderSide.LONG:
            # Exiting long (selling): receive less
            return price - slippage_amount
        else:
            # Exiting short (buying): pay more
            return price + slippage_amount
    
    def _calculate_slippage(
        self,
        price: float,
        size_usdt: Optional[float] = None,
        bar: Optional[Bar] = None,
    ) -> float:
        """
        Calculate slippage amount.
        
        Args:
            price: Base price
            size_usdt: Order size (for volume-based)
            bar: Bar data (for volume-based)
            
        Returns:
            Slippage amount in price units
        """
        if self._config.mode == "fixed":
            return price * self.slippage_rate
        elif self._config.mode == "volume_based":
            # Future: implement volume-based slippage
            return price * self.slippage_rate
        else:
            return price * self.slippage_rate
    
    def get_slippage_bps(
        self,
        size_usdt: Optional[float] = None,
        bar: Optional[Bar] = None,
    ) -> float:
        """
        Get slippage in basis points.
        
        Args:
            size_usdt: Order size (for volume-based)
            bar: Bar data (for volume-based)
            
        Returns:
            Slippage in basis points
        """
        if self._config.mode == "fixed":
            return self._config.fixed_bps
        else:
            # Placeholder for volume-based
            return self._config.fixed_bps

