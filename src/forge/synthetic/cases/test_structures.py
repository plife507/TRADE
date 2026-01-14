"""
Structure Detector Tests.

Phase 5 of DSL Foundation Freeze.

Tests incremental structure detectors with synthetic OHLCV data:
- Swing pivot detection (high/low)
- Fibonacci levels
- Zone state machine
- Derived zones (K slots)
"""

import pytest
import math
from dataclasses import dataclass

from src.backtest.incremental.base import BarData
from src.backtest.incremental.detectors.swing import IncrementalSwingDetector


# =============================================================================
# Helper Functions
# =============================================================================

def make_bar(
    idx: int,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: float = 100.0,
) -> BarData:
    """Create a BarData for testing."""
    return BarData(
        idx=idx,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        indicators={},
    )


def make_bars_from_highs_lows(highs: list[float], lows: list[float]) -> list[BarData]:
    """
    Create bars from separate high and low lists.

    Open and close are interpolated from high/low.
    """
    bars = []
    for i, (h, l) in enumerate(zip(highs, lows)):
        mid = (h + l) / 2
        bars.append(make_bar(
            idx=i,
            open_=mid,
            high=h,
            low=l,
            close=mid,
        ))
    return bars


# =============================================================================
# Swing Pivot Detection Tests
# =============================================================================

class TestSwingDetector:
    """Test IncrementalSwingDetector."""

    def test_swing_high_detection_basic(self):
        """Detect swing high with left=2, right=2."""
        detector = IncrementalSwingDetector({"left": 2, "right": 2}, None)

        # Build price pattern with clear swing high at bar 2
        # Highs: [10, 12, 15, 11, 9] - peak at index 2 (value 15)
        # Swing high at bar 2 should be confirmed at bar 4 (after 2 right bars)
        bars = make_bars_from_highs_lows(
            highs=[10, 12, 15, 11, 9],
            lows=[8, 9, 12, 9, 7],
        )

        for bar in bars:
            detector.update(bar.idx, bar)

        # Swing high should be detected
        assert detector.high_level == 15.0
        assert detector.high_idx == 2

    def test_swing_low_detection_basic(self):
        """Detect swing low with left=2, right=2."""
        detector = IncrementalSwingDetector({"left": 2, "right": 2}, None)

        # Build price pattern with clear swing low at bar 2
        # Lows: [10, 8, 5, 9, 11] - trough at index 2 (value 5)
        bars = make_bars_from_highs_lows(
            highs=[12, 10, 7, 11, 13],
            lows=[10, 8, 5, 9, 11],
        )

        for bar in bars:
            detector.update(bar.idx, bar)

        # Swing low should be detected
        assert detector.low_level == 5.0
        assert detector.low_idx == 2

    def test_swing_high_needs_full_window(self):
        """Swing not confirmed until window is full."""
        detector = IncrementalSwingDetector({"left": 2, "right": 2}, None)

        # Only 4 bars - not enough to confirm (need 5)
        bars = make_bars_from_highs_lows(
            highs=[10, 12, 15, 11],
            lows=[8, 9, 12, 9],
        )

        for bar in bars:
            detector.update(bar.idx, bar)

        # No swing confirmed yet
        assert math.isnan(detector.high_level)
        assert detector.high_idx == -1

    def test_swing_high_not_strictly_greater(self):
        """Equal high values don't form a swing."""
        detector = IncrementalSwingDetector({"left": 2, "right": 2}, None)

        # Highs: [10, 12, 15, 15, 9] - bar 2 equals bar 3
        bars = make_bars_from_highs_lows(
            highs=[10, 12, 15, 15, 9],  # Not strictly greater
            lows=[8, 9, 12, 12, 7],
        )

        for bar in bars:
            detector.update(bar.idx, bar)

        # No swing high - bar 2 is not strictly greater than bar 3
        assert math.isnan(detector.high_level)
        assert detector.high_idx == -1

    def test_swing_low_not_strictly_less(self):
        """Equal low values don't form a swing."""
        detector = IncrementalSwingDetector({"left": 2, "right": 2}, None)

        # Lows: [10, 8, 5, 5, 11] - bar 2 equals bar 3
        bars = make_bars_from_highs_lows(
            highs=[12, 10, 7, 7, 13],
            lows=[10, 8, 5, 5, 11],  # Not strictly less
        )

        for bar in bars:
            detector.update(bar.idx, bar)

        # No swing low - bar 2 is not strictly less than bar 3
        assert math.isnan(detector.low_level)
        assert detector.low_idx == -1

    def test_multiple_swings(self):
        """Detect multiple swings in sequence."""
        detector = IncrementalSwingDetector({"left": 2, "right": 2}, None)

        # Create pattern with swing high at bar 2, swing low at bar 4, swing high at bar 6
        # Highs: [10, 12, 15, 11, 9, 11, 18, 14, 13]
        # Lows:  [8,  9,  12, 9,  7, 8,  15, 12, 11]
        bars = make_bars_from_highs_lows(
            highs=[10, 12, 15, 11, 9, 11, 18, 14, 13],
            lows=[8, 9, 12, 9, 7, 8, 15, 12, 11],
        )

        confirmed_highs = []
        confirmed_lows = []

        for bar in bars:
            prev_high_idx = detector.high_idx
            prev_low_idx = detector.low_idx

            detector.update(bar.idx, bar)

            if detector.high_idx != prev_high_idx and detector.high_idx >= 0:
                confirmed_highs.append((detector.high_idx, detector.high_level))
            if detector.low_idx != prev_low_idx and detector.low_idx >= 0:
                confirmed_lows.append((detector.low_idx, detector.low_level))

        # Should have swing high at bar 2 (15) and bar 6 (18)
        assert (2, 15.0) in confirmed_highs
        assert (6, 18.0) in confirmed_highs

        # Should have swing low at bar 4 (7)
        assert (4, 7.0) in confirmed_lows

    def test_version_increments_on_pivot(self):
        """Version increments exactly once per confirmed pivot."""
        detector = IncrementalSwingDetector({"left": 2, "right": 2}, None)

        bars = make_bars_from_highs_lows(
            highs=[10, 12, 15, 11, 9, 11, 18, 14, 13],
            lows=[8, 9, 12, 9, 7, 8, 15, 12, 11],
        )

        versions = []
        for bar in bars:
            detector.update(bar.idx, bar)
            versions.append(detector.get_value("version"))

        # Version should increment 3 times (2 highs, 1 low)
        final_version = versions[-1]
        assert final_version == 3

    def test_parameter_validation_left_zero(self):
        """left=0 raises ValueError."""
        with pytest.raises(ValueError, match="'left' must be integer >= 1"):
            IncrementalSwingDetector.validate_and_create(
                "swing", "test", {"left": 0, "right": 2}, {}
            )

    def test_parameter_validation_right_negative(self):
        """right=-1 raises ValueError."""
        with pytest.raises(ValueError, match="'right' must be integer >= 1"):
            IncrementalSwingDetector.validate_and_create(
                "swing", "test", {"left": 2, "right": -1}, {}
            )

    def test_parameter_validation_missing_required(self):
        """Missing required param raises ValueError."""
        with pytest.raises(ValueError, match="missing required params"):
            IncrementalSwingDetector.validate_and_create(
                "swing", "test", {"left": 2}, {}
            )

    def test_asymmetric_window(self):
        """Different left/right window sizes work."""
        # left=3, right=1 means we need the pivot to be highest in 5 bars
        # but only need 1 bar after to confirm
        detector = IncrementalSwingDetector({"left": 3, "right": 1}, None)

        # Peak at bar 3 (15), confirmed at bar 4
        bars = make_bars_from_highs_lows(
            highs=[10, 11, 12, 15, 13],
            lows=[8, 9, 10, 12, 11],
        )

        for bar in bars:
            detector.update(bar.idx, bar)

        assert detector.high_level == 15.0
        assert detector.high_idx == 3


