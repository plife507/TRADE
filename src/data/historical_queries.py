"""
Historical data query operations.

Contains: get_ohlcv, get_mtf_data, get_funding, get_open_interest
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union, TYPE_CHECKING
import pandas as pd

if TYPE_CHECKING:
    from .historical_data_store import HistoricalDataStore


def get_ohlcv(
    store: "HistoricalDataStore",
    symbol: str,
    timeframe: str,
    period: str = None,
    start: datetime = None,
    end: datetime = None,
    limit: int = None,
) -> pd.DataFrame:
    """
    Get OHLCV data for a symbol/timeframe.
    
    Args:
        symbol: Trading symbol
        timeframe: Candle timeframe (1m, 5m, 15m, 1h, 4h, 1d)
        period: Time period back from now ("1Y", "6M", "1M", "1W", etc.)
        start: Start datetime (alternative to period)
        end: End datetime (alternative to period)
        limit: Max number of candles
    
    Returns:
        DataFrame with timestamp, open, high, low, close, volume, turnover
    """
    symbol = symbol.upper()
    
    query = f"""
        SELECT timestamp, open, high, low, close, volume, turnover
        FROM {store.table_ohlcv}
        WHERE symbol = ? AND timeframe = ?
    """
    params = [symbol, timeframe]
    
    if period:
        start = datetime.now() - store.parse_period(period)
    
    if start:
        query += " AND timestamp >= ?"
        params.append(start)
    
    if end:
        query += " AND timestamp <= ?"
        params.append(end)
    
    query += " ORDER BY timestamp ASC"
    
    if limit:
        query += f" LIMIT {limit}"
    
    df = store.conn.execute(query, params).fetchdf()
    
    return df


def get_mtf_data(
    store: "HistoricalDataStore",
    symbol: str,
    timeframes: List[str],
    period: str = None,
    start: datetime = None,
    end: datetime = None,
) -> Dict[str, pd.DataFrame]:
    """
    Get multi-timeframe data for a symbol.
    
    Args:
        symbol: Trading symbol
        timeframes: List of timeframes to get
        period: Time period (e.g., "1M" for 1 month)
        start: Start datetime
        end: End datetime
    
    Returns:
        Dict mapping timeframe to DataFrame
    """
    result = {}
    
    for tf in timeframes:
        df = get_ohlcv(store, symbol, tf, period=period, start=start, end=end)
        result[tf] = df
    
    return result


def get_funding(
    store: "HistoricalDataStore",
    symbol: str,
    period: str = None,
    start: datetime = None,
    end: datetime = None,
    limit: int = None,
) -> pd.DataFrame:
    """
    Get funding rate history for a symbol.
    
    Args:
        symbol: Trading symbol
        period: Time period back from now ("1M", "3M", etc.)
        start: Start datetime
        end: End datetime
        limit: Max number of records
    
    Returns:
        DataFrame with timestamp, funding_rate, funding_rate_timestamp
    """
    symbol = symbol.upper()
    
    query = f"""
        SELECT timestamp, funding_rate, funding_rate_timestamp
        FROM {store.table_funding}
        WHERE symbol = ?
    """
    params = [symbol]
    
    if period:
        start = datetime.now() - store.parse_period(period)
    
    if start:
        query += " AND timestamp >= ?"
        params.append(start)
    
    if end:
        query += " AND timestamp <= ?"
        params.append(end)
    
    query += " ORDER BY timestamp ASC"
    
    if limit:
        query += f" LIMIT {limit}"
    
    df = store.conn.execute(query, params).fetchdf()
    
    return df


def get_open_interest(
    store: "HistoricalDataStore",
    symbol: str,
    period: str = None,
    start: datetime = None,
    end: datetime = None,
    limit: int = None,
) -> pd.DataFrame:
    """
    Get open interest history for a symbol.
    
    Args:
        symbol: Trading symbol
        period: Time period back from now ("1M", "3M", etc.)
        start: Start datetime
        end: End datetime
        limit: Max number of records
    
    Returns:
        DataFrame with timestamp, open_interest
    """
    symbol = symbol.upper()
    
    query = f"""
        SELECT timestamp, open_interest
        FROM {store.table_oi}
        WHERE symbol = ?
    """
    params = [symbol]
    
    if period:
        start = datetime.now() - store.parse_period(period)
    
    if start:
        query += " AND timestamp >= ?"
        params.append(start)
    
    if end:
        query += " AND timestamp <= ?"
        params.append(end)
    
    query += " ORDER BY timestamp ASC"
    
    if limit:
        query += f" LIMIT {limit}"
    
    df = store.conn.execute(query, params).fetchdf()
    
    return df

