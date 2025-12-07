"""
Tests for TimeRange abstraction.

Validates that:
1. TimeRange presets create correct ms timestamps
2. Invalid ranges (end < start, exceeds max) raise errors
3. to_bybit_params() always returns startTime and endTime
4. parse_time_window() handles all input formats
"""

import pytest
from datetime import datetime, timezone, timedelta

from src.utils.time_range import (
    TimeRange,
    TimeRangePreset,
    parse_time_window,
    get_max_range_days,
    MAX_RANGE_DAYS,
)


class TestTimeRangeBasics:
    """Test basic TimeRange creation and validation."""
    
    def test_last_24h_creates_valid_range(self):
        """last_24h should create a range from 24h ago to now."""
        now = datetime(2024, 12, 7, 12, 0, 0, tzinfo=timezone.utc)
        tr = TimeRange.last_24h(now=now)
        
        assert tr.label == "last_24h"
        assert tr.end_ms == int(now.timestamp() * 1000)
        assert tr.start_ms == int((now - timedelta(hours=24)).timestamp() * 1000)
        assert tr.duration_hours == 24.0
    
    def test_last_7d_creates_valid_range(self):
        """last_7d should create a range from 7 days ago to now."""
        now = datetime(2024, 12, 7, 12, 0, 0, tzinfo=timezone.utc)
        tr = TimeRange.last_7d(now=now)
        
        assert tr.label == "last_7d"
        assert tr.duration_days == 7.0
    
    def test_last_30d_creates_valid_range(self):
        """last_30d should create a range from 30 days ago to now."""
        now = datetime(2024, 12, 7, 12, 0, 0, tzinfo=timezone.utc)
        tr = TimeRange.last_30d(now=now, endpoint_type="borrow_history")
        
        assert tr.label == "last_30d"
        assert tr.duration_days == 30.0
    
    def test_invalid_range_start_after_end_raises(self):
        """TimeRange should raise ValueError if start >= end."""
        with pytest.raises(ValueError, match="must be less than"):
            TimeRange(
                start_ms=1000000000000,  # Later
                end_ms=900000000000,      # Earlier
                label="invalid",
            )
    
    def test_negative_timestamps_raise(self):
        """TimeRange should raise ValueError for negative timestamps."""
        with pytest.raises(ValueError, match="must be positive"):
            TimeRange(start_ms=-1000, end_ms=1000000, label="invalid")
    
    def test_exceeds_max_range_raises(self):
        """TimeRange should raise ValueError if range exceeds max for endpoint type."""
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=10)  # 10 days exceeds 7-day max
        
        with pytest.raises(ValueError, match="exceeds maximum"):
            TimeRange.from_dates(start, now, endpoint_type="order_history")
    
    def test_30d_allowed_for_borrow_history(self):
        """30-day range should be allowed for borrow_history endpoint."""
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=25)
        
        # Should not raise
        tr = TimeRange.from_dates(start, now, endpoint_type="borrow_history")
        assert tr.duration_days == 25.0


class TestTimeRangeBybitParams:
    """Test conversion to Bybit API parameters."""
    
    def test_to_bybit_params_returns_both_times(self):
        """to_bybit_params must always return startTime and endTime."""
        tr = TimeRange.last_24h()
        params = tr.to_bybit_params()
        
        assert "startTime" in params
        assert "endTime" in params
        assert isinstance(params["startTime"], int)
        assert isinstance(params["endTime"], int)
        assert params["startTime"] < params["endTime"]
    
    def test_to_bybit_params_matches_timestamps(self):
        """Bybit params should match the internal ms timestamps."""
        tr = TimeRange.last_7d()
        params = tr.to_bybit_params()
        
        assert params["startTime"] == tr.start_ms
        assert params["endTime"] == tr.end_ms
    
    def test_to_dict_includes_all_fields(self):
        """to_dict should include start, end, label, and ISO strings."""
        tr = TimeRange.last_24h()
        d = tr.to_dict()
        
        assert "start_ms" in d
        assert "end_ms" in d
        assert "label" in d
        assert "start_iso" in d
        assert "end_iso" in d
        assert "endpoint_type" in d


