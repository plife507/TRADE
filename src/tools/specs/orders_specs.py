"""
Order tool specifications.

Defines metadata for ToolRegistry to discover and validate order tools.

Pattern: Specs declare parameters/descriptions, get_imports() maps tool names
to actual functions. This separation allows specs to be introspectable without
importing heavy dependencies.
"""

from .shared_params import TRADING_ENV_PARAM, SYMBOL_PARAM


def get_imports():
    """Return dict of function_name -> actual function reference."""
    from .. import (
        market_buy_tool, market_sell_tool,
        market_buy_with_tpsl_tool, market_sell_with_tpsl_tool,
        limit_buy_tool, limit_sell_tool, partial_close_position_tool,
        stop_market_buy_tool, stop_market_sell_tool,
        stop_limit_buy_tool, stop_limit_sell_tool,
        get_open_orders_tool, cancel_order_tool, amend_order_tool, cancel_all_orders_tool,
    )
    return {
        "market_buy": market_buy_tool,
        "market_sell": market_sell_tool,
        "market_buy_with_tpsl": market_buy_with_tpsl_tool,
        "market_sell_with_tpsl": market_sell_with_tpsl_tool,
        "limit_buy": limit_buy_tool,
        "limit_sell": limit_sell_tool,
        "partial_close": partial_close_position_tool,
        "stop_market_buy": stop_market_buy_tool,
        "stop_market_sell": stop_market_sell_tool,
        "stop_limit_buy": stop_limit_buy_tool,
        "stop_limit_sell": stop_limit_sell_tool,
        "get_open_orders": get_open_orders_tool,
        "cancel_order": cancel_order_tool,
        "amend_order": amend_order_tool,
        "cancel_all_orders": cancel_all_orders_tool,
    }


