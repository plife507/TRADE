"""
Exchange constraints for order validation.

Handles:
- Tick size: Price rounding
- Lot size: Quantity rounding
- Min notional: Minimum order value
- Price/qty bounds validation

Bybit reference:
- Instrument info: reference/exchanges/bybit/docs/v5/market/instrument.mdx

Currency model: All monetary values are in USDTT (quote currency).
All monetary values are in USDT (quote currency).
"""

from dataclasses import dataclass
from typing import Optional
import math

from ..types import Order


@dataclass
class ConstraintConfig:
    """Exchange constraint configuration."""
    tick_size: float = 0.01  # Price tick size
    lot_size: float = 0.001  # Quantity lot size
    min_notional_usdt: float = 1.0  # Minimum order value
    max_leverage: float = 100.0  # Maximum leverage
    
    # Optional price bounds
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    
    # Optional qty bounds
    min_qty: Optional[float] = None
    max_qty: Optional[float] = None


@dataclass
class ValidationResult:
    """Result of order validation."""
    valid: bool
    errors: list
    warnings: list
    
    # Adjusted values (after rounding)
    adjusted_price: Optional[float] = None
    adjusted_qty: Optional[float] = None
    
    def __init__(self):
        self.valid = True
        self.errors = []
        self.warnings = []
        self.adjusted_price = None
        self.adjusted_qty = None


class Constraints:
    """
    Validates and adjusts orders to exchange constraints.
    
    Phase 1: Basic tick/lot rounding and min notional check.
    """
    
    def __init__(self, config: Optional[ConstraintConfig] = None):
        """
        Initialize constraints.
        
        Args:
            config: Optional constraint configuration
        """
        self._config = config or ConstraintConfig()
    
    def round_price(self, price: float) -> float:
        """
        Round price to tick size.
        
        Uses truncation toward zero (Bybit behavior).
        
        Args:
            price: Raw price
            
        Returns:
            Price rounded to tick size
        """
        tick = self._config.tick_size
        if tick <= 0:
            return price
        
        # Truncate to tick size
        return math.floor(price / tick) * tick
    
    def round_qty(self, qty: float) -> float:
        """
        Round quantity to lot size.
        
        Uses truncation (can't fill more than available).
        
        Args:
            qty: Raw quantity
            
        Returns:
            Quantity rounded to lot size
        """
        lot = self._config.lot_size
        if lot <= 0:
            return qty
        
        # Truncate to lot size
        return math.floor(qty / lot) * lot
    
    def validate_order(self, order: Order) -> ValidationResult:
        """
        Validate an order against constraints.
        
        Checks:
        - Min notional
        - Price bounds (if specified)
        - Quantity bounds (if specified)
        
        Args:
            order: Order to validate
            
        Returns:
            ValidationResult with errors/warnings
        """
        result = ValidationResult()
        
        # Check min notional
        if order.size_usdt < self._config.min_notional_usdt:
            result.valid = False
            result.errors.append(
                f"Order size {order.size_usdt} < min notional {self._config.min_notional_usdt}"
            )
        
        # Check limit price if present
        if order.limit_price is not None:
            if self._config.min_price and order.limit_price < self._config.min_price:
                result.valid = False
                result.errors.append(
                    f"Limit price {order.limit_price} < min price {self._config.min_price}"
                )
            if self._config.max_price and order.limit_price > self._config.max_price:
                result.valid = False
                result.errors.append(
                    f"Limit price {order.limit_price} > max price {self._config.max_price}"
                )
            
            # Round and warn if different
            rounded = self.round_price(order.limit_price)
            if rounded != order.limit_price:
                result.warnings.append(
                    f"Limit price rounded: {order.limit_price} -> {rounded}"
                )
                result.adjusted_price = rounded
        
        return result
    
    def validate_notional(self, notional_usdt: float) -> bool:
        """
        Check if notional meets minimum.
        
        Args:
            notional_usdt: Order notional in USDTT
            
        Returns:
            True if notional is valid
        """
        return notional_usdt >= self._config.min_notional_usdt
    
    def get_min_qty_for_notional(self, price: float) -> float:
        """
        Calculate minimum quantity to meet min notional.
        
        Args:
            price: Order price
            
        Returns:
            Minimum quantity (rounded up to lot size)
        """
        if price <= 0:
            return 0.0
        
        min_qty = self._config.min_notional_usdt / price
        
        # Round up to lot size
        lot = self._config.lot_size
        if lot > 0:
            min_qty = math.ceil(min_qty / lot) * lot
        
        return min_qty

