"""
Position tool specifications.

NO LEGACY FALLBACKS - Forward coding only.
"""

from .shared_params import TRADING_ENV_PARAM


def get_imports():
    """Return dict of function_name -> import path."""
    from .. import (
        list_open_positions_tool, get_position_detail_tool, close_position_tool,
        set_take_profit_tool, set_stop_loss_tool, remove_take_profit_tool, remove_stop_loss_tool,
        set_trailing_stop_tool, set_trailing_stop_by_percent_tool,
        panic_close_all_tool,
    )
    return {
        "list_positions": list_open_positions_tool,
        "get_position": get_position_detail_tool,
        "close_position": close_position_tool,
        "set_take_profit": set_take_profit_tool,
        "set_stop_loss": set_stop_loss_tool,
        "remove_take_profit": remove_take_profit_tool,
        "remove_stop_loss": remove_stop_loss_tool,
        "set_trailing_stop": set_trailing_stop_tool,
        "set_trailing_stop_percent": set_trailing_stop_by_percent_tool,
        "panic_close_all": panic_close_all_tool,
    }


SPECS = [
    {
        "name": "list_positions",
        "description": "List all open positions",
        "category": "positions",
        "parameters": {
            "trading_env": TRADING_ENV_PARAM,
        },
        "required": [],
    },
    {
        "name": "get_position",
        "description": "Get details of a specific position",
        "category": "positions",
        "parameters": {
            "symbol": {"type": "string", "description": "Trading symbol"},
            "trading_env": TRADING_ENV_PARAM,
        },
        "required": ["symbol"],
    },
    {
        "name": "close_position",
        "description": "Close an open position at market",
        "category": "positions",
        "parameters": {
            "symbol": {"type": "string", "description": "Trading symbol"},
            "trading_env": TRADING_ENV_PARAM,
        },
        "required": ["symbol"],
    },
    {
        "name": "set_take_profit",
        "description": "Set take profit for a position",
        "category": "positions.tpsl",
        "parameters": {
            "symbol": {"type": "string", "description": "Trading symbol"},
            "take_profit": {"type": "number", "description": "Take profit price"},
            "trading_env": TRADING_ENV_PARAM,
        },
        "required": ["symbol", "take_profit"],
    },
    {
        "name": "set_stop_loss",
        "description": "Set stop loss for a position",
        "category": "positions.tpsl",
        "parameters": {
            "symbol": {"type": "string", "description": "Trading symbol"},
            "stop_loss": {"type": "number", "description": "Stop loss price"},
            "trading_env": TRADING_ENV_PARAM,
        },
        "required": ["symbol", "stop_loss"],
    },
    {
        "name": "remove_take_profit",
        "description": "Remove take profit from position",
        "category": "positions.tpsl",
        "parameters": {
            "symbol": {"type": "string", "description": "Trading symbol"},
            "trading_env": TRADING_ENV_PARAM,
        },
        "required": ["symbol"],
    },
    {
        "name": "remove_stop_loss",
        "description": "Remove stop loss from position",
        "category": "positions.tpsl",
        "parameters": {
            "symbol": {"type": "string", "description": "Trading symbol"},
            "trading_env": TRADING_ENV_PARAM,
        },
        "required": ["symbol"],
    },
    {
        "name": "set_trailing_stop",
        "description": "Set trailing stop by distance",
        "category": "positions.trailing",
        "parameters": {
            "symbol": {"type": "string", "description": "Trading symbol"},
            "trailing_distance": {"type": "number", "description": "Distance in price units (0 to remove)"},
            "active_price": {"type": "number", "description": "Activation price", "optional": True},
            "trading_env": TRADING_ENV_PARAM,
        },
        "required": ["symbol", "trailing_distance"],
    },
    {
        "name": "set_trailing_stop_percent",
        "description": "Set trailing stop by percentage",
        "category": "positions.trailing",
        "parameters": {
            "symbol": {"type": "string", "description": "Trading symbol"},
            "callback_rate": {"type": "number", "description": "Callback rate percentage (e.g., 3.0 for 3%)"},
            "trading_env": TRADING_ENV_PARAM,
        },
        "required": ["symbol", "callback_rate"],
    },
    {
        "name": "panic_close_all",
        "description": "Emergency close all positions and cancel all orders",
        "category": "positions.emergency",
        "parameters": {
            "reason": {"type": "string", "description": "Reason for panic close", "optional": True},
            "trading_env": TRADING_ENV_PARAM,
        },
        "required": [],
    },
]
