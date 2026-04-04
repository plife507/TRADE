"""
Portfolio tool specifications for ToolRegistry.

Categories: portfolio.state, portfolio.instruments, portfolio.subs,
portfolio.deploy, portfolio.collateral
"""


def get_imports():
    """Return dict of function_name -> callable."""
    from .. import portfolio_tools as pt
    return {
        # State
        "get_uta_snapshot": pt.get_uta_snapshot_tool,
        "get_portfolio_wallet": pt.get_portfolio_wallet_tool,
        "get_portfolio_risk": pt.get_portfolio_risk_tool,
        "get_portfolio_exposure": pt.get_portfolio_exposure_tool,
        # Instruments
        "resolve_instrument": pt.resolve_instrument_tool,
        "list_instruments": pt.list_instruments_tool,
        # Sub-accounts
        "list_sub_accounts": pt.list_sub_accounts_tool,
        "create_sub_account": pt.create_sub_account_tool,
        "fund_sub_account": pt.fund_sub_account_tool,
        "withdraw_sub_account": pt.withdraw_sub_account_tool,
        "get_sub_account_balance": pt.get_sub_account_balance_tool,
        "get_sub_account_positions": pt.get_sub_account_positions_tool,
        "freeze_sub_account": pt.freeze_sub_account_tool,
        "delete_sub_account": pt.delete_sub_account_tool,
        # Deploy
        "deploy_play": pt.deploy_play_tool,
        "stop_play": pt.stop_play_tool,
        "get_play_status": pt.get_play_status_tool,
        "rebalance_play": pt.rebalance_play_tool,
        "list_active_plays": pt.list_active_plays_tool,
        # Emergency
        "recall_all": pt.recall_all_tool,
        # Collateral
        "get_collateral_tiers": pt.get_collateral_tiers_tool,
        "toggle_collateral": pt.toggle_collateral_tool,
    }