class TestTimeRangeFromWindow:
    """Test creating TimeRange from window strings."""
    
    def test_from_window_string_24h(self):
        """'24h' should create a 24-hour range."""
        tr = TimeRange.from_window_string("24h")
        assert tr.label == "last_24h"
        assert 23.9 <= tr.duration_hours <= 24.1
    
    def test_from_window_string_7d(self):
        """'7d' should create a 7-day range."""
        tr = TimeRange.from_window_string("7d")
        assert tr.label == "last_7d"
        assert 6.9 <= tr.duration_days <= 7.1
    
    def test_from_window_string_1w(self):
        """'1w' should be alias for 7 days."""
        tr = TimeRange.from_window_string("1w")
        assert tr.label == "last_7d"
    
    def test_from_window_string_custom_hours(self):
        """Custom hour format like '4h' should work."""
        tr = TimeRange.from_window_string("4h")
        assert tr.label == "last_4h"
        assert 3.9 <= tr.duration_hours <= 4.1
    
    def test_from_window_string_custom_days(self):
        """Custom day format like '3d' should work."""
        tr = TimeRange.from_window_string("3d")
        assert tr.label == "last_3d"
        assert 2.9 <= tr.duration_days <= 3.1
    
    def test_from_window_string_invalid_raises(self):
        """Invalid window format should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid window format"):
            TimeRange.from_window_string("invalid")
        
        with pytest.raises(ValueError, match="Invalid window format"):
            TimeRange.from_window_string("10x")


class TestTimeRangeFromDates:
    """Test creating TimeRange from datetime objects."""
    
    def test_from_dates_naive_assumed_utc(self):
        """Naive datetimes should be treated as UTC."""
        start = datetime(2024, 12, 1, 0, 0, 0)  # Naive
        end = datetime(2024, 12, 7, 0, 0, 0)    # Naive
        
        tr = TimeRange.from_dates(start, end)
        
        # Should have been converted to UTC
        assert "custom" in tr.label
        assert tr.duration_days == 6.0
    
    def test_from_dates_aware_converted_to_utc(self):
        """Timezone-aware datetimes should be converted to UTC."""
        from datetime import timezone as tz
        
        # Create times in different timezone (e.g., UTC+5)
        tz_plus5 = tz(timedelta(hours=5))
        start = datetime(2024, 12, 1, 5, 0, 0, tzinfo=tz_plus5)  # 00:00 UTC
        end = datetime(2024, 12, 2, 5, 0, 0, tzinfo=tz_plus5)    # 00:00 UTC next day
        
        tr = TimeRange.from_dates(start, end)
        
        assert tr.duration_days == 1.0
    
    def test_from_timestamps_ms(self):
        """from_timestamps_ms should create TimeRange from ms values."""
        start_ms = 1700000000000
        end_ms = 1700100000000
        
        tr = TimeRange.from_timestamps_ms(start_ms, end_ms)
        
        assert tr.start_ms == start_ms
        assert tr.end_ms == end_ms
        assert "custom" in tr.label


class TestParseTimeWindow:
    """Test the parse_time_window convenience function."""
    
    def test_window_takes_priority(self):
        """Window string should take priority over timestamps."""
        tr = parse_time_window(
            window="24h",
            start_ms=1000,  # Should be ignored
            end_ms=2000,    # Should be ignored
        )
        
        assert tr.label == "last_24h"
        assert tr.start_ms != 1000
    
    def test_timestamps_used_if_no_window(self):
        """Timestamps should be used if window is None."""
        tr = parse_time_window(
            window=None,
            start_ms=1700000000000,
            end_ms=1700100000000,
        )
        
        assert tr.start_ms == 1700000000000
        assert tr.end_ms == 1700100000000
    
    def test_default_window_used_if_nothing_provided(self):
        """Default window should be used if nothing provided."""
        tr = parse_time_window(
            window=None,
            start_ms=None,
            end_ms=None,
            default_window="7d",
        )
        
        assert tr.label == "last_7d"
    
    def test_partial_timestamps_raise(self):
        """Providing only start_ms or only end_ms should raise ValueError."""
        with pytest.raises(ValueError, match="must be provided together"):
            parse_time_window(start_ms=1000)
        
        with pytest.raises(ValueError, match="must be provided together"):
            parse_time_window(end_ms=2000)
    
    def test_endpoint_type_passed_through(self):
        """Endpoint type should be passed to TimeRange for validation."""
        # 8 days should fail for order_history (max 7d)
        # The error may be wrapped with "Invalid window format" on some paths
        with pytest.raises(ValueError):
            parse_time_window(
                window="8d",
                endpoint_type="order_history",
            )
        
        # But 8 days should work for borrow_history (max 30d)
        tr = parse_time_window(
            window="8d",
            endpoint_type="borrow_history",
        )
        assert 7.9 <= tr.duration_days <= 8.1


class TestTimeRangePresets:
    """Test TimeRangePreset enum and from_preset factory."""
    
    def test_from_preset_all_presets(self):
        """All presets except CUSTOM should work (with appropriate endpoint_type)."""
        # Test presets that work with default (7d max)
        for preset in [TimeRangePreset.LAST_1H, TimeRangePreset.LAST_4H, 
                       TimeRangePreset.LAST_24H, TimeRangePreset.LAST_7D]:
            tr = TimeRange.from_preset(preset)
            assert tr is not None
        
        # LAST_30D requires borrow_history endpoint (30d max)
        tr = TimeRange.from_preset(TimeRangePreset.LAST_30D, endpoint_type="borrow_history")
        assert tr is not None
    
    def test_from_preset_custom_raises(self):
        """CUSTOM preset should raise ValueError."""
        with pytest.raises(ValueError, match="Use TimeRange.from_dates"):
            TimeRange.from_preset(TimeRangePreset.CUSTOM)


class TestMaxRangeDays:
    """Test max range configuration."""
    
    def test_get_max_range_days(self):
        """get_max_range_days should return correct values."""
        assert get_max_range_days("transaction_log") == 7
        assert get_max_range_days("order_history") == 7
        assert get_max_range_days("borrow_history") == 30
        assert get_max_range_days("unknown") == 7  # Default
    
    def test_max_range_days_constant(self):
        """MAX_RANGE_DAYS should have expected values."""
        assert MAX_RANGE_DAYS["transaction_log"] == 7
        assert MAX_RANGE_DAYS["borrow_history"] == 30
        assert "default" in MAX_RANGE_DAYS


class TestTimeRangeDisplay:
    """Test display and formatting methods."""
    
    def test_format_range(self):
        """format_range should return human-readable string."""
        now = datetime(2024, 12, 7, 12, 0, 0, tzinfo=timezone.utc)
        tr = TimeRange.last_24h(now=now)
        
        formatted = tr.format_range()
        
        assert "Dec 06" in formatted or "Dec 07" in formatted
        assert "UTC" in formatted
        assert "24h" in formatted or "1.0d" in formatted
    
    def test_str_representation(self):
        """__str__ should be informative."""
        tr = TimeRange.last_7d()
        s = str(tr)
        
        assert "TimeRange" in s
        assert "last_7d" in s
    
    def test_repr_detailed(self):
        """__repr__ should include all fields."""
        tr = TimeRange.last_24h()
        r = repr(tr)
        
        assert "start_ms=" in r
        assert "end_ms=" in r
        assert "label=" in r


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

