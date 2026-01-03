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

# Time range parameters for history queries
TIME_RANGE_PARAMS = {
    "period": {
        "type": "string",
        "description": "Relative period (1M, 3M, 6M, 1Y) - alternative to start/end",
        "optional": True,
    },
    "start": {
        "type": "string",
        "description": "Start datetime ISO string (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)",
        "optional": True,
    },
    "end": {
        "type": "string",
        "description": "End datetime ISO string (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)",
        "optional": True,
    },
}
