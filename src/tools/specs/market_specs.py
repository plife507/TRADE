"""
Market data tool specifications.

NO LEGACY FALLBACKS - Forward coding only.
"""


def get_imports():
    """Return dict of function_name -> import path."""
    from .. import (
        get_price_tool, get_ohlcv_tool, get_funding_rate_tool,
        get_open_interest_tool, get_orderbook_tool,
        get_instruments_tool, run_market_data_tests_tool,
    )
    return {
        "get_price": get_price_tool,
        "get_ohlcv": get_ohlcv_tool,
        "get_funding_rate": get_funding_rate_tool,
        "get_open_interest": get_open_interest_tool,
        "get_orderbook": get_orderbook_tool,
        "get_instruments": get_instruments_tool,
        "run_market_data_tests": run_market_data_tests_tool,
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
            "interval": {"type": "string", "description": "Timeframe (1m, 5m, 15m, 1h, 4h, D)", "default": "15m"},
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
    {
        "name": "get_open_interest",
        "description": "Get open interest data for a symbol",
        "category": "market",
        "parameters": {
            "symbol": {"type": "string", "description": "Trading symbol"},
            "interval": {"type": "string", "description": "Time interval (5min, 15min, 30min, 1h, 4h, D)", "default": "5min"},
            "limit": {"type": "integer", "description": "Number of records to retrieve", "default": 1},
        },
        "required": ["symbol"],
    },
    {
        "name": "get_orderbook",
        "description": "Get orderbook data for a symbol (bids and asks)",
        "category": "market",
        "parameters": {
            "symbol": {"type": "string", "description": "Trading symbol"},
            "limit": {"type": "integer", "description": "Depth of orderbook (levels per side)", "default": 25},
        },
        "required": ["symbol"],
    },
    {
        "name": "get_instruments",
        "description": "Get instrument information for a symbol or all symbols",
        "category": "market",
        "parameters": {
            "symbol": {"type": "string", "description": "Trading symbol (None for all instruments)", "optional": True},
        },
        "required": [],
    },
    {
        "name": "run_market_data_tests",
        "description": "Run comprehensive market data tests on a symbol (price, OHLCV, funding, OI, orderbook, instruments)",
        "category": "market",
        "parameters": {
            "symbol": {"type": "string", "description": "Symbol to test"},
        },
        "required": ["symbol"],
    },
]
