"""
Timeframe utilities for the backtest runtime.

Provides timeframe duration calculation and validation.
Uses TF_MINUTES from the data store as the source of truth.

Timeframe Role Definitions (1m Action Model):

    action_tf: Always 1m. The timeframe at which signals are evaluated and
        TP/SL is checked. This is fixed and not configurable. In backtest,
        we iterate every 1m bar within each eval_tf bar.

    eval_tf: The resolved execution timeframe from Play YAML. Determines bar-stepping
        granularity and indicator computation timing. E.g., if eval_tf="15m",
        we process 15m bars but evaluate signals at every 1m within each.

    condition_tf (low_tf/med_tf/high_tf): Timeframes used for indicators and
        structures. These define when indicator values update (on their TF close)
        and forward-fill until the next close.

    low_tf (Low Timeframe): 1m, 3m, 5m, 15m - Execution timing, micro-structure
    med_tf (Medium Timeframe): 30m, 1h, 2h, 4h - Trade bias + structure context
    high_tf (High Timeframe): 6h, 12h, 1D - Higher-level trend (capped at 1D)

    exec (Pointer): Points to which of low_tf/med_tf/high_tf to use for bar-stepping

Hierarchy Rule:
    high_tf >= med_tf >= low_tf (in minutes)
    Enforced by validate_tf_mapping()

Note: Close detection is data-driven (via close_ts maps), not modulo-based.
This module only provides duration helpers for warmup/buffer calculations.
"""

from datetime import datetime, timedelta

# Import TF_MINUTES from data store (canonical source)
from ...data.historical_data_store import TF_MINUTES

# =============================================================================
# Constants
# =============================================================================

# Fixed action timeframe - signals are evaluated and TP/SL checked at this granularity
ACTION_TF = "1m"
ACTION_TF_MINUTES = 1

# Maximum window duration for window operators (holds_for_duration, etc.)
WINDOW_DURATION_CEILING_MINUTES = 1440  # 24 hours


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
    Validate a 3-feed + exec role timeframe mapping.

    Required keys: low_tf, med_tf, high_tf, exec
    - low_tf, med_tf, high_tf: actual timeframe strings (e.g., "15m", "1h", "4h")
    - exec: role pointer, must be one of "low_tf", "med_tf", "high_tf"

    Hierarchy rule: high_tf >= med_tf >= low_tf (in minutes)

    Args:
        tf_mapping: Dict with keys low_tf, med_tf, high_tf, exec

    Raises:
        ValueError: If mapping is invalid or timeframes don't follow hierarchy
    """
    required_keys = {"low_tf", "med_tf", "high_tf", "exec"}
    missing = required_keys - set(tf_mapping.keys())
    if missing:
        raise ValueError(f"Missing required tf_mapping keys: {missing}")

    # Validate exec points to valid role
    exec_role = tf_mapping["exec"]
    if exec_role not in ("low_tf", "med_tf", "high_tf"):
        raise ValueError(
            f"exec must be one of low_tf/med_tf/high_tf, got: {exec_role}"
        )

    # Validate each timeframe string exists (skip 'exec' which is a role pointer)
    for role, tf in tf_mapping.items():
        if role == "exec":
            continue  # exec is a role pointer, not a TF string
        if tf.lower() not in TF_MINUTES:
            raise ValueError(
                f"Unknown timeframe '{tf}' for role '{role}'. "
                f"Supported: {list(TF_MINUTES.keys())}"
            )

    # Validate hierarchy: high_tf >= med_tf >= low_tf (in minutes)
    low_tf_min = tf_minutes(tf_mapping["low_tf"])
    med_tf_min = tf_minutes(tf_mapping["med_tf"])
    high_tf_min = tf_minutes(tf_mapping["high_tf"])

    if not (high_tf_min >= med_tf_min >= low_tf_min):
        raise ValueError(
            f"Invalid tf_mapping hierarchy: high_tf ({tf_mapping['high_tf']}={high_tf_min}m) "
            f"must be >= med_tf ({tf_mapping['med_tf']}={med_tf_min}m) "
            f"must be >= low_tf ({tf_mapping['low_tf']}={low_tf_min}m)"
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

