"""
Funding rate data adapter.

Converts DuckDB/pandas funding rows to FundingEvent objects.

Handles:
- Dict rows from DuckDB
- pandas DataFrame
- Time window filtering
- Timestamp parsing
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

from ..types import FundingEvent


def adapt_funding_row(row: dict[str, Any] | "pd.Series") -> FundingEvent:
    """
    Convert a single funding row to a FundingEvent.
    
    Args:
        row: Funding data with keys: timestamp (or funding_time), symbol, funding_rate
        
    Returns:
        FundingEvent instance
    """
    # Handle pandas Series
    if hasattr(row, "to_dict"):
        row = dict(row)
    
    # Parse timestamp (could be 'timestamp' or 'funding_time')
    ts = row.get("timestamp") or row.get("funding_time")
    if ts is None:
        raise KeyError("Missing timestamp or funding_time column")
    
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts)
    elif hasattr(ts, "to_pydatetime"):
        ts = ts.to_pydatetime()
    
    # Get symbol
    symbol = row.get("symbol", "")
    
    # Get funding rate (could be 'funding_rate' or 'fundingRate')
    rate = row.get("funding_rate") or row.get("fundingRate")
    if rate is None:
        raise KeyError("Missing funding_rate column")
    
    return FundingEvent(
        timestamp=ts,
        symbol=symbol,
        funding_rate=float(rate),
    )


def adapt_funding_rows(
    rows: list[dict[str, Any]],
    prev_ts: datetime | None,
    ts: datetime,
) -> list[FundingEvent]:
    """
    Convert funding rows to events, filtering to time window (prev_ts, ts].
    
    Funding events are applied to positions held at funding time.
    Only events in the half-open interval (prev_ts, ts] are included.
    
    Args:
        rows: List of funding data dicts
        prev_ts: Previous bar timestamp (exclusive bound), or None for first bar
        ts: Current bar timestamp (inclusive bound)
        
    Returns:
        List of FundingEvent instances within the time window
    """
    events = []
    
    for row in rows:
        event = adapt_funding_row(row)
        
        # Filter to time window (prev_ts, ts]
        if prev_ts is not None and event.timestamp <= prev_ts:
            continue
        if event.timestamp > ts:
            continue
        
        events.append(event)
    
    # Sort by timestamp
    events.sort(key=lambda e: e.timestamp)
    
    return events


def adapt_funding_dataframe(
    df: "pd.DataFrame",
    prev_ts: datetime | None = None,
    ts: datetime | None = None,
) -> list[FundingEvent]:
    """
    Convert a pandas DataFrame to a list of FundingEvents.
    
    Optionally filters to time window (prev_ts, ts].
    
    Args:
        df: DataFrame with funding data
        prev_ts: Optional previous bar timestamp (exclusive bound)
        ts: Optional current bar timestamp (inclusive bound)
        
    Returns:
        List of FundingEvent instances
    """
    events = []
    
    for _, row in df.iterrows():
        event = adapt_funding_row(row)
        
        # Apply time window filter if bounds provided
        if prev_ts is not None and event.timestamp <= prev_ts:
            continue
        if ts is not None and event.timestamp > ts:
            continue
        
        events.append(event)
    
    # Sort by timestamp
    events.sort(key=lambda e: e.timestamp)
    
    return events

