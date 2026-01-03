"""
Account tool specifications.

NO LEGACY FALLBACKS - Forward coding only.
"""

from .shared_params import TRADING_ENV_PARAM


def get_imports():
    """Return dict of function_name -> import path."""
    from .. import (
        get_account_balance_tool, get_portfolio_snapshot_tool, set_leverage_tool,
        get_order_history_tool, get_closed_pnl_tool,
        get_transaction_log_tool, get_borrow_history_tool,
    )
    return {
        "get_balance": get_account_balance_tool,
        "get_portfolio": get_portfolio_snapshot_tool,
        "set_leverage": set_leverage_tool,
        "get_order_history": get_order_history_tool,
        "get_closed_pnl": get_closed_pnl_tool,
        "get_transaction_log": get_transaction_log_tool,
        "get_borrow_history": get_borrow_history_tool,
    }


SPECS = [
    {
        "name": "get_balance",
        "description": "Get account balance",
        "category": "account",
        "parameters": {
            "trading_env": TRADING_ENV_PARAM,
        },
        "required": [],
    },
    {
        "name": "get_portfolio",
        "description": "Get portfolio snapshot with positions",
        "category": "account",
        "parameters": {
            "trading_env": TRADING_ENV_PARAM,
        },
        "required": [],
    },
    {
        "name": "set_leverage",
        "description": "Set leverage for a symbol",
        "category": "account",
        "parameters": {
            "symbol": {"type": "string", "description": "Trading symbol"},
            "leverage": {"type": "integer", "description": "Leverage value (1-125)"},
            "trading_env": TRADING_ENV_PARAM,
        },
        "required": ["symbol", "leverage"],
    },
    {
        "name": "get_order_history",
        "description": "Get order history within a time range (max 7 days)",
        "category": "account.history",
        "parameters": {
            "window": {"type": "string", "description": "Time window (24h, 7d). Max 7 days.", "default": "7d"},
            "start_ms": {"type": "integer", "description": "Start timestamp ms (alternative to window)", "optional": True},
            "end_ms": {"type": "integer", "description": "End timestamp ms (alternative to window)", "optional": True},
            "symbol": {"type": "string", "description": "Filter by symbol", "optional": True},
            "limit": {"type": "integer", "description": "Max results (1-50)", "default": 50},
            "trading_env": TRADING_ENV_PARAM,
        },
        "required": [],
    },
    {
        "name": "get_closed_pnl",
        "description": "Get closed P&L records within a time range (max 7 days)",
        "category": "account.history",
        "parameters": {
            "window": {"type": "string", "description": "Time window (24h, 7d). Max 7 days.", "default": "7d"},
            "start_ms": {"type": "integer", "description": "Start timestamp ms (alternative to window)", "optional": True},
            "end_ms": {"type": "integer", "description": "End timestamp ms (alternative to window)", "optional": True},
            "symbol": {"type": "string", "description": "Filter by symbol", "optional": True},
            "limit": {"type": "integer", "description": "Max results (1-50)", "default": 50},
            "trading_env": TRADING_ENV_PARAM,
        },
        "required": [],
    },
    {
        "name": "get_transaction_log",
        "description": "Get transaction logs within a time range (max 7 days)",
        "category": "account.history",
        "parameters": {
            "window": {"type": "string", "description": "Time window (24h, 7d). Max 7 days.", "default": "7d"},
            "start_ms": {"type": "integer", "description": "Start timestamp ms (alternative to window)", "optional": True},
            "end_ms": {"type": "integer", "description": "End timestamp ms (alternative to window)", "optional": True},
            "category": {"type": "string", "description": "spot, linear, option", "optional": True},
            "currency": {"type": "string", "description": "Filter by currency (USDT, BTC)", "optional": True},
            "log_type": {"type": "string", "description": "TRADE, SETTLEMENT, TRANSFER_IN, etc.", "optional": True},
            "limit": {"type": "integer", "description": "Max results (1-50)", "default": 50},
            "trading_env": TRADING_ENV_PARAM,
        },
        "required": [],
    },
    {
        "name": "get_borrow_history",
        "description": "Get borrow/interest history within a time range (max 30 days)",
        "category": "account.history",
        "parameters": {
            "window": {"type": "string", "description": "Time window (7d, 30d). Max 30 days.", "default": "30d"},
            "start_ms": {"type": "integer", "description": "Start timestamp ms (alternative to window)", "optional": True},
            "end_ms": {"type": "integer", "description": "End timestamp ms (alternative to window)", "optional": True},
            "currency": {"type": "string", "description": "Filter by currency (USDT, BTC)", "optional": True},
            "limit": {"type": "integer", "description": "Max results (1-50)", "default": 50},
            "trading_env": TRADING_ENV_PARAM,
        },
        "required": [],
    },
]