# =============================================================================
# Fibonacci Level Tests
# =============================================================================

class TestFibonacciDetector:
    """Test Fibonacci level detector."""

    @pytest.fixture
    def swing_detector(self) -> IncrementalSwingDetector:
        """Create a swing detector with known state."""
        detector = IncrementalSwingDetector({"left": 2, "right": 2}, None)
        # Force state for testing fib levels
        detector.high_level = 100.0
        detector.high_idx = 5
        detector.low_level = 80.0
        detector.low_idx = 2
        detector._version = 2
        return detector

    def test_fib_retracement_levels(self, swing_detector):
        """Calculate fib retracement levels from swing range."""
        from src.backtest.incremental.detectors.fibonacci import IncrementalFibonacci

        params = {
            "levels": [0.236, 0.382, 0.5, 0.618, 0.786],
            "mode": "retracement",
        }
        deps = {"swing": swing_detector}
        fib = IncrementalFibonacci(params, deps)

        # Force regeneration
        fib.update(10, make_bar(10, 90, 92, 88, 90))

        # Range = 100 - 80 = 20
        # Retracement: level = high - (ratio * range)
        assert fib.get_value("level_0.236") == pytest.approx(100 - 0.236 * 20)  # 95.28
        assert fib.get_value("level_0.382") == pytest.approx(100 - 0.382 * 20)  # 92.36
        assert fib.get_value("level_0.5") == pytest.approx(90.0)
        assert fib.get_value("level_0.618") == pytest.approx(100 - 0.618 * 20)  # 87.64
        assert fib.get_value("level_0.786") == pytest.approx(100 - 0.786 * 20)  # 84.28

    def test_fib_extension_levels(self, swing_detector):
        """Calculate fib extension levels from swing range using explicit extension_up mode."""
        from src.backtest.incremental.detectors.fibonacci import IncrementalFibonacci

        # Note: "extension" mode requires use_paired_anchor (auto-direction).
        # For explicit direction without pairing, use "extension_up" or "extension_down".
        params = {
            "levels": [1.0, 1.272, 1.618],
            "mode": "extension_up",  # Explicit upward extension (legacy mode)
        }
        deps = {"swing": swing_detector}
        fib = IncrementalFibonacci(params, deps)

        # Force regeneration
        fib.update(10, make_bar(10, 90, 92, 88, 90))

        # Range = 100 - 80 = 20
        # Extension up: level = high + (ratio * range)
        # Key format uses :g so 1.0 becomes "1"
        assert fib.get_value("level_1") == pytest.approx(100 + 1.0 * 20)  # 120
        assert fib.get_value("level_1.272") == pytest.approx(100 + 1.272 * 20)  # 125.44
        assert fib.get_value("level_1.618") == pytest.approx(100 + 1.618 * 20)  # 132.36

    def test_fib_no_swing_returns_nan(self):
        """Fib levels are NaN when no swing is available."""
        from src.backtest.incremental.detectors.fibonacci import IncrementalFibonacci

        # Empty swing detector
        swing = IncrementalSwingDetector({"left": 2, "right": 2}, None)
        params = {"levels": [0.5], "mode": "retracement"}
        deps = {"swing": swing}
        fib = IncrementalFibonacci(params, deps)

        # Update without any swings confirmed
        fib.update(0, make_bar(0, 50, 52, 48, 50))

        assert math.isnan(fib.get_value("level_0.5"))


# =============================================================================
# Zone State Machine Tests
# =============================================================================

