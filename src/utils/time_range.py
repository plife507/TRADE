"""
TimeRange abstraction for time-sensitive Bybit API queries.

This module provides a consistent, validated way to handle time ranges
for history endpoints (transaction log, order history, closed PnL, etc.).

CRITICAL: All history queries MUST use TimeRange. Never rely on Bybit's
implicit defaults (24h for transaction log, 7d for orders, etc.).

Bybit API Time Constraints (from docs):
| Endpoint         | Default Window | Max Range  |
|------------------|----------------|------------|
| Transaction Log  | 24 hours       | 7 days     |
| Order History    | 7 days         | 7 days     |
| Trade History    | 7 days         | 7 days     |
| Closed PnL       | 7 days         | 7 days     |
| Borrow History   | 30 days        | 30 days    |
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, Optional, Tuple


class TimeRangePreset(Enum):
    """Preset time windows for convenience."""
    LAST_1H = "1h"
    LAST_4H = "4h"
    LAST_24H = "24h"
    LAST_7D = "7d"
    LAST_30D = "30d"
    CUSTOM = "custom"


# Maximum allowed ranges per endpoint type
MAX_RANGE_DAYS = {
    "transaction_log": 7,
    "order_history": 7,
    "trade_history": 7,
    "closed_pnl": 7,
    "borrow_history": 30,
    "default": 7,  # Conservative default
}


@dataclass(frozen=True)
class TimeRange:
    """
    Represents a validated time range for Bybit API queries.
    
    All times are in milliseconds (epoch) and UTC.
    
    Attributes:
        start_ms: Start timestamp in milliseconds (UTC)
        end_ms: End timestamp in milliseconds (UTC)
        label: Human-readable label (e.g., "last_24h", "last_7d", "custom")
        endpoint_type: The type of endpoint this range is for (for max validation)
    
    Usage:
        # Create from preset
        time_range = TimeRange.last_24h()
        time_range = TimeRange.last_7d()
        
        # Create from custom dates
        time_range = TimeRange.from_dates(start_dt, end_dt)
        
        # Convert to Bybit params
        params = time_range.to_bybit_params()
        # Returns: {"startTime": 1234567890000, "endTime": 1234567999000}
    """
    start_ms: int
    end_ms: int
    label: str
    endpoint_type: str = "default"
    
    def __post_init__(self):
        """Validate the time range."""
        if self.start_ms >= self.end_ms:
            raise ValueError(
                f"Invalid TimeRange: start_ms ({self.start_ms}) must be less than end_ms ({self.end_ms})"
            )
        
        if self.start_ms < 0 or self.end_ms < 0:
            raise ValueError("TimeRange timestamps must be positive")
        
        # Validate max range for endpoint type
        max_days = MAX_RANGE_DAYS.get(self.endpoint_type, MAX_RANGE_DAYS["default"])
        max_ms = max_days * 24 * 60 * 60 * 1000
        actual_range_ms = self.end_ms - self.start_ms
        
        if actual_range_ms > max_ms:
            actual_days = actual_range_ms / (24 * 60 * 60 * 1000)
            raise ValueError(
                f"TimeRange exceeds maximum for {self.endpoint_type}: "
                f"{actual_days:.1f} days > {max_days} days max"
            )
    
    # =========================================================================
    # Factory Methods (Presets)
    # =========================================================================
    
    @classmethod
    def last_1h(cls, now: Optional[datetime] = None, endpoint_type: str = "default") -> "TimeRange":
        """Create a time range for the last 1 hour."""
        return cls._from_hours_back(1, now, "last_1h", endpoint_type)
    
    @classmethod
    def last_4h(cls, now: Optional[datetime] = None, endpoint_type: str = "default") -> "TimeRange":
        """Create a time range for the last 4 hours."""
        return cls._from_hours_back(4, now, "last_4h", endpoint_type)
    
    @classmethod
    def last_24h(cls, now: Optional[datetime] = None, endpoint_type: str = "default") -> "TimeRange":
        """Create a time range for the last 24 hours."""
        return cls._from_hours_back(24, now, "last_24h", endpoint_type)
    
    @classmethod
    def last_7d(cls, now: Optional[datetime] = None, endpoint_type: str = "default") -> "TimeRange":
        """Create a time range for the last 7 days."""
        return cls._from_days_back(7, now, "last_7d", endpoint_type)
    
    @classmethod
    def last_30d(cls, now: Optional[datetime] = None, endpoint_type: str = "default") -> "TimeRange":
        """Create a time range for the last 30 days (only valid for borrow_history)."""
        return cls._from_days_back(30, now, "last_30d", endpoint_type)
    
    @classmethod
    def from_preset(
        cls,
        preset: TimeRangePreset,
        now: Optional[datetime] = None,
        endpoint_type: str = "default",
    ) -> "TimeRange":
        """
        Create a TimeRange from a preset.
        
        Args:
            preset: One of LAST_1H, LAST_4H, LAST_24H, LAST_7D, LAST_30D
            now: Reference time (defaults to current UTC time)
            endpoint_type: The endpoint type for max range validation
        
        Returns:
            TimeRange instance
        
        Raises:
            ValueError: If preset is CUSTOM (use from_dates instead)
        """
        if preset == TimeRangePreset.CUSTOM:
            raise ValueError("Use TimeRange.from_dates() for custom time ranges")
        
        factory_map = {
            TimeRangePreset.LAST_1H: cls.last_1h,
            TimeRangePreset.LAST_4H: cls.last_4h,
            TimeRangePreset.LAST_24H: cls.last_24h,
            TimeRangePreset.LAST_7D: cls.last_7d,
            TimeRangePreset.LAST_30D: cls.last_30d,
        }
        
        return factory_map[preset](now=now, endpoint_type=endpoint_type)
    
    @classmethod
    def from_window_string(
        cls,
        window: str,
        now: Optional[datetime] = None,
        endpoint_type: str = "default",
    ) -> "TimeRange":
        """
        Create a TimeRange from a window string like "24h", "7d", "30d".
        
        Args:
            window: Window string (e.g., "1h", "4h", "24h", "7d", "30d")
            now: Reference time (defaults to current UTC time)
            endpoint_type: The endpoint type for max range validation
        
        Returns:
            TimeRange instance
        
        Raises:
            ValueError: If window string is invalid
        """
        window = window.lower().strip()
        
        # Try preset mapping first
        preset_map = {
            "1h": TimeRangePreset.LAST_1H,
            "4h": TimeRangePreset.LAST_4H,
            "24h": TimeRangePreset.LAST_24H,
            "1d": TimeRangePreset.LAST_24H,
            "7d": TimeRangePreset.LAST_7D,
            "1w": TimeRangePreset.LAST_7D,
            "30d": TimeRangePreset.LAST_30D,
            "1m": TimeRangePreset.LAST_30D,
        }
        
        if window in preset_map:
            return cls.from_preset(preset_map[window], now=now, endpoint_type=endpoint_type)
        
        # Try to parse custom format like "3d", "12h"
        try:
            if window.endswith("h"):
                hours = int(window[:-1])
                return cls._from_hours_back(hours, now, f"last_{hours}h", endpoint_type)
            elif window.endswith("d"):
                days = int(window[:-1])
                return cls._from_days_back(days, now, f"last_{days}d", endpoint_type)
            else:
                raise ValueError(f"Invalid window format: '{window}'. Use format like '24h' or '7d'")
        except ValueError as e:
            if "Invalid window format" in str(e):
                raise
            raise ValueError(f"Invalid window format: '{window}'. Use format like '24h' or '7d'")
    
    # =========================================================================
    # Factory Methods (Custom)
    # =========================================================================
    
    @classmethod
    def from_dates(
        cls,
        start: datetime,
        end: datetime,
        endpoint_type: str = "default",
    ) -> "TimeRange":
        """
        Create a TimeRange from datetime objects.
        
        Args:
            start: Start datetime (will be converted to UTC if naive)
            end: End datetime (will be converted to UTC if naive)
            endpoint_type: The endpoint type for max range validation
        
        Returns:
            TimeRange instance
        
        Raises:
            ValueError: If range exceeds max for endpoint type
        """
        # Ensure UTC
        start_utc = cls._to_utc(start)
        end_utc = cls._to_utc(end)
        
        start_ms = int(start_utc.timestamp() * 1000)
        end_ms = int(end_utc.timestamp() * 1000)
        
        # Format label with readable dates
        start_str = start_utc.strftime("%Y-%m-%d %H:%M")
        end_str = end_utc.strftime("%Y-%m-%d %H:%M")
        label = f"custom ({start_str} to {end_str} UTC)"
        
        return cls(
            start_ms=start_ms,
            end_ms=end_ms,
            label=label,
            endpoint_type=endpoint_type,
        )
    
    @classmethod
    def from_timestamps_ms(
        cls,
        start_ms: int,
        end_ms: int,
        endpoint_type: str = "default",
    ) -> "TimeRange":
        """
        Create a TimeRange from millisecond timestamps.
        
        Args:
            start_ms: Start timestamp in milliseconds
            end_ms: End timestamp in milliseconds
            endpoint_type: The endpoint type for max range validation
        
        Returns:
            TimeRange instance
        """
        # Format label with readable dates
        start_dt = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc)
        end_dt = datetime.fromtimestamp(end_ms / 1000, tz=timezone.utc)
        start_str = start_dt.strftime("%Y-%m-%d %H:%M")
        end_str = end_dt.strftime("%Y-%m-%d %H:%M")
        label = f"custom ({start_str} to {end_str} UTC)"
        
        return cls(
            start_ms=start_ms,
            end_ms=end_ms,
            label=label,
            endpoint_type=endpoint_type,
        )
    
    # =========================================================================
    # Conversion Methods
    # =========================================================================
    
    def to_bybit_params(self) -> Dict[str, int]:
        """
        Convert to Bybit API parameters.
        
        Returns:
            Dict with 'startTime' and 'endTime' keys (milliseconds)
        """
        return {
            "startTime": self.start_ms,
            "endTime": self.end_ms,
        }
    
    def to_dict(self) -> Dict:
        """
        Convert to a dictionary for inclusion in ToolResult.data.
        
        Returns:
            Dict with start_ms, end_ms, label, start_iso, end_iso
        """
        start_dt = datetime.fromtimestamp(self.start_ms / 1000, tz=timezone.utc)
        end_dt = datetime.fromtimestamp(self.end_ms / 1000, tz=timezone.utc)
        
        return {
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "label": self.label,
            "start_iso": start_dt.isoformat(),
            "end_iso": end_dt.isoformat(),
            "endpoint_type": self.endpoint_type,
        }
    
    def to_tuple_ms(self) -> Tuple[int, int]:
        """Return (start_ms, end_ms) tuple."""
        return (self.start_ms, self.end_ms)
    
    # =========================================================================
    # Display Methods
    # =========================================================================
    
    @property
    def start_datetime(self) -> datetime:
        """Get start time as datetime (UTC)."""
        return datetime.fromtimestamp(self.start_ms / 1000, tz=timezone.utc)
    
    @property
    def end_datetime(self) -> datetime:
        """Get end time as datetime (UTC)."""
        return datetime.fromtimestamp(self.end_ms / 1000, tz=timezone.utc)
    
    @property
    def duration_hours(self) -> float:
        """Get duration in hours."""
        return (self.end_ms - self.start_ms) / (1000 * 60 * 60)
    
    @property
    def duration_days(self) -> float:
        """Get duration in days."""
        return self.duration_hours / 24
    
    def format_range(self) -> str:
        """
        Format the range for display.
        
        Returns:
            String like "Dec 1, 2024 00:00 - Dec 7, 2024 23:59 UTC (7d)"
        """
        start_str = self.start_datetime.strftime("%b %d, %Y %H:%M")
        end_str = self.end_datetime.strftime("%b %d, %Y %H:%M")
        
        # Duration label
        if self.duration_hours < 24:
            duration = f"{self.duration_hours:.0f}h"
        else:
            duration = f"{self.duration_days:.1f}d"
        
        return f"{start_str} - {end_str} UTC ({duration})"
    
    def __str__(self) -> str:
        """String representation."""
        return f"TimeRange({self.label}: {self.format_range()})"
    
    def __repr__(self) -> str:
        """Detailed representation."""
        return (
            f"TimeRange(start_ms={self.start_ms}, end_ms={self.end_ms}, "
            f"label='{self.label}', endpoint_type='{self.endpoint_type}')"
        )
    
    # =========================================================================
    # Private Helpers
    # =========================================================================
    
    @classmethod
    def _from_hours_back(
        cls,
        hours: int,
        now: Optional[datetime],
        label: str,
        endpoint_type: str,
    ) -> "TimeRange":
        """Create a time range going back N hours from now."""
        now_utc = cls._get_now_utc(now)
        start_utc = now_utc - timedelta(hours=hours)
        
        return cls(
            start_ms=int(start_utc.timestamp() * 1000),
            end_ms=int(now_utc.timestamp() * 1000),
            label=label,
            endpoint_type=endpoint_type,
        )
    
    @classmethod
    def _from_days_back(
        cls,
        days: int,
        now: Optional[datetime],
        label: str,
        endpoint_type: str,
    ) -> "TimeRange":
        """Create a time range going back N days from now."""
        now_utc = cls._get_now_utc(now)
        start_utc = now_utc - timedelta(days=days)
        
        return cls(
            start_ms=int(start_utc.timestamp() * 1000),
            end_ms=int(now_utc.timestamp() * 1000),
            label=label,
            endpoint_type=endpoint_type,
        )
    
    @staticmethod
    def _get_now_utc(now: Optional[datetime]) -> datetime:
        """Get current UTC time or convert provided time to UTC."""
        if now is None:
            return datetime.now(timezone.utc)
        return TimeRange._to_utc(now)
    
    @staticmethod
    def _to_utc(dt: datetime) -> datetime:
        """Convert datetime to UTC, assuming UTC if naive."""
        if dt.tzinfo is None:
            # Assume naive datetime is UTC
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)


# =============================================================================
# Convenience Functions
# =============================================================================

def parse_time_window(
    window: Optional[str] = None,
    start_ms: Optional[int] = None,
    end_ms: Optional[int] = None,
    endpoint_type: str = "default",
    default_window: str = "24h",
) -> TimeRange:
    """
    Parse time range from various input formats.
    
    This is the primary entry point for tools that need to accept flexible
    time range inputs.
    
    Args:
        window: Window string like "24h", "7d" (takes precedence if provided)
        start_ms: Start timestamp in ms (used if window not provided)
        end_ms: End timestamp in ms (used if window not provided)
        endpoint_type: The endpoint type for validation
        default_window: Default window if nothing provided
    
    Returns:
        TimeRange instance
    
    Raises:
        ValueError: If inputs are invalid or range exceeds max
    
    Examples:
        # Using window string
        tr = parse_time_window(window="7d", endpoint_type="order_history")
        
        # Using explicit timestamps
        tr = parse_time_window(start_ms=1700000000000, end_ms=1700086400000)
        
        # Uses default_window if nothing provided
        tr = parse_time_window(endpoint_type="transaction_log")  # Uses "24h"
    """
    # Priority: window string > explicit timestamps > default
    if window:
        return TimeRange.from_window_string(window, endpoint_type=endpoint_type)
    
    if start_ms is not None and end_ms is not None:
        return TimeRange.from_timestamps_ms(start_ms, end_ms, endpoint_type=endpoint_type)
    
    if start_ms is not None or end_ms is not None:
        raise ValueError(
            "Both start_ms and end_ms must be provided together, or use window string"
        )
    
    # Use default
    return TimeRange.from_window_string(default_window, endpoint_type=endpoint_type)


def get_max_range_days(endpoint_type: str) -> int:
    """Get maximum allowed range in days for an endpoint type."""
    return MAX_RANGE_DAYS.get(endpoint_type, MAX_RANGE_DAYS["default"])

