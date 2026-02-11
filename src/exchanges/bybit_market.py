"""
Bybit market data methods.

Contains: get_klines, get_ticker, get_funding_rate, get_open_interest,
get_orderbook, get_instruments, get_instrument_info, get_server_time, get_risk_limit
"""

from typing import TYPE_CHECKING, Any
import pandas as pd

if TYPE_CHECKING:
    from .bybit_client import BybitClient


def get_klines(
    client: "BybitClient",
    symbol: str,
    interval: str = "15",
    limit: int = 200,
    start: int | None = None,
    end: int | None = None,
    category: str = "linear",
) -> pd.DataFrame:
    """Get OHLCV candlestick data."""
    client._public_limiter.acquire()

    response = client._session.get_kline(
        category=category,
        symbol=symbol,
        interval=interval,
        limit=min(limit, 1000),
        start=start,
        end=end,
    )

    result = client._extract_result(response)
    data = result.get("list", [])

    if not data:
        return pd.DataFrame()

    cols = pd.Index(["timestamp", "open", "high", "low", "close", "volume", "turnover"])
    df = pd.DataFrame(data, columns=cols)

    df["timestamp"] = pd.to_datetime(df["timestamp"].astype(int), unit="ms", utc=True)
    for col in ["open", "high", "low", "close", "volume", "turnover"]:
        df[col] = df[col].astype(float)

    df = df.sort_values("timestamp").reset_index(drop=True)

    return df


def get_ticker(client: "BybitClient", symbol: str | None = None, category: str = "linear") -> dict[str, Any]:
    """Get ticker information."""
    client._public_limiter.acquire()

    response = client._session.get_tickers(
        category=category,
        symbol=symbol,
    )

    result = client._extract_result(response)
    tickers = result.get("list", [])

    if symbol and tickers:
        return tickers[0]
    return tickers


def get_funding_rate(
    client: "BybitClient",
    symbol: str,
    limit: int = 1,
    category: str = "linear",
    start_time: int | None = None,
    end_time: int | None = None,
) -> list[dict]:
    """Get funding rate history."""
    client._public_limiter.acquire()

    params: dict = {
        "category": category,
        "symbol": symbol,
        "limit": limit,
    }
    if start_time is not None:
        params["startTime"] = start_time
    if end_time is not None:
        params["endTime"] = end_time

    response = client._session.get_funding_rate_history(**params)

    result = client._extract_result(response)
    return result.get("list", [])


def get_open_interest(
    client: "BybitClient",
    symbol: str,
    interval: str = "5min",
    limit: int = 1,
    category: str = "linear",
    start_time: int | None = None,
    end_time: int | None = None,
) -> list[dict]:
    """Get open interest data."""
    client._public_limiter.acquire()

    params: dict = {
        "category": category,
        "symbol": symbol,
        "intervalTime": interval,
        "limit": limit,
    }
    if start_time is not None:
        params["startTime"] = start_time
    if end_time is not None:
        params["endTime"] = end_time

    response = client._session.get_open_interest(**params)

    result = client._extract_result(response)
    return result.get("list", [])


def get_orderbook(client: "BybitClient", symbol: str, limit: int = 25, category: str = "linear") -> dict:
    """Get orderbook depth."""
    client._public_limiter.acquire()

    response = client._session.get_orderbook(
        category=category,
        symbol=symbol,
        limit=limit,
    )

    return client._extract_result(response)


def get_instruments(client: "BybitClient", symbol: str | None = None, category: str = "linear") -> list[dict]:
    """Get instrument specifications."""
    client._public_limiter.acquire()

    response = client._session.get_instruments_info(
        category=category,
        symbol=symbol,
    )

    result = client._extract_result(response)
    return result.get("list", [])


def get_instrument_info(client: "BybitClient", symbol: str, category: str = "linear") -> dict | None:
    """Get instrument info for a single symbol."""
    instruments = get_instruments(client, symbol=symbol, category=category)
    return instruments[0] if instruments else None


def get_server_time(client: "BybitClient") -> dict:
    """Get Bybit server time."""
    client._public_limiter.acquire()

    response = client._session.get_server_time()
    return client._extract_result(response)


def get_risk_limit(client: "BybitClient", symbol: str | None = None, category: str = "linear") -> list[dict]:
    """Get risk limit info for symbols."""
    client._public_limiter.acquire()

    response = client._session.get_risk_limit(
        category=category,
        symbol=symbol,
    )

    result = client._extract_result(response)
    return result.get("list", [])


def get_instrument_launch_time(client: "BybitClient", symbol: str, category: str = "linear") -> int | None:
    """
    Get instrument launch timestamp in milliseconds.

    Args:
        client: BybitClient instance
        symbol: Trading symbol (e.g., "BTCUSDT")
        category: Product category ("linear", "inverse", "spot", "option")

    Returns:
        Launch timestamp in milliseconds, or None if not found/not available
    """
    info = get_instrument_info(client, symbol=symbol, category=category)
    if info and "launchTime" in info:
        try:
            return int(info["launchTime"])
        except (ValueError, TypeError):
            return None
    return None
