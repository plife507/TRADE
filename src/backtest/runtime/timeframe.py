"""
Timeframe utilities for the backtest runtime.

Provides timeframe duration calculation and validation.
Uses TF_MINUTES from the data store as the source of truth.

Note: Close detection is data-driven (via close_ts maps), not modulo-based.
This module only provides duration helpers for warmup/buffer calculations.
"""

from datetime import datetime, timedelta

# Import TF_MINUTES from data store (canonical source)
from ...data.historical_data_store import TF_MINUTES


def tf_duration(tf: str) -> timedelta:
    """
    Get the duration of a timeframe as a timedelta.
    
    Args:
        tf: Timeframe string (e.g., "5m", "1h", "D", "W")
        
    Returns:
        Timedelta representing the timeframe duration
        
    Raises:
        ValueError: If timeframe is not recognized
    """
    tf_key = tf.lower()
    
    if tf_key not in TF_MINUTES:
        raise ValueError(
            f"Unknown timeframe '{tf}'. "
            f"Supported: {list(TF_MINUTES.keys())}"
        )
    
    minutes = TF_MINUTES[tf_key]
    return timedelta(minutes=minutes)


def tf_minutes(tf: str) -> int:
    """
    Get the duration of a timeframe in minutes.
    
    Args:
        tf: Timeframe string
        
    Returns:
        Duration in minutes
        
    Raises:
        ValueError: If timeframe is not recognized
    """
    tf_key = tf.lower()
    
    if tf_key not in TF_MINUTES:
        raise ValueError(
            f"Unknown timeframe '{tf}'. "
            f"Supported: {list(TF_MINUTES.keys())}"
        )
    
    return TF_MINUTES[tf_key]


def validate_tf_mapping(tf_mapping: dict[str, str]) -> None:
    """
    Validate a timeframe mapping (htf/mtf/ltf -> tf string).
    
    Ensures all specified timeframes are valid and HTF >= MTF >= LTF.
    
    Args:
        tf_mapping: Dict with keys htf, mtf, ltf and tf string values
        
    Raises:
        ValueError: If mapping is invalid or timeframes don't follow hierarchy
    """
    required_keys = {"htf", "mtf", "ltf"}
    missing = required_keys - set(tf_mapping.keys())
    if missing:
        raise ValueError(f"Missing required tf_mapping keys: {missing}")
    
    # Validate each timeframe exists
    for role, tf in tf_mapping.items():
        if tf.lower() not in TF_MINUTES:
            raise ValueError(
                f"Unknown timeframe '{tf}' for role '{role}'. "
                f"Supported: {list(TF_MINUTES.keys())}"
            )
    
    # Validate hierarchy: HTF >= MTF >= LTF (in minutes)
    htf_min = tf_minutes(tf_mapping["htf"])
    mtf_min = tf_minutes(tf_mapping["mtf"])
    ltf_min = tf_minutes(tf_mapping["ltf"])
    
    if not (htf_min >= mtf_min >= ltf_min):
        raise ValueError(
            f"Invalid tf_mapping hierarchy: HTF ({tf_mapping['htf']}={htf_min}m) "
            f"must be >= MTF ({tf_mapping['mtf']}={mtf_min}m) "
            f"must be >= LTF ({tf_mapping['ltf']}={ltf_min}m)"
        )


def get_supported_timeframes() -> dict[str, int]:
    """
    Get all supported timeframes and their durations in minutes.
    
    Returns:
        Dict of tf string -> minutes
    """
    return dict(TF_MINUTES)


def ceil_to_tf_close(dt: datetime, tf: str) -> datetime:
    """
    Align a datetime to the next TF close boundary (ceiling).

    If dt is already on a TF close boundary, returns dt unchanged.
    Otherwise, returns the next TF close after dt.

    Used for no-lookahead evaluation start alignment:
    - eval_start = ceil_to_tf_close(window_start, exec_tf) + delay_bars * tf_duration

    Args:
        dt: Datetime to align (naive UTC or aware with any timezone)
        tf: Timeframe string (e.g., "5m", "1h", "4h")

    Returns:
        Datetime aligned to TF close boundary (ceiling).
        Returns naive datetime if input was naive, aware if input was aware.

    Examples:
        >>> ceil_to_tf_close(datetime(2024, 1, 1, 10, 3), "5m")
        datetime(2024, 1, 1, 10, 5)  # Next 5m close

        >>> ceil_to_tf_close(datetime(2024, 1, 1, 10, 5), "5m")
        datetime(2024, 1, 1, 10, 5)  # Already on boundary
    """
    tf_min = tf_minutes(tf)

    # P2-003 FIX: Handle timezone-aware datetimes correctly
    # dt.timestamp() always returns UTC seconds regardless of timezone,
    # so the modulo calculation is consistent. We preserve the original
    # tzinfo in the returned datetime.
    original_tz = dt.tzinfo

    # Convert to minutes since epoch for modulo calculation
    # Note: timestamp() returns UTC epoch seconds for both naive and aware datetimes
    total_minutes = int(dt.timestamp() // 60)

    # Check if already on boundary
    remainder = total_minutes % tf_min
    if remainder == 0:
        return dt

    # Calculate minutes to add to reach next boundary
    minutes_to_add = tf_min - remainder

    result = dt + timedelta(minutes=minutes_to_add)

    # Ensure we preserve timezone info
    if original_tz is not None and result.tzinfo is None:
        result = result.replace(tzinfo=original_tz)

    return result