SPECS = [
    # ── State ────────────────────────────────────────────
    {
        "name": "get_uta_snapshot",
        "description": "Get complete UTA portfolio snapshot (main + all sub-accounts)",
        "category": "portfolio.state",
        "parameters": {},
        "required": [],
    },
    {
        "name": "get_portfolio_wallet",
        "description": "Get all wallet coins with balances and collateral status",
        "category": "portfolio.state",
        "parameters": {},
        "required": [],
    },
    {
        "name": "get_portfolio_risk",
        "description": "Get account-level risk metrics (margin utilization, liquidation proximity)",
        "category": "portfolio.state",
        "parameters": {},
        "required": [],
    },
    {
        "name": "get_portfolio_exposure",
        "description": "Get exposure breakdown by category and settle coin",
        "category": "portfolio.state",
        "parameters": {},
        "required": [],
    },
    # ── Instruments ──────────────────────────────────────
    {
        "name": "resolve_instrument",
        "description": "Resolve a symbol to its full instrument specification (category, settle coin, filters)",
        "category": "portfolio.instruments",
        "parameters": {
            "symbol": {"type": "string", "description": "Bybit symbol (e.g., BTCUSDT, BTCPERP, BTCUSD)"},
        },
        "required": ["symbol"],
    },
    {
        "name": "list_instruments",
        "description": "List available instruments with optional filters",
        "category": "portfolio.instruments",
        "parameters": {
            "category": {"type": "string", "description": "Filter by category (linear, inverse)", "optional": True},
            "settle_coin": {"type": "string", "description": "Filter by settle coin (USDT, USDC)", "optional": True},
        },
        "required": [],
    },
    # ── Sub-Accounts ────────────────────────────────────
    {
        "name": "list_sub_accounts",
        "description": "List all managed sub-accounts",
        "category": "portfolio.subs",
        "parameters": {},
        "required": [],
    },
    {
        "name": "create_sub_account",
        "description": "Create a new sub-account with API keys",
        "category": "portfolio.subs",
        "parameters": {
            "username": {"type": "string", "description": "6-16 chars, must include letters and digits"},
        },
        "required": ["username"],
    },
    {
        "name": "fund_sub_account",
        "description": "Transfer funds from main account to sub-account",
        "category": "portfolio.subs",
        "parameters": {
            "uid": {"type": "integer", "description": "Sub-account UID"},
            "coin": {"type": "string", "description": "Coin to transfer (USDT, USDC)"},
            "amount": {"type": "number", "description": "Amount to transfer"},
        },
        "required": ["uid", "coin", "amount"],
    },
    {
        "name": "withdraw_sub_account",
        "description": "Transfer funds from sub-account back to main",
        "category": "portfolio.subs",
        "parameters": {
            "uid": {"type": "integer", "description": "Sub-account UID"},
            "coin": {"type": "string", "description": "Coin to transfer"},
            "amount": {"type": "number", "description": "Amount to transfer"},
        },
        "required": ["uid", "coin", "amount"],
    },
    {
        "name": "get_sub_account_balance",
        "description": "Get sub-account wallet balance",
        "category": "portfolio.subs",
        "parameters": {
            "uid": {"type": "integer", "description": "Sub-account UID"},
        },
        "required": ["uid"],
    },
    {
        "name": "get_sub_account_positions",
        "description": "Get sub-account open positions",
        "category": "portfolio.subs",
        "parameters": {
            "uid": {"type": "integer", "description": "Sub-account UID"},
        },
        "required": ["uid"],
    },
    {
        "name": "freeze_sub_account",
        "description": "Freeze a sub-account (stop trading)",
        "category": "portfolio.subs",
        "parameters": {
            "uid": {"type": "integer", "description": "Sub-account UID"},
        },
        "required": ["uid"],
    },
    {
        "name": "delete_sub_account",
        "description": "Delete a sub-account (must have zero balance)",
        "category": "portfolio.subs",
        "parameters": {
            "uid": {"type": "integer", "description": "Sub-account UID"},
        },
        "required": ["uid"],
    },
    # ── Deploy ──────────────────────────────────────────
    {
        "name": "deploy_play",
        "description": "Deploy a proven play into a sub-account",
        "category": "portfolio.deploy",
        "parameters": {
            "play_id": {"type": "string", "description": "Play identifier"},
            "symbol": {"type": "string", "description": "Trading symbol"},
            "capital": {"type": "number", "description": "Capital to allocate (USD)"},
            "confirm": {"type": "boolean", "description": "Must be true to proceed", "default": False},
        },
        "required": ["play_id", "symbol", "capital"],
    },
    {
        "name": "stop_play",
        "description": "Stop a deployed play",
        "category": "portfolio.deploy",
        "parameters": {
            "uid": {"type": "integer", "description": "Sub-account UID running the play"},
            "close_positions": {"type": "boolean", "description": "Close open positions", "default": True},
        },
        "required": ["uid"],
    },
    {
        "name": "get_play_status",
        "description": "Get status of a deployed play",
        "category": "portfolio.deploy",
        "parameters": {
            "uid": {"type": "integer", "description": "Sub-account UID"},
        },
        "required": ["uid"],
    },
    {
        "name": "rebalance_play",
        "description": "Add/remove capital from a deployed play",
        "category": "portfolio.deploy",
        "parameters": {
            "uid": {"type": "integer", "description": "Sub-account UID"},
            "new_capital": {"type": "number", "description": "New target capital amount"},
        },
        "required": ["uid", "new_capital"],
    },
    {
        "name": "list_active_plays",
        "description": "List all running plays",
        "category": "portfolio.deploy",
        "parameters": {},
        "required": [],
    },
    # ── Emergency ───────────────────────────────────────
    {
        "name": "recall_all",
        "description": "Emergency: stop all plays, close all positions, sweep funds to main",
        "category": "portfolio.deploy",
        "parameters": {
            "confirm": {"type": "boolean", "description": "Must be true to proceed", "default": False},
        },
        "required": [],
    },
    # ── Collateral ──────────────────────────────────────
    {
        "name": "get_collateral_tiers",
        "description": "Get tiered collateral ratios",
        "category": "portfolio.collateral",
        "parameters": {
            "currency": {"type": "string", "description": "Filter by currency (e.g., BTC)", "optional": True},
        },
        "required": [],
    },
    {
        "name": "toggle_collateral",
        "description": "Enable/disable a coin as collateral",
        "category": "portfolio.collateral",
        "parameters": {
            "coin": {"type": "string", "description": "Coin to toggle (e.g., BTC, ETH)"},
            "enabled": {"type": "boolean", "description": "True to enable, False to disable"},
        },
        "required": ["coin", "enabled"],
    },
]