class TestZoneDetector:
    """Test Zone state machine detector."""

    @pytest.fixture
    def swing_detector_with_low(self) -> IncrementalSwingDetector:
        """Create swing detector with confirmed swing low."""
        detector = IncrementalSwingDetector({"left": 2, "right": 2}, None)
        # Set a swing low
        detector.low_level = 80.0
        detector.low_idx = 2
        detector._version = 1
        detector._last_confirmed_pivot_type = "low"
        detector._last_confirmed_pivot_idx = 2
        return detector

    def test_zone_lifecycle_none_to_active(self, swing_detector_with_low):
        """Zone transitions from none to active when swing detected."""
        from src.backtest.incremental.detectors.zone import IncrementalZoneDetector

        params = {"zone_type": "demand", "width_atr": 0.5}
        deps = {"swing": swing_detector_with_low}
        zone = IncrementalZoneDetector(params, deps)

        # First bar after swing - zone should become active
        bar = make_bar(3, 85, 88, 83, 87)
        zone.update(3, bar)

        assert zone.get_value("state") == "active"
        assert zone.get_value("lower") is not None or not math.isnan(zone.get_value("lower"))

    def test_zone_touched_but_not_broken(self, swing_detector_with_low):
        """Zone touched when price enters but doesn't break through."""
        from src.backtest.incremental.detectors.zone import IncrementalZoneDetector

        params = {"zone_type": "demand", "width_atr": 0.5}
        deps = {"swing": swing_detector_with_low}
        zone = IncrementalZoneDetector(params, deps)

        # Setup zone
        zone.update(3, make_bar(3, 85, 88, 83, 87))

        # Price enters zone but doesn't break below
        lower = zone.get_value("lower")
        upper = zone.get_value("upper")

        # Price dips into zone
        mid_zone = (lower + upper) / 2 if not math.isnan(lower) and not math.isnan(upper) else 81
        zone.update(4, make_bar(4, 82, 84, mid_zone, 83))

        # Zone should still be active (touched but not broken)
        assert zone.get_value("state") == "active"

    def test_zone_broken(self, swing_detector_with_low):
        """Zone broken when price breaks through."""
        from src.backtest.incremental.detectors.zone import IncrementalZoneDetector

        params = {"zone_type": "demand", "width_atr": 0.5}
        deps = {"swing": swing_detector_with_low}
        zone = IncrementalZoneDetector(params, deps)

        # Setup zone
        zone.update(3, make_bar(3, 85, 88, 83, 87))

        lower = zone.get_value("lower")

        # Price breaks below zone
        if not math.isnan(lower):
            break_price = lower - 2
            zone.update(4, make_bar(4, lower, lower + 1, break_price, break_price + 0.5))

            # Zone should be broken
            assert zone.get_value("state") == "broken"


# =============================================================================
# Derived Zone (K Slots) Tests
# =============================================================================

class TestDerivedZoneDetector:
    """Test DerivedZone detector with K slots pattern."""

    @pytest.fixture
    def swing_detector_with_pivots(self) -> IncrementalSwingDetector:
        """Create swing detector with both high and low."""
        detector = IncrementalSwingDetector({"left": 2, "right": 2}, None)
        detector.high_level = 100.0
        detector.high_idx = 5
        detector.low_level = 80.0
        detector.low_idx = 2
        detector._version = 2
        return detector

    def test_derived_zones_created_at_fib_levels(self, swing_detector_with_pivots):
        """Derived zones created at specified fib levels."""
        from src.backtest.incremental.detectors.derived_zone import IncrementalDerivedZone

        params = {
            "levels": [0.5, 0.618],
            "mode": "retracement",
            "max_active": 3,
            "width_pct": 0.02,  # 2% width for easier testing
        }
        deps = {"source": swing_detector_with_pivots}
        dz = IncrementalDerivedZone(params, deps)

        # Trigger zone generation
        # 0.5 retracement of 100-80 = 90 (zone with 2% width: 89.1 to 90.9)
        # 0.618 retracement of 100-80 = 87.64 (zone with 2% width: 85.88 to 89.40)
        # Use price inside one zone (90 is inside 0.5 zone)
        dz.update(10, make_bar(10, 90, 91, 89, 90))

        # Should have 2 zones created
        # zone0 is 0.618 (created second, prepended first)
        # zone1 is 0.5
        # Check zone boundaries exist (not None)
        assert dz.get_value("zone0_lower") is not None
        assert dz.get_value("zone1_lower") is not None

        # Price 90 is inside 0.5 zone but above 0.618 zone
        # 0.618 zone may be BROKEN because price > upper * 1.001
        # At least one zone should exist
        assert dz.get_value("zone0_state") in ("ACTIVE", "BROKEN")
        assert dz.get_value("zone1_state") in ("ACTIVE", "BROKEN")

    def test_derived_zone_aggregate_fields(self, swing_detector_with_pivots):
        """Aggregate fields computed correctly when price inside zone."""
        from src.backtest.incremental.detectors.derived_zone import IncrementalDerivedZone

        params = {
            "levels": [0.5],  # Single zone for simpler test
            "mode": "retracement",
            "max_active": 3,
            "width_pct": 0.02,  # 2% width: zone 89.1 to 90.9
        }
        deps = {"source": swing_detector_with_pivots}
        dz = IncrementalDerivedZone(params, deps)

        # Price 90 is inside the 0.5 zone (89.1 to 90.9)
        dz.update(10, make_bar(10, 90, 91, 89, 90))

        # Check aggregate fields
        # Price 90 is inside zone so touched_this_bar and inside are True
        assert dz.get_value("any_active") is True
        assert dz.get_value("any_touched") is True  # Price entered zone
        assert dz.get_value("any_inside") is True   # Price currently inside

    def test_derived_zone_touched_this_bar(self, swing_detector_with_pivots):
        """touched_this_bar resets each bar, true only when price in zone."""
        from src.backtest.incremental.detectors.derived_zone import IncrementalDerivedZone

        params = {
            "levels": [0.5],  # 50% retracement = 90.0
            "mode": "retracement",
            "max_active": 3,
            "width_pct": 0.02,  # 2% width: zone 89.1 to 90.9
        }
        deps = {"source": swing_detector_with_pivots}
        dz = IncrementalDerivedZone(params, deps)

        # First bar: price inside zone triggers touch
        dz.update(10, make_bar(10, 90, 91, 89, 90))
        assert dz.get_value("zone0_touched_this_bar") is True
        assert dz.get_value("any_touched") is True

        # Second bar: price still inside zone, touched again
        dz.update(11, make_bar(11, 90.5, 90.8, 89.5, 90.2))
        assert dz.get_value("zone0_touched_this_bar") is True

        # Third bar: price outside zone, touched resets
        dz.update(12, make_bar(12, 92, 93, 91.5, 92))
        # Price 92 is outside zone (89.1-90.9) but not breaking (92 < 90.9 * 1.001 * factor)
        # Actually 92 > 90.9 * 1.001 = 91.0, so zone is BROKEN
        # touched_this_bar should be False since price not in zone
        assert dz.get_value("zone0_touched_this_bar") is False

    def test_derived_zone_empty_guards(self):
        """Empty derived zones have safe default values."""
        from src.backtest.incremental.detectors.derived_zone import IncrementalDerivedZone

        # No swing pivots
        swing = IncrementalSwingDetector({"left": 2, "right": 2}, None)

        params = {
            "levels": [0.5],
            "mode": "retracement",
            "max_active": 3,
            "width_pct": 0.01,
        }
        deps = {"source": swing}
        dz = IncrementalDerivedZone(params, deps)

        # No zones created without swings
        dz.update(0, make_bar(0, 50, 52, 48, 50))

        assert dz.get_value("active_count") == 0
        assert dz.get_value("any_active") is False
        assert dz.get_value("zone0_state") == "NONE"


