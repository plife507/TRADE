"""
Datetime normalization and validation utilities.

Single source of truth for datetime parsing across the codebase.
"""

from datetime import datetime, timezone

# Maximum allowed range in days for query tools (to prevent bloat)
MAX_QUERY_RANGE_DAYS = 365


def normalize_datetime(
    value: datetime | str | None,
    param_name: str = "datetime",
) -> tuple[datetime | None, str | None]:
    """
    Normalize a datetime value from various input formats.

    Args:
        value: A datetime object, ISO-format string, or None
        param_name: Parameter name for error messages

    Returns:
        Tuple of (normalized_datetime, error_message)
        - If successful: (datetime, None)
        - If failed: (None, error_string)
    """
    if value is None:
        return None, None

    if isinstance(value, datetime):
        return value, None

    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None, None

        # Try multiple common ISO formats
        formats = [
            "%Y-%m-%dT%H:%M:%S",      # Full ISO
            "%Y-%m-%dT%H:%M",          # ISO without seconds
            "%Y-%m-%d %H:%M:%S",       # Space separator with seconds
            "%Y-%m-%d %H:%M",          # Space separator without seconds
            "%Y-%m-%d",                # Date only
        ]

        for fmt in formats:
            try:
                return datetime.strptime(value, fmt), None
            except ValueError:
                continue

        # Try fromisoformat as fallback (handles more edge cases)
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")), None
        except ValueError:
            pass

        return None, f"Invalid {param_name} format: '{value}'. Use YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS"

    return None, f"Invalid {param_name} type: expected datetime or string, got {type(value).__name__}"


def validate_time_range(
    start: datetime | None,
    end: datetime | None,
    max_days: int = MAX_QUERY_RANGE_DAYS,
) -> tuple[bool, str | None]:
    """
    Validate a time range for reasonableness.

    Args:
        start: Start datetime
        end: End datetime
        max_days: Maximum allowed range in days

    Returns:
        Tuple of (is_valid, error_message)
    """
    if start is None and end is None:
        return True, None

    if start is not None and end is not None:
        if start >= end:
            return False, "Start time must be before end time"

        duration = end - start
        if duration.days > max_days:
            return False, f"Time range too large: {duration.days} days exceeds maximum of {max_days} days"

    return True, None


def normalize_time_range_params(
    start: datetime | str | None,
    end: datetime | str | None,
    max_days: int = MAX_QUERY_RANGE_DAYS,
) -> tuple[datetime | None, datetime | None, str | None]:
    """
    Normalize and validate start/end time range parameters.

    Args:
        start: Start time as datetime or ISO string
        end: End time as datetime or ISO string
        max_days: Maximum allowed range in days

    Returns:
        Tuple of (start_dt, end_dt, error_message)
        - If successful: (start_datetime, end_datetime, None)
        - If failed: (None, None, error_string)
    """
    # Normalize start
    start_dt, start_err = normalize_datetime(start, "start")
    if start_err:
        return None, None, start_err

    # Normalize end
    end_dt, end_err = normalize_datetime(end, "end")
    if end_err:
        return None, None, end_err

    # Validate range
    is_valid, range_err = validate_time_range(start_dt, end_dt, max_days)
    if not is_valid:
        return None, None, range_err

    return start_dt, end_dt, None


def normalize_datetime_for_storage(dt: datetime | str | None) -> str | None:
    """
    Normalize a datetime to ISO format string for storage.

    Args:
        dt: Datetime object or ISO string

    Returns:
        ISO format string (YYYY-MM-DDTHH:MM:SS) or None
    """
    if dt is None:
        return None

    normalized, err = normalize_datetime(dt)
    if err or normalized is None:
        return None

    return normalized.strftime("%Y-%m-%dT%H:%M:%S")


def datetime_to_epoch_ms(dt: datetime | None) -> int | None:
    """
    Convert datetime to epoch milliseconds.

    Handles both timezone-aware and naive datetimes.
    Naive datetimes are assumed to be UTC.

    Args:
        dt: Datetime object or None

    Returns:
        Epoch milliseconds as int, or None if input is None
    """
    if dt is None:
        return None
    # Handle both aware and naive datetimes
    if dt.tzinfo is not None:
        return int(dt.timestamp() * 1000)
    # Assume naive datetime is UTC
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)
