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
        set_position_tpsl_tool,
        panic_close_all_tool,
    )
    from .. import (
        set_risk_limit_tool, get_risk_limits_tool,
        set_tp_sl_mode_tool, set_auto_add_margin_tool,
        modify_position_margin_tool, switch_margin_mode_tool, switch_position_mode_tool,
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
        "set_position_tpsl": set_position_tpsl_tool,
        "panic_close_all": panic_close_all_tool,
        # Position configuration
        "set_risk_limit": set_risk_limit_tool,
        "get_risk_limits": get_risk_limits_tool,
        "set_tp_sl_mode": set_tp_sl_mode_tool,
        "set_auto_add_margin": set_auto_add_margin_tool,
        "modify_position_margin": modify_position_margin_tool,
        "switch_margin_mode": switch_margin_mode_tool,
        "switch_position_mode": switch_position_mode_tool,
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
        "name": "set_position_tpsl",
        "description": "Set both take profit and stop loss for an existing position",
        "category": "positions.tpsl",
        "parameters": {
            "symbol": {"type": "string", "description": "Trading symbol"},
            "take_profit": {"type": "number", "description": "Take profit price (None to leave unchanged, 0 to remove)", "optional": True},
            "stop_loss": {"type": "number", "description": "Stop loss price (None to leave unchanged, 0 to remove)", "optional": True},
            "tpsl_mode": {"type": "string", "description": "Full (entire position) or Partial", "default": "Full"},
            "trading_env": TRADING_ENV_PARAM,
        },
        "required": ["symbol"],
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
    # Position Configuration
    {
        "name": "set_risk_limit",
        "description": "Set risk limit for a symbol by risk ID",
        "category": "positions.config",
        "parameters": {
            "symbol": {"type": "string", "description": "Trading symbol"},
            "risk_id": {"type": "integer", "description": "Risk limit ID from get_risk_limits"},
            "trading_env": TRADING_ENV_PARAM,
        },
        "required": ["symbol", "risk_id"],
    },
    {
        "name": "get_risk_limits",
        "description": "Get risk limit tiers for a symbol",
        "category": "positions.config",
        "parameters": {
            "symbol": {"type": "string", "description": "Trading symbol"},
            "trading_env": TRADING_ENV_PARAM,
        },
        "required": ["symbol"],
    },
    {
        "name": "set_tp_sl_mode",
        "description": "Set TP/SL mode for a symbol (Full or Partial)",
        "category": "positions.config",
        "parameters": {
            "symbol": {"type": "string", "description": "Trading symbol"},
            "full_mode": {"type": "boolean", "description": "True for Full (entire position), False for Partial"},
            "trading_env": TRADING_ENV_PARAM,
        },
        "required": ["symbol", "full_mode"],
    },
    {
        "name": "set_auto_add_margin",
        "description": "Enable or disable auto-add-margin for isolated margin position",
        "category": "positions.config",
        "parameters": {
            "symbol": {"type": "string", "description": "Trading symbol"},
            "enabled": {"type": "boolean", "description": "True to enable, False to disable"},
            "trading_env": TRADING_ENV_PARAM,
        },
        "required": ["symbol", "enabled"],
    },
    {
        "name": "modify_position_margin",
        "description": "Add or reduce margin for isolated margin position",
        "category": "positions.config",
        "parameters": {
            "symbol": {"type": "string", "description": "Trading symbol"},
            "margin": {"type": "number", "description": "Amount to add (positive) or reduce (negative)"},
            "trading_env": TRADING_ENV_PARAM,
        },
        "required": ["symbol", "margin"],
    },
    {
        "name": "switch_margin_mode",
        "description": "Switch between cross and isolated margin mode for a symbol",
        "category": "positions.config",
        "parameters": {
            "symbol": {"type": "string", "description": "Trading symbol"},
            "isolated": {"type": "boolean", "description": "True for isolated, False for cross"},
            "leverage": {"type": "integer", "description": "Leverage to set (uses default if not provided)", "optional": True},
            "trading_env": TRADING_ENV_PARAM,
        },
        "required": ["symbol", "isolated"],
    },
    {
        "name": "switch_position_mode",
        "description": "Switch position mode for the account (one-way or hedge)",
        "category": "positions.config",
        "parameters": {
            "hedge_mode": {"type": "boolean", "description": "True for hedge mode (both Buy & Sell), False for one-way"},
            "trading_env": TRADING_ENV_PARAM,
        },
        "required": ["hedge_mode"],
    },
]
