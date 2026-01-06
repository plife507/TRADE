"""
Funding rate scheduler utilities.

Provides O(1) detection of funding settlement times in the hot loop.

Bybit funding schedule:
- Settlements at 00:00, 08:00, 16:00 UTC (every 8 hours)
- Positive rate: longs pay shorts
- Negative rate: shorts pay longs

Usage in hot loop:
    # Check if funding settlement occurred in (prev_ts, current_ts] window
    events = get_funding_events_in_window(
        prev_ts=prev_bar.ts_close,
        current_ts=bar.ts_close,
        funding_settlement_times=exec_feed.funding_settlement_times,
        funding_df=funding_df,
        symbol=symbol,
    )

    # Pass events to exchange.process_bar()
    exchange.process_bar(..., funding_events=events)
"""

from datetime import datetime
from typing import TYPE_CHECKING

import pandas as pd
import numpy as np

if TYPE_CHECKING:
    from ..sim.types import FundingEvent

# Bybit funding settlement hours (UTC)
FUNDING_HOURS_UTC = frozenset({0, 8, 16})

# 8 hours in milliseconds (funding interval)
FUNDING_INTERVAL_MS = 8 * 60 * 60 * 1000


def is_funding_settlement_time(ts: datetime) -> bool:
    """
    Check if timestamp is a funding settlement time.

    Funding settlements occur at 00:00, 08:00, 16:00 UTC.

    Args:
        ts: Timestamp to check (should be UTC)

    Returns:
        True if this is a funding settlement time
    """
    return ts.hour in FUNDING_HOURS_UTC and ts.minute == 0 and ts.second == 0


def get_funding_events_in_window(
    prev_ts: datetime | None,
    current_ts: datetime,
    funding_settlement_times: set[int],
    funding_df: pd.DataFrame | None,
    symbol: str,
) -> list["FundingEvent"]:
    """
    Get funding events that occurred in time window (prev_ts, current_ts].

    Uses precomputed funding_settlement_times set for O(1) lookup.
    Only returns events with timestamps in the window.

    Args:
        prev_ts: Previous bar timestamp (exclusive bound, None for first bar)
        current_ts: Current bar timestamp (inclusive bound)
        funding_settlement_times: Set of epoch_ms funding settlement times
        funding_df: DataFrame with timestamp, funding_rate columns
        symbol: Trading symbol

    Returns:
        List of FundingEvent objects in the window (usually 0 or 1)
    """
    # Import here to avoid circular imports
    from ..sim.types import FundingEvent

    if not funding_settlement_times or funding_df is None or funding_df.empty:
        return []

    # Convert timestamps to epoch ms
    if prev_ts is not None:
        if hasattr(prev_ts, "timestamp"):
            prev_ms = int(prev_ts.timestamp() * 1000)
        else:
            prev_ms = int(pd.Timestamp(prev_ts).timestamp() * 1000)
    else:
        prev_ms = 0  # First bar: include all up to current

    if hasattr(current_ts, "timestamp"):
        current_ms = int(current_ts.timestamp() * 1000)
    else:
        current_ms = int(pd.Timestamp(current_ts).timestamp() * 1000)

    # Find funding settlements in window (prev_ms, current_ms]
    events = []
    for settlement_ms in funding_settlement_times:
        if prev_ms < settlement_ms <= current_ms:
            # Find the funding rate for this settlement
            settlement_ts = pd.Timestamp(settlement_ms, unit="ms").to_pydatetime()

            # Lookup rate from DataFrame
            mask = funding_df["timestamp"] == settlement_ts
            if mask.any():
                rate = float(funding_df.loc[mask, "funding_rate"].iloc[0])
                events.append(FundingEvent(
                    timestamp=settlement_ts,
                    symbol=symbol,
                    funding_rate=rate,
                ))

    # Sort by timestamp (usually just 0-1 events, but be safe)
    events.sort(key=lambda e: e.timestamp)

    return events


def count_funding_settlements_in_range(
    start_ts: datetime,
    end_ts: datetime,
) -> int:
    """
    Count how many funding settlements occur in a time range.

    Useful for estimating funding costs over a period.

    Args:
        start_ts: Start timestamp (inclusive)
        end_ts: End timestamp (inclusive)

    Returns:
        Number of funding settlements in range
    """
    if end_ts <= start_ts:
        return 0

    # Calculate time span in hours
    hours = (end_ts - start_ts).total_seconds() / 3600

    # Each 8 hour period has 1 settlement
    # Add 1 if start or end is on a settlement
    base_count = int(hours // 8)

    # Check if start is on a settlement
    if is_funding_settlement_time(start_ts):
        base_count += 1

    return base_count


def next_funding_settlement(ts: datetime) -> datetime:
    """
    Get the next funding settlement time after ts.

    Args:
        ts: Current timestamp

    Returns:
        Next funding settlement datetime
    """
    # Find current hour and next settlement hour
    current_hour = ts.hour

    if current_hour < 8:
        next_hour = 8
    elif current_hour < 16:
        next_hour = 16
    else:
        next_hour = 24  # Next day 00:00

    # Build next settlement time
    if next_hour == 24:
        # Roll to next day
        next_ts = ts.replace(hour=0, minute=0, second=0, microsecond=0)
        next_ts = next_ts + pd.Timedelta(days=1)
    else:
        next_ts = ts.replace(hour=next_hour, minute=0, second=0, microsecond=0)

    # If we're exactly on a settlement, return next one
    if is_funding_settlement_time(ts):
        return next_funding_settlement(next_ts)

    return next_ts


def time_to_next_settlement(ts: datetime) -> float:
    """
    Calculate hours until next funding settlement.

    Args:
        ts: Current timestamp

    Returns:
        Hours until next settlement (0.0 to 8.0)
    """
    next_settlement = next_funding_settlement(ts)
    delta = next_settlement - ts
    return delta.total_seconds() / 3600