SPECS = [
    # Market Orders
    {
        "name": "market_buy",
        "description": "Open a long position with a market buy order",
        "category": "orders.market",
        "parameters": {
            "symbol": SYMBOL_PARAM,
            "usd_amount": {"type": "number", "description": "Position size in USD"},
            "trading_env": TRADING_ENV_PARAM,
        },
        "required": ["symbol", "usd_amount"],
    },
    {
        "name": "market_sell",
        "description": "Open a short position with a market sell order",
        "category": "orders.market",
        "parameters": {
            "symbol": {"type": "string", "description": "Trading symbol"},
            "usd_amount": {"type": "number", "description": "Position size in USD"},
            "trading_env": TRADING_ENV_PARAM,
        },
        "required": ["symbol", "usd_amount"],
    },
    {
        "name": "market_buy_with_tpsl",
        "description": "Open long position with take profit and stop loss",
        "category": "orders.market",
        "parameters": {
            "symbol": {"type": "string", "description": "Trading symbol"},
            "usd_amount": {"type": "number", "description": "Position size in USD"},
            "take_profit": {"type": "number", "description": "Take profit price", "optional": True},
            "stop_loss": {"type": "number", "description": "Stop loss price", "optional": True},
            "trading_env": TRADING_ENV_PARAM,
        },
        "required": ["symbol", "usd_amount"],
    },
    {
        "name": "market_sell_with_tpsl",
        "description": "Open short position with take profit and stop loss",
        "category": "orders.market",
        "parameters": {
            "symbol": {"type": "string", "description": "Trading symbol"},
            "usd_amount": {"type": "number", "description": "Position size in USD"},
            "take_profit": {"type": "number", "description": "Take profit price", "optional": True},
            "stop_loss": {"type": "number", "description": "Stop loss price", "optional": True},
            "trading_env": TRADING_ENV_PARAM,
        },
        "required": ["symbol", "usd_amount"],
    },
    # Limit Orders
    {
        "name": "limit_buy",
        "description": "Place a limit buy order",
        "category": "orders.limit",
        "parameters": {
            "symbol": {"type": "string", "description": "Trading symbol"},
            "usd_amount": {"type": "number", "description": "Position size in USD"},
            "price": {"type": "number", "description": "Limit price"},
            "time_in_force": {"type": "string", "description": "GTC, IOC, FOK, or PostOnly", "default": "GTC"},
            "reduce_only": {"type": "boolean", "description": "Reduce-only order", "default": False},
            "trading_env": TRADING_ENV_PARAM,
        },
        "required": ["symbol", "usd_amount", "price"],
    },
    {
        "name": "limit_sell",
        "description": "Place a limit sell order",
        "category": "orders.limit",
        "parameters": {
            "symbol": {"type": "string", "description": "Trading symbol"},
            "usd_amount": {"type": "number", "description": "Position size in USD"},
            "price": {"type": "number", "description": "Limit price"},
            "time_in_force": {"type": "string", "description": "GTC, IOC, FOK, or PostOnly", "default": "GTC"},
            "reduce_only": {"type": "boolean", "description": "Reduce-only order", "default": False},
            "trading_env": TRADING_ENV_PARAM,
        },
        "required": ["symbol", "usd_amount", "price"],
    },
    {
        "name": "partial_close",
        "description": "Partially close a position by percentage",
        "category": "orders.limit",
        "parameters": {
            "symbol": {"type": "string", "description": "Trading symbol"},
            "close_percent": {"type": "number", "description": "Percentage to close (0-100)"},
            "price": {"type": "number", "description": "Limit price (None for market)", "optional": True},
            "trading_env": TRADING_ENV_PARAM,
        },
        "required": ["symbol", "close_percent"],
    },
    # Stop Orders
    {
        "name": "stop_market_buy",
        "description": "Place stop market buy (triggers when price rises/falls to trigger)",
        "category": "orders.stop",
        "parameters": {
            "symbol": {"type": "string", "description": "Trading symbol"},
            "usd_amount": {"type": "number", "description": "Position size in USD"},
            "trigger_price": {"type": "number", "description": "Price to trigger order"},
            "trigger_direction": {"type": "integer", "description": "1=rises to, 2=falls to", "default": 1},
            "reduce_only": {"type": "boolean", "description": "Reduce-only order", "default": False},
            "trading_env": TRADING_ENV_PARAM,
        },
        "required": ["symbol", "usd_amount", "trigger_price"],
    },
    {
        "name": "stop_market_sell",
        "description": "Place stop market sell (triggers when price rises/falls to trigger)",
        "category": "orders.stop",
        "parameters": {
            "symbol": {"type": "string", "description": "Trading symbol"},
            "usd_amount": {"type": "number", "description": "Position size in USD"},
            "trigger_price": {"type": "number", "description": "Price to trigger order"},
            "trigger_direction": {"type": "integer", "description": "1=rises to, 2=falls to", "default": 2},
            "reduce_only": {"type": "boolean", "description": "Reduce-only order", "default": False},
            "trading_env": TRADING_ENV_PARAM,
        },
        "required": ["symbol", "usd_amount", "trigger_price"],
    },
    {
        "name": "stop_limit_buy",
        "description": "Place stop limit buy (triggers limit order at trigger price)",
        "category": "orders.stop",
        "parameters": {
            "symbol": {"type": "string", "description": "Trading symbol"},
            "usd_amount": {"type": "number", "description": "Position size in USD"},
            "trigger_price": {"type": "number", "description": "Price to trigger order"},
            "limit_price": {"type": "number", "description": "Limit price for triggered order"},
            "trigger_direction": {"type": "integer", "description": "1=rises to, 2=falls to", "default": 1},
            "trading_env": TRADING_ENV_PARAM,
        },
        "required": ["symbol", "usd_amount", "trigger_price", "limit_price"],
    },
    {
        "name": "stop_limit_sell",
        "description": "Place stop limit sell (triggers limit order at trigger price)",
        "category": "orders.stop",
        "parameters": {
            "symbol": {"type": "string", "description": "Trading symbol"},
            "usd_amount": {"type": "number", "description": "Position size in USD"},
            "trigger_price": {"type": "number", "description": "Price to trigger order"},
            "limit_price": {"type": "number", "description": "Limit price for triggered order"},
            "trigger_direction": {"type": "integer", "description": "1=rises to, 2=falls to", "default": 2},
            "trading_env": TRADING_ENV_PARAM,
        },
        "required": ["symbol", "usd_amount", "trigger_price", "limit_price"],
    },
    # Order Management
    {
        "name": "get_open_orders",
        "description": "Get list of open orders",
        "category": "orders.manage",
        "parameters": {
            "symbol": {"type": "string", "description": "Filter by symbol", "optional": True},
            "order_filter": {"type": "string", "description": "Order/StopOrder/tpslOrder", "optional": True},
            "trading_env": TRADING_ENV_PARAM,
        },
        "required": [],
    },
    {
        "name": "cancel_order",
        "description": "Cancel a specific order by ID",
        "category": "orders.manage",
        "parameters": {
            "symbol": {"type": "string", "description": "Trading symbol"},
            "order_id": {"type": "string", "description": "Order ID to cancel", "optional": True},
            "order_link_id": {"type": "string", "description": "Custom order ID", "optional": True},
            "trading_env": TRADING_ENV_PARAM,
        },
        "required": ["symbol"],
    },
    {
        "name": "amend_order",
        "description": "Modify an existing order",
        "category": "orders.manage",
        "parameters": {
            "symbol": {"type": "string", "description": "Trading symbol"},
            "order_id": {"type": "string", "description": "Order ID", "optional": True},
            "qty": {"type": "number", "description": "New quantity", "optional": True},
            "price": {"type": "number", "description": "New price", "optional": True},
            "take_profit": {"type": "number", "description": "New TP", "optional": True},
            "stop_loss": {"type": "number", "description": "New SL", "optional": True},
            "trading_env": TRADING_ENV_PARAM,
        },
        "required": ["symbol"],
    },
    {
        "name": "cancel_all_orders",
        "description": "Cancel all open orders",
        "category": "orders.manage",
        "parameters": {
            "symbol": {"type": "string", "description": "Filter by symbol", "optional": True},
            "trading_env": TRADING_ENV_PARAM,
        },
        "required": [],
    },
]
