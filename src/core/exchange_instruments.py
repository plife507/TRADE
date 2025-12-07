"""
Instrument information and trading helpers for ExchangeManager.

Handles:
- Instrument info caching (tick sizes, lot sizes)
- Price rounding to valid tick sizes
- Quantity calculation from USD amounts
- Price precision utilities
"""

from typing import Dict, TYPE_CHECKING
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP

if TYPE_CHECKING:
    from .exchange_manager import ExchangeManager


def get_instrument_info(manager: "ExchangeManager", symbol: str) -> dict:
    """Get and cache instrument specifications."""
    if symbol not in manager._instruments:
        instruments = manager.bybit.get_instruments(symbol)
        if instruments:
            manager._instruments[symbol] = instruments[0]
    return manager._instruments.get(symbol, {})


def round_price(manager: "ExchangeManager", symbol: str, price: float) -> float:
    """
    Round price to valid tick size for symbol.
    
    Args:
        manager: ExchangeManager instance
        symbol: Trading symbol
        price: Price to round
    
    Returns:
        Price rounded to valid tick size
    """
    info = get_instrument_info(manager, symbol)
    price_filter = info.get("priceFilter", {})
    tick_size = float(price_filter.get("tickSize", "0.01"))
    
    # Round to tick size
    rounded = float(Decimal(str(price)).quantize(
        Decimal(str(tick_size)), 
        rounding=ROUND_HALF_UP
    ))
    return rounded


def get_tick_size(manager: "ExchangeManager", symbol: str) -> float:
    """Get the minimum price increment for a symbol."""
    info = get_instrument_info(manager, symbol)
    price_filter = info.get("priceFilter", {})
    return float(price_filter.get("tickSize", "0.01"))


def get_min_qty(manager: "ExchangeManager", symbol: str) -> float:
    """Get the minimum order quantity for a symbol."""
    info = get_instrument_info(manager, symbol)
    lot_size = info.get("lotSizeFilter", {})
    return float(lot_size.get("minOrderQty", "0.001"))


def calculate_qty(
    manager: "ExchangeManager",
    symbol: str,
    usd_amount: float,
    price: float = None
) -> float:
    """
    Calculate order quantity from USD amount.
    
    Args:
        manager: ExchangeManager instance
        symbol: Trading symbol
        usd_amount: Amount in USD
        price: Price to use (None = current market price)
    
    Returns:
        Quantity in contracts/coins, rounded to valid precision
    """
    if price is None:
        price = manager.get_price(symbol)
    
    if price <= 0:
        raise ValueError(f"Invalid price for {symbol}: {price}")
    
    # Get instrument info for precision
    info = get_instrument_info(manager, symbol)
    lot_size = info.get("lotSizeFilter", {})
    
    qty_step = float(lot_size.get("qtyStep", "0.001"))
    min_qty = float(lot_size.get("minOrderQty", "0.001"))
    
    # Calculate base quantity
    qty = usd_amount / price
    
    # Round down to step size
    qty = float(Decimal(str(qty)).quantize(Decimal(str(qty_step)), rounding=ROUND_DOWN))
    
    # Ensure minimum
    if qty < min_qty:
        manager.logger.warning(f"Order size {qty} below minimum {min_qty} for {symbol}")
        return 0.0
    
    return qty


def get_price_precision(manager: "ExchangeManager", symbol: str) -> int:
    """Get price decimal precision for a symbol."""
    info = get_instrument_info(manager, symbol)
    tick_size = info.get("priceFilter", {}).get("tickSize", "0.01")
    # Count decimal places
    if "." in tick_size:
        return len(tick_size.split(".")[1].rstrip("0"))
    return 2

