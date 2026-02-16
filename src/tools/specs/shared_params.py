"""
Shared parameter definitions for tool specs.

NO LEGACY FALLBACKS - Forward coding only.
"""

# Trading environment validation parameter
TRADING_ENV_PARAM = {
    "type": "string",
    "description": "Trading environment for validation ('demo' or 'live'). Validates caller's intent against process config.",
    "optional": True,
}

# Data environment parameter
DATA_ENV_PARAM = {
    "type": "string",
    "description": "Data environment: 'live' (backtest) or 'demo'",
    "default": "live",
    "optional": True,
}

# Common symbol parameter
SYMBOL_PARAM = {
    "type": "string",
    "description": "Trading symbol (e.g., SOLUSDT)",
}
