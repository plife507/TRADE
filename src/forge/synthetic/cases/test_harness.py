"""
Tests for the synthetic test harness itself.

Validates that SyntheticSnapshot correctly provides controlled values
for DSL evaluation testing.
"""

import pytest
from tests.synthetic.harness.snapshot import SyntheticSnapshot


class TestSyntheticSnapshotCreation:
    """Test snapshot creation methods."""

    def test_empty_snapshot(self):
        """Empty snapshot should be valid."""
        snapshot = SyntheticSnapshot()
        assert snapshot.get("nonexistent") is None

    def test_with_features(self):
        """Create snapshot with specific features."""
        snapshot = SyntheticSnapshot.with_features({
            "ema_9": 52.0,
            "rsi_14": 45.0,
        })
        assert snapshot.get("ema_9") == 52.0
        assert snapshot.get("rsi_14") == 45.0

    def test_with_structure_fields(self):
        """Create snapshot with dot-notation structure fields."""
        snapshot = SyntheticSnapshot.with_features({
            "swing.high_level": 100.0,
            "swing.low_level": 80.0,
            "zone.state": "active",
        })
        assert snapshot.get("swing.high_level") == 100.0
        assert snapshot.get("swing.low_level") == 80.0
        assert snapshot.get("zone.state") == "active"

    def test_with_history(self):
        """Create snapshot with feature history."""
        snapshot = SyntheticSnapshot.with_history({
            "ema_9": [48.0, 49.0, 51.0],
        })
        # Current (offset 0) = last element
        assert snapshot.get("ema_9") == 51.0

    def test_with_ohlcv(self):
        """Create snapshot with OHLCV data."""
        snapshot = SyntheticSnapshot.with_ohlcv([
            {"open": 100, "high": 105, "low": 98, "close": 103, "volume": 1000},
            {"open": 103, "high": 108, "low": 101, "close": 106, "volume": 1200},
        ])
        assert snapshot.get("close") == 106
        assert snapshot.get("high") == 108
        assert snapshot.close == 106


class TestGetWithOffset:
    """Test offset-based feature access."""

    def test_offset_zero_current(self):
        """Offset 0 returns current bar."""
        snapshot = SyntheticSnapshot.with_history({
            "rsi_14": [30, 40, 50, 60, 70],  # Current = 70
        })
        assert snapshot.get_with_offset("rsi_14", 0) == 70

    def test_offset_one_previous(self):
        """Offset 1 returns previous bar."""
        snapshot = SyntheticSnapshot.with_history({
            "rsi_14": [30, 40, 50, 60, 70],
        })
        assert snapshot.get_with_offset("rsi_14", 1) == 60

    def test_offset_exceeds_history(self):
        """Offset beyond history returns None."""
        snapshot = SyntheticSnapshot.with_history({
            "rsi_14": [50, 60, 70],  # Only 3 bars
        })
        assert snapshot.get_with_offset("rsi_14", 0) == 70
        assert snapshot.get_with_offset("rsi_14", 2) == 50
        assert snapshot.get_with_offset("rsi_14", 3) is None  # Beyond history

    def test_offset_without_history(self):
        """Offset > 0 without history returns None."""
        snapshot = SyntheticSnapshot.with_features({
            "ema_9": 52.0,  # No history
        })
        assert snapshot.get_with_offset("ema_9", 0) == 52.0
        assert snapshot.get_with_offset("ema_9", 1) is None