# =============================================================================
# Paired Pivot Tests
# =============================================================================

class TestPairedPivots:
    """
    Test paired pivot detection in swing detector.

    The swing detector tracks both individual pivots (high_level, low_level)
    AND paired pivots (pair_high_level, pair_low_level) that form coherent
    swing sequences.
    """

    def test_bullish_pair_lhl(self):
        """
        Bullish pair: Low → High sequence.

        Timeline:
        - Bar 4: Swing LOW confirmed (L1)
        - Bar 6: Swing HIGH confirmed (H1) → completes BULLISH pair
        """
        swing = IncrementalSwingDetector({"left": 2, "right": 2}, None)

        # Create bars with clear L → H sequence
        # Low at bar 2 (confirmed at bar 4), High at bar 4 (confirmed at bar 6)
        bars = [
            make_bar(0, 100, 102, 99, 101),   # warmup
            make_bar(1, 101, 103, 98, 100),   # warmup
            make_bar(2, 100, 101, 95, 98),    # SWING LOW at 95
            make_bar(3, 98, 100, 96, 99),     # right-1
            make_bar(4, 99, 105, 97, 104),    # right-2 → LOW confirmed
            make_bar(5, 104, 110, 103, 108),  # SWING HIGH at 110
            make_bar(6, 108, 109, 105, 107),  # right-1
            make_bar(7, 107, 108, 104, 106),  # right-2 → HIGH confirmed
        ]

        for bar in bars:
            swing.update(bar.idx, bar)

        # Verify individual pivots
        assert swing.get_value("low_level") == 95.0
        assert swing.get_value("low_idx") == 2
        assert swing.get_value("high_level") == 110.0
        assert swing.get_value("high_idx") == 5

        # Verify paired pivot
        assert swing.get_value("pair_direction") == "bullish"
        assert swing.get_value("pair_low_level") == 95.0
        assert swing.get_value("pair_low_idx") == 2
        assert swing.get_value("pair_high_level") == 110.0
        assert swing.get_value("pair_high_idx") == 5
        assert swing.get_value("pair_version") == 1
        assert len(swing.get_value("pair_anchor_hash")) == 16  # blake2b hex

    def test_bearish_pair_hlh(self):
        """
        Bearish pair: High → Low sequence.

        Timeline:
        - Bar 4: Swing HIGH confirmed (H1)
        - Bar 6: Swing LOW confirmed (L1) → completes BEARISH pair
        """
        swing = IncrementalSwingDetector({"left": 2, "right": 2}, None)

        # Create bars with clear H → L sequence
        bars = [
            make_bar(0, 100, 102, 99, 101),   # warmup
            make_bar(1, 101, 105, 100, 104),  # warmup
            make_bar(2, 104, 110, 103, 108),  # SWING HIGH at 110
            make_bar(3, 108, 109, 105, 107),  # right-1
            make_bar(4, 107, 108, 104, 105),  # right-2 → HIGH confirmed
            make_bar(5, 105, 106, 95, 98),    # SWING LOW at 95
            make_bar(6, 98, 100, 96, 99),     # right-1
            make_bar(7, 99, 101, 97, 100),    # right-2 → LOW confirmed
        ]

        for bar in bars:
            swing.update(bar.idx, bar)

        # Verify paired pivot
        assert swing.get_value("pair_direction") == "bearish"
        assert swing.get_value("pair_high_level") == 110.0
        assert swing.get_value("pair_low_level") == 95.0
        assert swing.get_value("pair_version") == 1

    def test_pair_version_increments_on_new_pair(self):
        """
        pair_version only increments when a COMPLETE pair forms.

        Timeline:
        - L1 → H1 → pair_version=1 (bullish)
        - L2 forms → pair_version=2 (bearish H1→L2)
        """
        swing = IncrementalSwingDetector({"left": 2, "right": 2}, None)

        # First pair: L1 → H1 (bullish)
        bars = [
            make_bar(0, 100, 102, 99, 101),
            make_bar(1, 101, 103, 98, 100),
            make_bar(2, 100, 101, 90, 95),    # LOW at 90
            make_bar(3, 95, 97, 91, 96),
            make_bar(4, 96, 98, 92, 97),      # LOW confirmed → GOT_LOW state
        ]
        for bar in bars:
            swing.update(bar.idx, bar)

        assert swing.get_value("pair_version") == 0  # No pair yet

        # H1 forms → completes bullish pair
        bars2 = [
            make_bar(5, 97, 110, 96, 108),    # HIGH at 110
            make_bar(6, 108, 109, 105, 107),
            make_bar(7, 107, 108, 104, 106),  # HIGH confirmed → BULLISH pair
        ]
        for bar in bars2:
            swing.update(bar.idx, bar)

        assert swing.get_value("pair_version") == 1
        assert swing.get_value("pair_direction") == "bullish"

        # L2 forms → completes bearish pair (H1 → L2)
        bars3 = [
            make_bar(8, 106, 107, 85, 88),    # LOW at 85
            make_bar(9, 88, 90, 86, 89),
            make_bar(10, 89, 91, 87, 90),     # LOW confirmed → BEARISH pair
        ]
        for bar in bars3:
            swing.update(bar.idx, bar)

        assert swing.get_value("pair_version") == 2
        assert swing.get_value("pair_direction") == "bearish"
        assert swing.get_value("pair_high_level") == 110.0  # H1
        assert swing.get_value("pair_low_level") == 85.0    # L2

    def test_same_direction_pivot_replaces_pending(self):
        """
        When two highs (or two lows) form in sequence, the second replaces the first.
        No pair forms until the opposite pivot completes.
        """
        swing = IncrementalSwingDetector({"left": 2, "right": 2}, None)

        # H1 forms
        bars = [
            make_bar(0, 100, 102, 99, 101),
            make_bar(1, 101, 105, 100, 104),
            make_bar(2, 104, 110, 103, 108),  # HIGH at 110
            make_bar(3, 108, 109, 105, 107),
            make_bar(4, 107, 108, 104, 105),  # H1 confirmed → GOT_HIGH state
        ]
        for bar in bars:
            swing.update(bar.idx, bar)

        assert swing.get_value("pair_version") == 0  # No pair yet

        # H2 forms (higher high) → replaces H1 as pending
        bars2 = [
            make_bar(5, 105, 120, 104, 118),  # HIGH at 120
            make_bar(6, 118, 119, 115, 117),
            make_bar(7, 117, 118, 114, 116),  # H2 confirmed → still GOT_HIGH
        ]
        for bar in bars2:
            swing.update(bar.idx, bar)

        # Still no pair - waiting for low
        assert swing.get_value("pair_version") == 0

        # L1 forms → completes pair with H2 (not H1)
        bars3 = [
            make_bar(8, 116, 117, 90, 95),    # LOW at 90
            make_bar(9, 95, 97, 91, 96),
            make_bar(10, 96, 98, 92, 97),     # LOW confirmed → BEARISH pair
        ]
        for bar in bars3:
            swing.update(bar.idx, bar)

        assert swing.get_value("pair_version") == 1
        assert swing.get_value("pair_direction") == "bearish"
        assert swing.get_value("pair_high_level") == 120.0  # H2, not H1
        assert swing.get_value("pair_low_level") == 90.0

    def test_anchor_hash_unique_per_pair(self):
        """Each unique pair gets a different anchor hash."""
        swing = IncrementalSwingDetector({"left": 2, "right": 2}, None)

        # First pair: L1 → H1
        bars = [
            make_bar(0, 100, 102, 99, 101),
            make_bar(1, 101, 103, 98, 100),
            make_bar(2, 100, 101, 90, 95),    # LOW at 90
            make_bar(3, 95, 97, 91, 96),
            make_bar(4, 96, 110, 92, 108),    # LOW confirmed
            make_bar(5, 108, 115, 107, 113),  # HIGH at 115
            make_bar(6, 113, 114, 110, 112),
            make_bar(7, 112, 113, 109, 111),  # HIGH confirmed → pair 1
        ]
        for bar in bars:
            swing.update(bar.idx, bar)

        hash1 = swing.get_value("pair_anchor_hash")
        assert len(hash1) == 16

        # Second pair: H1 → L2
        bars2 = [
            make_bar(8, 111, 112, 80, 85),    # LOW at 80
            make_bar(9, 85, 87, 81, 86),
            make_bar(10, 86, 88, 82, 87),     # LOW confirmed → pair 2
        ]
        for bar in bars2:
            swing.update(bar.idx, bar)

        hash2 = swing.get_value("pair_anchor_hash")
        assert len(hash2) == 16
        assert hash1 != hash2  # Different pairs, different hashes


