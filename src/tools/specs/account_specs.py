"""
Account tool specifications.

NO LEGACY FALLBACKS - Forward coding only.
"""

from .shared_params import TRADING_ENV_PARAM


def get_imports():
    """Return dict of function_name -> import path."""
    from .. import (
        get_account_balance_tool, get_total_exposure_tool, get_account_info_tool,
        get_portfolio_snapshot_tool, set_leverage_tool,
        get_order_history_tool, get_closed_pnl_tool,
        get_transaction_log_tool, get_collateral_info_tool, set_collateral_coin_tool,
        get_borrow_history_tool, get_coin_greeks_tool,
        set_account_margin_mode_tool, get_transferable_amount_tool,
    )
    return {
        "get_balance": get_account_balance_tool,
        "get_total_exposure": get_total_exposure_tool,
        "get_account_info": get_account_info_tool,
        "get_portfolio": get_portfolio_snapshot_tool,
        "set_leverage": set_leverage_tool,
        "get_order_history": get_order_history_tool,
        "get_closed_pnl": get_closed_pnl_tool,
        "get_transaction_log": get_transaction_log_tool,
        "get_collateral_info": get_collateral_info_tool,
        "set_collateral_coin": set_collateral_coin_tool,
        "get_borrow_history": get_borrow_history_tool,
        "get_coin_greeks": get_coin_greeks_tool,
        "set_account_margin_mode": set_account_margin_mode_tool,
        "get_transferable_amount": get_transferable_amount_tool,
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
        "name": "get_total_exposure",
        "description": "Get total position exposure across all positions in USD",
        "category": "account",
        "parameters": {
            "trading_env": TRADING_ENV_PARAM,
        },
        "required": [],
    },
    {
        "name": "get_account_info",
        "description": "Get detailed account information (margin mode, unified margin status)",
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
    # Unified account tools
    {
        "name": "get_collateral_info",
        "description": "Get collateral information for Unified account (rates, limits, status)",
        "category": "account.collateral",
        "parameters": {
            "currency": {"type": "string", "description": "Specific currency (None for all)", "optional": True},
            "trading_env": TRADING_ENV_PARAM,
        },
        "required": [],
    },
    {
        "name": "set_collateral_coin",
        "description": "Enable or disable a coin as collateral",
        "category": "account.collateral",
        "parameters": {
            "coin": {"type": "string", "description": "Coin name (e.g., BTC, ETH, USDT)"},
            "enabled": {"type": "boolean", "description": "True to enable, False to disable"},
            "trading_env": TRADING_ENV_PARAM,
        },
        "required": ["coin", "enabled"],
    },
    {
        "name": "get_coin_greeks",
        "description": "Get account Greeks information (for options)",
        "category": "account.greeks",
        "parameters": {
            "base_coin": {"type": "string", "description": "Base coin filter (BTC, ETH, etc.)", "optional": True},
            "trading_env": TRADING_ENV_PARAM,
        },
        "required": [],
    },
    {
        "name": "set_account_margin_mode",
        "description": "Set account-level margin mode (Portfolio Margin or Regular Margin)",
        "category": "account.config",
        "parameters": {
            "portfolio_margin": {"type": "boolean", "description": "True for Portfolio Margin, False for Regular Margin"},
            "trading_env": TRADING_ENV_PARAM,
        },
        "required": ["portfolio_margin"],
    },
    {
        "name": "get_transferable_amount",
        "description": "Get the available amount to transfer for a coin",
        "category": "account.transfer",
        "parameters": {
            "coin": {"type": "string", "description": "Coin name (e.g., USDT, BTC)"},
            "trading_env": TRADING_ENV_PARAM,
        },
        "required": ["coin"],
    },
]