class TestGetFeatureValue:
    """Test get_feature_value interface (matches RuntimeSnapshotView)."""

    def test_simple_feature(self):
        """Get simple feature without field."""
        snapshot = SyntheticSnapshot.with_features({
            "ema_9": 52.0,
        })
        assert snapshot.get_feature_value("ema_9") == 52.0

    def test_feature_with_field(self):
        """Get feature with field name."""
        snapshot = SyntheticSnapshot.with_features({
            "swing.high_level": 100.0,
        })
        assert snapshot.get_feature_value("swing", field="high_level") == 100.0

    def test_feature_with_offset(self):
        """Get feature with offset."""
        snapshot = SyntheticSnapshot.with_history({
            "ema_9": [48.0, 49.0, 51.0],
        })
        assert snapshot.get_feature_value("ema_9", offset=0) == 51.0
        assert snapshot.get_feature_value("ema_9", offset=1) == 49.0
        assert snapshot.get_feature_value("ema_9", offset=2) == 48.0

    def test_missing_feature(self):
        """Missing feature returns None."""
        snapshot = SyntheticSnapshot()
        assert snapshot.get_feature_value("nonexistent") is None


class TestMutation:
    """Test snapshot mutation methods."""

    def test_add_feature(self):
        """Add feature after creation."""
        snapshot = SyntheticSnapshot()
        snapshot.add_feature("ema_9", 52.0)
        assert snapshot.get("ema_9") == 52.0

    def test_add_feature_chaining(self):
        """Add features with chaining."""
        snapshot = SyntheticSnapshot()
        snapshot.add_feature("ema_9", 52.0).add_feature("ema_21", 50.0)
        assert snapshot.get("ema_9") == 52.0
        assert snapshot.get("ema_21") == 50.0

    def test_add_history(self):
        """Add history after creation."""
        snapshot = SyntheticSnapshot()
        snapshot.add_history("rsi_14", [30, 40, 50])
        assert snapshot.get("rsi_14") == 50
        assert snapshot.get_with_offset("rsi_14", 1) == 40

    def test_has_feature(self):
        """Check feature existence."""
        snapshot = SyntheticSnapshot.with_features({"ema_9": 52.0})
        assert snapshot.has_feature("ema_9")
        assert not snapshot.has_feature("ema_21")


class TestCrossoverScenarios:
    """Test scenarios for crossover operator validation."""

    def test_cross_above_setup(self):
        """Verify setup for cross_above test."""
        snapshot = SyntheticSnapshot.with_history({
            "ema_9": [49.0, 51.0],   # prev=49, curr=51
            "ema_21": [50.0, 50.0],  # constant
        })
        # Current values
        assert snapshot.get("ema_9") == 51.0
        assert snapshot.get("ema_21") == 50.0
        # Previous values
        assert snapshot.get_with_offset("ema_9", 1) == 49.0
        assert snapshot.get_with_offset("ema_21", 1) == 50.0

    def test_cross_below_setup(self):
        """Verify setup for cross_below test."""
        snapshot = SyntheticSnapshot.with_history({
            "ema_9": [51.0, 49.0],   # prev=51, curr=49
            "ema_21": [50.0, 50.0],
        })
        assert snapshot.get("ema_9") == 49.0
        assert snapshot.get_with_offset("ema_9", 1) == 51.0


class TestWindowScenarios:
    """Test scenarios for window operator validation."""

    def test_holds_for_setup(self):
        """Verify setup for holds_for test."""
        snapshot = SyntheticSnapshot.with_history({
            "rsi_14": [55, 52, 51, 53, 54],  # 5 bars all > 50
        })
        # All 5 bars should be > 50
        for offset in range(5):
            value = snapshot.get_with_offset("rsi_14", offset)
            assert value > 50, f"Bar at offset {offset} should be > 50"

    def test_holds_for_broken_setup(self):
        """Verify setup for broken holds_for test."""
        snapshot = SyntheticSnapshot.with_history({
            "rsi_14": [55, 52, 48, 53, 54],  # bar at offset 2 < 50
        })
        assert snapshot.get_with_offset("rsi_14", 2) == 48  # < 50

    def test_occurred_within_setup(self):
        """Verify setup for occurred_within test."""
        snapshot = SyntheticSnapshot.with_history({
            "rsi_14": [40, 42, 65, 45, 43],  # One bar > 60
        })
        # Only bar at offset 2 should be > 60
        assert snapshot.get_with_offset("rsi_14", 2) == 65
        assert snapshot.get_with_offset("rsi_14", 0) == 43
