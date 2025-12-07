"""
CLI Menu handlers for TRADE trading bot.

Each menu module handles a specific area:
- account_menu: Account balance, portfolio, history
- positions_menu: Position management, TP/SL, margin
- orders_menu: Order placement and management
- market_data_menu: Market data queries
- data_menu: Historical data management
- diagnostics_menu: Connection tests, health checks
"""

from .data_menu import data_menu
from .market_data_menu import market_data_menu
from .orders_menu import orders_menu, market_orders_menu, limit_orders_menu, stop_orders_menu, manage_orders_menu
from .positions_menu import positions_menu
from .account_menu import account_menu

__all__ = [
    "data_menu",
    "market_data_menu",
    "orders_menu",
    "market_orders_menu",
    "limit_orders_menu",
    "stop_orders_menu",
    "manage_orders_menu",
    "positions_menu",
    "account_menu",
]