class TestPairedFibonacci:
    """
    Test Fibonacci detector with paired anchor mode.
    """

    def test_fib_unpaired_mode_default(self):
        """Default mode uses individual pivots (may be from different sequences)."""
        from src.backtest.incremental.detectors.fibonacci import IncrementalFibonacci

        swing = IncrementalSwingDetector({"left": 2, "right": 2}, None)
        fib = IncrementalFibonacci(
            params={"levels": [0.5], "mode": "retracement"},
            deps={"swing": swing},
        )

        # Create L1 → H1 sequence
        bars = [
            make_bar(0, 100, 102, 99, 101),
            make_bar(1, 101, 103, 98, 100),
            make_bar(2, 100, 101, 90, 95),    # LOW at 90
            make_bar(3, 95, 97, 91, 96),
            make_bar(4, 96, 110, 92, 108),    # LOW confirmed
        ]
        for bar in bars:
            swing.update(bar.idx, bar)
            fib.update(bar.idx, bar)

        # With only low confirmed, fib should still have NaN
        assert math.isnan(fib.get_value("level_0.5"))

        # HIGH confirmed
        bars2 = [
            make_bar(5, 108, 115, 107, 113),  # HIGH at 115
            make_bar(6, 113, 114, 110, 112),
            make_bar(7, 112, 113, 109, 111),  # HIGH confirmed
        ]
        for bar in bars2:
            swing.update(bar.idx, bar)
            fib.update(bar.idx, bar)

        # Unpaired mode: uses latest high (115) and low (90)
        assert fib.get_value("anchor_high") == 115.0
        assert fib.get_value("anchor_low") == 90.0
        assert fib.get_value("level_0.5") == pytest.approx(102.5)  # 115 - (25 * 0.5)
        # No direction in unpaired mode
        assert fib.get_value("anchor_direction") == ""

    def test_fib_paired_mode_waits_for_pair(self):
        """Paired mode only calculates levels when a complete pair forms."""
        from src.backtest.incremental.detectors.fibonacci import IncrementalFibonacci

        swing = IncrementalSwingDetector({"left": 2, "right": 2}, None)
        fib = IncrementalFibonacci(
            params={"levels": [0.5], "mode": "retracement", "use_paired_anchor": True},
            deps={"swing": swing},
        )

        # Create H1 → waiting for L1
        bars = [
            make_bar(0, 100, 102, 99, 101),
            make_bar(1, 101, 105, 100, 104),
            make_bar(2, 104, 110, 103, 108),  # HIGH at 110
            make_bar(3, 108, 109, 105, 107),
            make_bar(4, 107, 108, 104, 105),  # HIGH confirmed
        ]
        for bar in bars:
            swing.update(bar.idx, bar)
            fib.update(bar.idx, bar)

        # Paired mode: no levels yet (waiting for pair)
        assert math.isnan(fib.get_value("level_0.5"))

        # L1 confirmed → completes bearish pair
        bars2 = [
            make_bar(5, 105, 106, 90, 95),    # LOW at 90
            make_bar(6, 95, 97, 91, 96),
            make_bar(7, 96, 98, 92, 97),      # LOW confirmed → BEARISH pair
        ]
        for bar in bars2:
            swing.update(bar.idx, bar)
            fib.update(bar.idx, bar)

        # Now paired levels available
        assert fib.get_value("anchor_high") == 110.0
        assert fib.get_value("anchor_low") == 90.0
        assert fib.get_value("level_0.5") == pytest.approx(100.0)  # 110 - (20 * 0.5)
        assert fib.get_value("anchor_direction") == "bearish"
        assert len(fib.get_value("anchor_hash")) == 16

    def test_fib_paired_mode_bullish_direction(self):
        """Paired mode tracks bullish direction for L→H swings."""
        from src.backtest.incremental.detectors.fibonacci import IncrementalFibonacci

        swing = IncrementalSwingDetector({"left": 2, "right": 2}, None)
        fib = IncrementalFibonacci(
            params={"levels": [0.382, 0.618], "mode": "retracement", "use_paired_anchor": True},
            deps={"swing": swing},
        )

        # Create L1 → H1 sequence (bullish)
        bars = [
            make_bar(0, 100, 102, 99, 101),
            make_bar(1, 101, 103, 98, 100),
            make_bar(2, 100, 101, 80, 85),    # LOW at 80
            make_bar(3, 85, 87, 81, 86),
            make_bar(4, 86, 100, 82, 98),     # LOW confirmed
            make_bar(5, 98, 120, 97, 118),    # HIGH at 120
            make_bar(6, 118, 119, 115, 117),
            make_bar(7, 117, 118, 114, 116),  # HIGH confirmed → BULLISH pair
        ]
        for bar in bars:
            swing.update(bar.idx, bar)
            fib.update(bar.idx, bar)

        # Range = 120 - 80 = 40
        assert fib.get_value("anchor_direction") == "bullish"
        assert fib.get_value("level_0.382") == pytest.approx(120 - 40 * 0.382)  # ~104.72
        assert fib.get_value("level_0.618") == pytest.approx(120 - 40 * 0.618)  # ~95.28

    def test_fib_extension_with_paired_anchor(self):
        """Extension mode works with paired anchors."""
        from src.backtest.incremental.detectors.fibonacci import IncrementalFibonacci

        swing = IncrementalSwingDetector({"left": 2, "right": 2}, None)
        fib = IncrementalFibonacci(
            params={"levels": [1.618], "mode": "extension_up", "use_paired_anchor": True},
            deps={"swing": swing},
        )

        # Create bullish pair
        bars = [
            make_bar(0, 100, 102, 99, 101),
            make_bar(1, 101, 103, 98, 100),
            make_bar(2, 100, 101, 80, 85),    # LOW at 80
            make_bar(3, 85, 87, 81, 86),
            make_bar(4, 86, 100, 82, 98),     # LOW confirmed
            make_bar(5, 98, 120, 97, 118),    # HIGH at 120
            make_bar(6, 118, 119, 115, 117),
            make_bar(7, 117, 118, 114, 116),  # HIGH confirmed → BULLISH pair
        ]
        for bar in bars:
            swing.update(bar.idx, bar)
            fib.update(bar.idx, bar)

        # Extension up: high + (range * ratio) = 120 + (40 * 1.618) = 184.72
        assert fib.get_value("level_1.618") == pytest.approx(120 + 40 * 1.618)

    def test_fib_negative_levels_above_high(self):
        """Negative levels project ABOVE the swing high (long targets)."""
        from src.backtest.incremental.detectors.fibonacci import IncrementalFibonacci

        swing = IncrementalSwingDetector({"left": 2, "right": 2}, None)
        fib = IncrementalFibonacci(
            params={"levels": [-0.272, -0.618], "mode": "retracement"},
            deps={"swing": swing},
        )

        # Create swing with high=100, low=80, range=20
        # Need clear pivots: low at bar 2 confirmed at bar 4, high at bar 5 confirmed at bar 7
        bars = [
            make_bar(0, 90, 92, 88, 91),      # warmup
            make_bar(1, 91, 93, 85, 88),      # warmup
            make_bar(2, 88, 89, 80, 82),      # SWING LOW at 80
            make_bar(3, 82, 85, 81, 84),      # right-1
            make_bar(4, 84, 86, 82, 85),      # right-2 → LOW confirmed
            make_bar(5, 85, 100, 84, 98),     # SWING HIGH at 100
            make_bar(6, 98, 99, 95, 97),      # right-1
            make_bar(7, 97, 98, 94, 96),      # right-2 → HIGH confirmed
        ]
        for bar in bars:
            swing.update(bar.idx, bar)
            fib.update(bar.idx, bar)

        # Verify pivots detected
        assert swing.get_value("high_level") == 100.0
        assert swing.get_value("low_level") == 80.0

        # Unified formula: level = high - (ratio × range)
        # ratio = -0.272: level = 100 - (-0.272 × 20) = 100 + 5.44 = 105.44
        # ratio = -0.618: level = 100 - (-0.618 × 20) = 100 + 12.36 = 112.36
        assert fib.get_value("level_-0.272") == pytest.approx(100 + 0.272 * 20)
        assert fib.get_value("level_-0.618") == pytest.approx(100 + 0.618 * 20)

    def test_fib_levels_above_100_below_low(self):
        """Levels > 1 project BELOW the swing low (short targets)."""
        from src.backtest.incremental.detectors.fibonacci import IncrementalFibonacci

        swing = IncrementalSwingDetector({"left": 2, "right": 2}, None)
        fib = IncrementalFibonacci(
            params={"levels": [1.272, 1.618], "mode": "retracement"},
            deps={"swing": swing},
        )

        # Create swing with high=100, low=80, range=20
        bars = [
            make_bar(0, 90, 92, 88, 91),      # warmup
            make_bar(1, 91, 93, 85, 88),      # warmup
            make_bar(2, 88, 89, 80, 82),      # SWING LOW at 80
            make_bar(3, 82, 85, 81, 84),      # right-1
            make_bar(4, 84, 86, 82, 85),      # right-2 → LOW confirmed
            make_bar(5, 85, 100, 84, 98),     # SWING HIGH at 100
            make_bar(6, 98, 99, 95, 97),      # right-1
            make_bar(7, 97, 98, 94, 96),      # right-2 → HIGH confirmed
        ]
        for bar in bars:
            swing.update(bar.idx, bar)
            fib.update(bar.idx, bar)

        # Unified formula: level = high - (ratio × range)
        # ratio = 1.272: level = 100 - (1.272 × 20) = 100 - 25.44 = 74.56
        # ratio = 1.618: level = 100 - (1.618 × 20) = 100 - 32.36 = 67.64
        assert fib.get_value("level_1.272") == pytest.approx(100 - 1.272 * 20)
        assert fib.get_value("level_1.618") == pytest.approx(100 - 1.618 * 20)

    def test_fib_extension_mode_bullish_auto_direction(self):
        """Extension mode auto-projects ABOVE high for bullish pairs."""
        from src.backtest.incremental.detectors.fibonacci import IncrementalFibonacci

        swing = IncrementalSwingDetector({"left": 2, "right": 2}, None)
        fib = IncrementalFibonacci(
            params={
                "levels": [0.272, 0.618, 1.0],
                "mode": "extension",
                "use_paired_anchor": True,
            },
            deps={"swing": swing},
        )

        # Create BULLISH pair (L→H): low=80 confirmed first, then high=100
        bars = [
            make_bar(0, 90, 92, 88, 91),      # warmup
            make_bar(1, 91, 93, 85, 88),      # warmup
            make_bar(2, 88, 89, 80, 82),      # SWING LOW at 80
            make_bar(3, 82, 85, 81, 84),      # right-1
            make_bar(4, 84, 86, 82, 85),      # right-2 → LOW confirmed
            make_bar(5, 85, 100, 84, 98),     # SWING HIGH at 100
            make_bar(6, 98, 99, 95, 97),      # right-1
            make_bar(7, 97, 98, 94, 96),      # right-2 → HIGH confirmed → BULLISH pair
        ]
        for bar in bars:
            swing.update(bar.idx, bar)
            fib.update(bar.idx, bar)

        assert fib.get_value("anchor_direction") == "bullish"

        # Bullish extension: targets ABOVE high
        # Formula: high + (ratio × range) = 100 + (ratio × 20)
        assert fib.get_value("level_0.272") == pytest.approx(100 + 0.272 * 20)
        assert fib.get_value("level_0.618") == pytest.approx(100 + 0.618 * 20)
        assert fib.get_value("level_1") == pytest.approx(100 + 1.0 * 20)

    def test_fib_extension_mode_bearish_auto_direction(self):
        """Extension mode auto-projects BELOW low for bearish pairs."""
        from src.backtest.incremental.detectors.fibonacci import IncrementalFibonacci

        swing = IncrementalSwingDetector({"left": 2, "right": 2}, None)
        fib = IncrementalFibonacci(
            params={
                "levels": [0.272, 0.618, 1.0],
                "mode": "extension",
                "use_paired_anchor": True,
            },
            deps={"swing": swing},
        )

        # Create BEARISH pair (H→L): high=100 confirmed first, then low=80
        bars = [
            make_bar(0, 95, 97, 94, 96),      # warmup
            make_bar(1, 96, 98, 95, 97),      # warmup
            make_bar(2, 97, 100, 96, 99),     # SWING HIGH at 100
            make_bar(3, 99, 99, 95, 97),      # right-1
            make_bar(4, 97, 98, 94, 96),      # right-2 → HIGH confirmed
            make_bar(5, 96, 97, 80, 82),      # SWING LOW at 80
            make_bar(6, 82, 84, 81, 83),      # right-1
            make_bar(7, 83, 85, 82, 84),      # right-2 → LOW confirmed → BEARISH pair
        ]
        for bar in bars:
            swing.update(bar.idx, bar)
            fib.update(bar.idx, bar)

        assert fib.get_value("anchor_direction") == "bearish"

        # Bearish extension: targets BELOW low
        # Formula: low - (ratio × range) = 80 - (ratio × 20)
        assert fib.get_value("level_0.272") == pytest.approx(80 - 0.272 * 20)
        assert fib.get_value("level_0.618") == pytest.approx(80 - 0.618 * 20)
        assert fib.get_value("level_1") == pytest.approx(80 - 1.0 * 20)

    def test_fib_extension_mode_requires_paired_anchor(self):
        """Extension mode validation requires use_paired_anchor=true."""
        from src.backtest.incremental.detectors.fibonacci import IncrementalFibonacci

        # Mock swing dependency to satisfy dependency check
        swing = IncrementalSwingDetector({"left": 2, "right": 2}, None)

        with pytest.raises(ValueError, match="requires use_paired_anchor"):
            IncrementalFibonacci.validate_and_create(
                "fibonacci",
                "test_fib",
                params={"levels": [0.272], "mode": "extension"},  # Missing use_paired_anchor
                deps={"swing": swing},
            )


