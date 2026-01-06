"""
Timestamp utilities for viz data loaders.

Converts various timestamp formats to Unix seconds for Lightweight Charts.
"""

from datetime import datetime
import pandas as pd


def to_unix_timestamp(ts: datetime | pd.Timestamp | str | int | float | None) -> int | None:
    """
    Convert various timestamp formats to Unix timestamp (seconds).

    Lightweight Charts expects Unix timestamps in seconds.

    Args:
        ts: Timestamp in various formats:
            - datetime object
            - pandas Timestamp
            - ISO string (e.g., "2024-01-01T00:00:00")
            - Unix timestamp in milliseconds (int > 1e12)
            - Unix timestamp in seconds (int/float)
            - None

    Returns:
        Unix timestamp in seconds, or None if conversion fails.
    """
    if ts is None:
        return None

    try:
        # Already a Unix timestamp in seconds (reasonable range check)
        if isinstance(ts, (int, float)):
            # If > 1e12, assume milliseconds
            if ts > 1e12:
                return int(ts // 1000)
            # If reasonable range for seconds (after year 2000)
            if ts > 946684800:  # 2000-01-01
                return int(ts)
            return None

        # pandas Timestamp
        if isinstance(ts, pd.Timestamp):
            # Handle NaT
            if pd.isna(ts):
                return None
            return int(ts.timestamp())

        # datetime object
        if isinstance(ts, datetime):
            return int(ts.timestamp())

        # String - try to parse
        if isinstance(ts, str):
            # Try ISO format first
            try:
                dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                return int(dt.timestamp())
            except ValueError:
                pass

            # Try pandas parsing as fallback
            try:
                dt = pd.to_datetime(ts)
                if pd.isna(dt):
                    return None
                return int(dt.timestamp())
            except Exception:
                pass

        return None

    except Exception:
        return None
