"""
Market data tool specifications.

NO LEGACY FALLBACKS - Forward coding only.
"""


def get_imports():
    """Return dict of function_name -> import path."""
    from .. import get_price_tool, get_ohlcv_tool, get_funding_rate_tool
    return {
        "get_price": get_price_tool,
        "get_ohlcv": get_ohlcv_tool,
        "get_funding_rate": get_funding_rate_tool,
    }


SPECS = [
    {
        "name": "get_price",
        "description": "Get current price for a symbol",
        "category": "market",
        "parameters": {
            "symbol": {"type": "string", "description": "Trading symbol"},
        },
        "required": ["symbol"],
    },
    {
        "name": "get_ohlcv",
        "description": "Get OHLCV candlestick data",
        "category": "market",
        "parameters": {
            "symbol": {"type": "string", "description": "Trading symbol"},
            "interval": {"type": "string", "description": "Timeframe (1m, 5m, 15m, 1h, 4h, 1d)", "default": "15m"},
            "limit": {"type": "integer", "description": "Number of candles", "default": 100},
        },
        "required": ["symbol"],
    },
    {
        "name": "get_funding_rate",
        "description": "Get funding rate for a symbol",
        "category": "market",
        "parameters": {
            "symbol": {"type": "string", "description": "Trading symbol"},
        },
        "required": ["symbol"],
    },
]