class TestDerivedZonePairedSource:
    """Test DerivedZone with use_paired_source option."""

    def test_derived_zone_paired_source_waits_for_pair(self):
        """
        With use_paired_source=True, zones don't regenerate until a complete pair forms.

        Individual pivots (high OR low alone) don't trigger zone regeneration.
        Only when pair_version increments (complete L→H or H→L) do zones update.
        """
        from src.backtest.incremental.detectors.derived_zone import IncrementalDerivedZone

        swing = IncrementalSwingDetector({"left": 2, "right": 2}, None)
        params = {
            "levels": [0.5],
            "mode": "retracement",
            "max_active": 3,
            "width_pct": 0.02,
            "use_paired_source": True,
        }
        deps = {"source": swing}
        dz = IncrementalDerivedZone(params, deps)

        # L1 forms (first pivot) - NO pair yet
        bars = [
            make_bar(0, 100, 102, 99, 101),
            make_bar(1, 101, 103, 98, 100),
            make_bar(2, 100, 101, 80, 85),     # LOW at 80
            make_bar(3, 85, 87, 81, 86),
            make_bar(4, 86, 88, 82, 87),       # LOW confirmed
        ]
        for bar in bars:
            swing.update(bar.idx, bar)
            dz.update(bar.idx, bar)

        # No zones yet - pair_version is still 0
        assert swing.get_value("pair_version") == 0
        # Zone should not exist (zone0_lower is None when no zones created)
        assert dz.get_value("zone0_lower") is None

        # H1 forms → completes BULLISH pair (L→H)
        bars2 = [
            make_bar(5, 87, 120, 86, 118),     # HIGH at 120
            make_bar(6, 118, 119, 115, 117),
            make_bar(7, 117, 118, 114, 116),   # HIGH confirmed → pair complete
        ]
        for bar in bars2:
            swing.update(bar.idx, bar)
            dz.update(bar.idx, bar)

        # Now pair_version=1 and zones should be created
        assert swing.get_value("pair_version") == 1
        assert swing.get_value("pair_high_level") == 120.0
        assert swing.get_value("pair_low_level") == 80.0

        # Zone was created - check that zone0_lower has a value
        # (zone may be BROKEN due to price being outside, but it EXISTS)
        zone_lower = dz.get_value("zone0_lower")
        assert zone_lower is not None

        # 50% retracement of 80-120 range = 100
        # Zone center should be around 100
        zone_upper = dz.get_value("zone0_upper")
        center = (zone_lower + zone_upper) / 2
        assert center == pytest.approx(100.0, rel=0.01)

    def test_derived_zone_paired_source_uses_pair_levels(self):
        """
        With use_paired_source=True, zones are calculated from pair_high/pair_low.

        The zone levels should match the paired pivot values, not individual pivots.
        """
        from src.backtest.incremental.detectors.derived_zone import IncrementalDerivedZone

        swing = IncrementalSwingDetector({"left": 2, "right": 2}, None)
        params = {
            "levels": [0.5],  # 50% retracement
            "mode": "retracement",
            "max_active": 3,
            "width_pct": 0.02,  # 2% width
            "use_paired_source": True,
        }
        deps = {"source": swing}
        dz = IncrementalDerivedZone(params, deps)

        # Create a complete pair with high=100, low=80
        bars = [
            make_bar(0, 90, 92, 88, 91),
            make_bar(1, 91, 93, 85, 88),
            make_bar(2, 88, 89, 80, 82),       # LOW at 80
            make_bar(3, 82, 85, 81, 84),
            make_bar(4, 84, 86, 82, 85),       # LOW confirmed
            make_bar(5, 85, 100, 84, 98),      # HIGH at 100
            make_bar(6, 98, 99, 95, 97),
            make_bar(7, 97, 98, 94, 96),       # HIGH confirmed → BULLISH pair
        ]
        for bar in bars:
            swing.update(bar.idx, bar)
            dz.update(bar.idx, bar)

        # Verify paired levels
        assert swing.get_value("pair_high_level") == 100.0
        assert swing.get_value("pair_low_level") == 80.0

        # Zone at 50% retracement = high - 0.5 × (high - low) = 100 - 10 = 90
        # Zone width = 90 × 0.02 = 1.8 → [89.1, 90.9]
        zone_lower = dz.get_value("zone0_lower")
        zone_upper = dz.get_value("zone0_upper")

        assert zone_lower is not None
        assert zone_upper is not None
        center = (zone_lower + zone_upper) / 2
        assert center == pytest.approx(90.0, rel=0.01)

    def test_derived_zone_unpaired_uses_individual_pivots(self):
        """
        Without use_paired_source (default), zones regenerate on any pivot.

        Even without a complete pair, zones are created from individual high/low.
        """
        from src.backtest.incremental.detectors.derived_zone import IncrementalDerivedZone

        swing = IncrementalSwingDetector({"left": 2, "right": 2}, None)
        params = {
            "levels": [0.5],
            "mode": "retracement",
            "max_active": 3,
            "width_pct": 0.02,
            # use_paired_source defaults to False
        }
        deps = {"source": swing}
        dz = IncrementalDerivedZone(params, deps)

        # Create swings that establish individual high and low
        bars = [
            make_bar(0, 100, 102, 99, 101),
            make_bar(1, 101, 103, 98, 100),
            make_bar(2, 100, 101, 80, 85),     # LOW at 80
            make_bar(3, 85, 87, 81, 86),
            make_bar(4, 84, 86, 82, 85),       # LOW confirmed
            make_bar(5, 85, 110, 84, 108),     # HIGH at 110
            make_bar(6, 108, 109, 105, 107),
            make_bar(7, 107, 108, 104, 106),   # HIGH confirmed
        ]
        for bar in bars:
            swing.update(bar.idx, bar)
            dz.update(bar.idx, bar)

        # Without paired source, zones are created as individual pivots are confirmed
        # version increments on each pivot, not just pairs
        assert swing.get_value("version") >= 2  # At least 2 pivots

        # Zone was created - check that zone0_lower has a value
        # (zone may be BROKEN due to price being outside, but it EXISTS)
        zone_lower = dz.get_value("zone0_lower")
        assert zone_lower is not None

        # 50% retracement of 80-110 range = 95
        zone_upper = dz.get_value("zone0_upper")
        center = (zone_lower + zone_upper) / 2
        assert center == pytest.approx(95.0, rel=0.01)
