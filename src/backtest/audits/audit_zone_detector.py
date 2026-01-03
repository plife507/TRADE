"""
Audit tests for IncrementalZoneDetector.

Tests:
1. Parameter validation (zone_type, width_atr)
2. Dependency validation (swing)
3. Demand zone creation and break detection
4. Supply zone creation and break detection
5. State transitions (none -> active -> broken)
6. Zone recalculation on new swing

Run as module:
    python -m src.backtest.audits.audit_zone_detector
"""

from __future__ import annotations

import sys
from typing import Any

import numpy as np

from ..incremental.base import BarData, BaseIncrementalDetector
from ..incremental.registry import STRUCTURE_REGISTRY, get_structure_info, unregister_structure
from ..incremental.detectors.zone import IncrementalZoneDetector


class MockSwingDetector(BaseIncrementalDetector):
    """
    Mock swing detector for testing zone detector.

    Allows manual control of swing levels and indices.
    """

    REQUIRED_PARAMS: list[str] = []
    OPTIONAL_PARAMS: dict[str, Any] = {}
    DEPENDS_ON: list[str] = []

    def __init__(
        self,
        params: dict[str, Any] | None = None,
        deps: dict[str, Any] | None = None,
    ) -> None:
        self.high_level: float = np.nan
        self.high_idx: int = -1
        self.low_level: float = np.nan
        self.low_idx: int = -1

    def set_swing_high(self, level: float, idx: int) -> None:
        """Set swing high for testing."""
        self.high_level = level
        self.high_idx = idx

    def set_swing_low(self, level: float, idx: int) -> None:
        """Set swing low for testing."""
        self.low_level = level
        self.low_idx = idx

    def update(self, bar_idx: int, bar: BarData) -> None:
        pass

    def get_output_keys(self) -> list[str]:
        return ["high_level", "high_idx", "low_level", "low_idx"]

    def get_value(self, key: str) -> float | int:
        return getattr(self, key)


def make_bar(
    idx: int,
    close: float,
    open_: float | None = None,
    high: float | None = None,
    low: float | None = None,
    atr: float | None = None,
) -> BarData:
    """Create a BarData for testing."""
    o = open_ if open_ is not None else close
    h = high if high is not None else max(o, close)
    l = low if low is not None else min(o, close)
    indicators = {"atr": atr} if atr is not None else {}
    return BarData(
        idx=idx,
        open=o,
        high=h,
        low=l,
        close=close,
        volume=1000.0,
        indicators=indicators,
    )


def test_zone_registered() -> None:
    """Test zone detector is registered in registry."""
    print("Testing zone registration...")

    assert "zone" in STRUCTURE_REGISTRY, "zone should be registered"
    assert STRUCTURE_REGISTRY["zone"] is IncrementalZoneDetector

    info = get_structure_info("zone")
    assert info["required_params"] == ["zone_type", "width_atr"]
    assert info["depends_on"] == ["swing"]
    assert info["class_name"] == "IncrementalZoneDetector"

    print("  zone registration: PASSED")


def test_validate_zone_type() -> None:
    """Test zone_type validation."""
    print("Testing zone_type validation...")

    mock_swing = MockSwingDetector()

    # Valid zone types should work
    for zone_type in ["demand", "supply"]:
        detector = IncrementalZoneDetector.validate_and_create(
            struct_type="zone",
            key="test_zone",
            params={"zone_type": zone_type, "width_atr": 1.5},
            deps={"swing": mock_swing},
        )
        assert detector.zone_type == zone_type

    # Invalid zone type should fail
    for invalid in ["support", "resistance", "DEMAND", "", None, 123]:
        try:
            IncrementalZoneDetector.validate_and_create(
                struct_type="zone",
                key="test_zone",
                params={"zone_type": invalid, "width_atr": 1.5},
                deps={"swing": mock_swing},
            )
            raise AssertionError(f"Should have rejected zone_type={invalid!r}")
        except ValueError as e:
            assert "'zone_type' must be 'demand' or 'supply'" in str(e)
            assert "Fix in IdeaCard:" in str(e)
            assert "Hint:" in str(e)

    print("  zone_type validation: PASSED")


def test_validate_width_atr() -> None:
    """Test width_atr validation."""
    print("Testing width_atr validation...")

    mock_swing = MockSwingDetector()

    # Valid width_atr values should work
    for width in [0.5, 1.0, 1.5, 2.0, 10]:
        detector = IncrementalZoneDetector.validate_and_create(
            struct_type="zone",
            key="test_zone",
            params={"zone_type": "demand", "width_atr": width},
            deps={"swing": mock_swing},
        )
        assert detector.width_atr == float(width)

    # Invalid width_atr should fail
    for invalid in [0, -1, -0.5, "1.5", None, []]:
        try:
            IncrementalZoneDetector.validate_and_create(
                struct_type="zone",
                key="test_zone",
                params={"zone_type": "demand", "width_atr": invalid},
                deps={"swing": mock_swing},
            )
            raise AssertionError(f"Should have rejected width_atr={invalid!r}")
        except ValueError as e:
            assert "'width_atr' must be a positive number" in str(e)
            assert "Fix in IdeaCard:" in str(e)
            assert "Hint:" in str(e)

    print("  width_atr validation: PASSED")


def test_missing_swing_dependency() -> None:
    """Test that missing swing dependency is caught."""
    print("Testing missing swing dependency...")

    try:
        IncrementalZoneDetector.validate_and_create(
            struct_type="zone",
            key="test_zone",
            params={"zone_type": "demand", "width_atr": 1.5},
            deps={},  # Missing swing
        )
        raise AssertionError("Should have rejected missing swing dependency")
    except ValueError as e:
        assert "missing dependencies" in str(e)
        assert "swing" in str(e)
        assert "depends_on:" in str(e)

    print("  missing swing dependency: PASSED")


def test_initial_state() -> None:
    """Test initial state is 'none'."""
    print("Testing initial state...")

    mock_swing = MockSwingDetector()
    detector = IncrementalZoneDetector.validate_and_create(
        struct_type="zone",
        key="test_zone",
        params={"zone_type": "demand", "width_atr": 1.5},
        deps={"swing": mock_swing},
    )

    assert detector.state == "none"
    assert np.isnan(detector.upper)
    assert np.isnan(detector.lower)
    assert detector.anchor_idx == -1

    print("  initial state: PASSED")


def test_demand_zone_creation() -> None:
    """Test demand zone creation from swing low."""
    print("Testing demand zone creation...")

    mock_swing = MockSwingDetector()
    detector = IncrementalZoneDetector.validate_and_create(
        struct_type="zone",
        key="demand_zone",
        params={"zone_type": "demand", "width_atr": 1.0},
        deps={"swing": mock_swing},
    )

    # Set swing low at 100.0 with ATR of 5.0
    mock_swing.set_swing_low(100.0, 5)

    # Update with a bar that has ATR=5.0
    bar = make_bar(idx=10, close=105.0, atr=5.0)
    detector.update(10, bar)

    # Demand zone should be active
    # lower = 100.0 - (5.0 * 1.0) = 95.0
    # upper = 100.0
    assert detector.state == "active"
    assert detector.lower == 95.0, f"Expected lower=95.0, got {detector.lower}"
    assert detector.upper == 100.0, f"Expected upper=100.0, got {detector.upper}"
    assert detector.anchor_idx == 5

    print("  demand zone creation: PASSED")


def test_supply_zone_creation() -> None:
    """Test supply zone creation from swing high."""
    print("Testing supply zone creation...")

    mock_swing = MockSwingDetector()
    detector = IncrementalZoneDetector.validate_and_create(
        struct_type="zone",
        key="supply_zone",
        params={"zone_type": "supply", "width_atr": 2.0},
        deps={"swing": mock_swing},
    )

    # Set swing high at 200.0 with ATR of 10.0
    mock_swing.set_swing_high(200.0, 8)

    # Update with a bar that has ATR=10.0
    bar = make_bar(idx=12, close=190.0, atr=10.0)
    detector.update(12, bar)

    # Supply zone should be active
    # lower = 200.0
    # upper = 200.0 + (10.0 * 2.0) = 220.0
    assert detector.state == "active"
    assert detector.lower == 200.0, f"Expected lower=200.0, got {detector.lower}"
    assert detector.upper == 220.0, f"Expected upper=220.0, got {detector.upper}"
    assert detector.anchor_idx == 8

    print("  supply zone creation: PASSED")


def test_demand_zone_break() -> None:
    """Test demand zone breaks when close < lower."""
    print("Testing demand zone break...")

    mock_swing = MockSwingDetector()
    detector = IncrementalZoneDetector.validate_and_create(
        struct_type="zone",
        key="demand_zone",
        params={"zone_type": "demand", "width_atr": 1.0},
        deps={"swing": mock_swing},
    )

    # Create demand zone: lower=95, upper=100
    mock_swing.set_swing_low(100.0, 5)
    bar1 = make_bar(idx=10, close=105.0, atr=5.0)
    detector.update(10, bar1)
    assert detector.state == "active"

    # Price stays above lower - still active
    bar2 = make_bar(idx=11, close=96.0, atr=5.0)
    detector.update(11, bar2)
    assert detector.state == "active"

    # Price closes below lower - zone broken
    bar3 = make_bar(idx=12, close=94.0, atr=5.0)
    detector.update(12, bar3)
    assert detector.state == "broken"

    # Stays broken
    bar4 = make_bar(idx=13, close=97.0, atr=5.0)
    detector.update(13, bar4)
    assert detector.state == "broken"

    print("  demand zone break: PASSED")


def test_supply_zone_break() -> None:
    """Test supply zone breaks when close > upper."""
    print("Testing supply zone break...")

    mock_swing = MockSwingDetector()
    detector = IncrementalZoneDetector.validate_and_create(
        struct_type="zone",
        key="supply_zone",
        params={"zone_type": "supply", "width_atr": 1.0},
        deps={"swing": mock_swing},
    )

    # Create supply zone: lower=200, upper=210
    mock_swing.set_swing_high(200.0, 5)
    bar1 = make_bar(idx=10, close=195.0, atr=10.0)
    detector.update(10, bar1)
    assert detector.state == "active"
    assert detector.lower == 200.0
    assert detector.upper == 210.0

    # Price stays below upper - still active
    bar2 = make_bar(idx=11, close=208.0, atr=10.0)
    detector.update(11, bar2)
    assert detector.state == "active"

    # Price closes above upper - zone broken
    bar3 = make_bar(idx=12, close=211.0, atr=10.0)
    detector.update(12, bar3)
    assert detector.state == "broken"

    print("  supply zone break: PASSED")


def test_zone_recalculation_on_new_swing() -> None:
    """Test zone recalculates when new swing is detected."""
    print("Testing zone recalculation on new swing...")

    mock_swing = MockSwingDetector()
    detector = IncrementalZoneDetector.validate_and_create(
        struct_type="zone",
        key="demand_zone",
        params={"zone_type": "demand", "width_atr": 1.0},
        deps={"swing": mock_swing},
    )

    # First swing low
    mock_swing.set_swing_low(100.0, 5)
    bar1 = make_bar(idx=10, close=105.0, atr=5.0)
    detector.update(10, bar1)
    assert detector.lower == 95.0
    assert detector.upper == 100.0
    assert detector.anchor_idx == 5

    # New swing low at different level
    mock_swing.set_swing_low(90.0, 15)
    bar2 = make_bar(idx=20, close=95.0, atr=4.0)
    detector.update(20, bar2)

    # Zone should be recalculated: lower=90-4=86, upper=90
    assert detector.state == "active"
    assert detector.lower == 86.0, f"Expected lower=86.0, got {detector.lower}"
    assert detector.upper == 90.0, f"Expected upper=90.0, got {detector.upper}"
    assert detector.anchor_idx == 15

    print("  zone recalculation on new swing: PASSED")


def test_zone_no_atr() -> None:
    """Test zone creation without ATR in indicators."""
    print("Testing zone without ATR...")

    mock_swing = MockSwingDetector()
    detector = IncrementalZoneDetector.validate_and_create(
        struct_type="zone",
        key="demand_zone",
        params={"zone_type": "demand", "width_atr": 1.0},
        deps={"swing": mock_swing},
    )

    # Create zone without ATR - width should be 0
    mock_swing.set_swing_low(100.0, 5)
    bar = make_bar(idx=10, close=105.0)  # No ATR
    detector.update(10, bar)

    # Zone should have zero width
    assert detector.state == "active"
    assert detector.lower == 100.0, f"Expected lower=100.0, got {detector.lower}"
    assert detector.upper == 100.0, f"Expected upper=100.0, got {detector.upper}"

    print("  zone without ATR: PASSED")


def test_output_keys() -> None:
    """Test get_output_keys returns correct keys."""
    print("Testing output keys...")

    mock_swing = MockSwingDetector()
    detector = IncrementalZoneDetector.validate_and_create(
        struct_type="zone",
        key="test_zone",
        params={"zone_type": "demand", "width_atr": 1.0},
        deps={"swing": mock_swing},
    )

    keys = detector.get_output_keys()
    assert keys == ["state", "upper", "lower", "anchor_idx"]

    print("  output keys: PASSED")


def test_get_value() -> None:
    """Test get_value returns correct values."""
    print("Testing get_value...")

    mock_swing = MockSwingDetector()
    detector = IncrementalZoneDetector.validate_and_create(
        struct_type="zone",
        key="test_zone",
        params={"zone_type": "demand", "width_atr": 1.0},
        deps={"swing": mock_swing},
    )

    # Create zone
    mock_swing.set_swing_low(100.0, 5)
    bar = make_bar(idx=10, close=105.0, atr=5.0)
    detector.update(10, bar)

    assert detector.get_value("state") == "active"
    assert detector.get_value("upper") == 100.0
    assert detector.get_value("lower") == 95.0
    assert detector.get_value("anchor_idx") == 5

    # Invalid key should raise KeyError
    try:
        detector.get_value("invalid")
        raise AssertionError("Should have raised KeyError for invalid key")
    except KeyError:
        pass

    print("  get_value: PASSED")


def test_get_value_safe() -> None:
    """Test get_value_safe provides helpful error messages."""
    print("Testing get_value_safe...")

    mock_swing = MockSwingDetector()
    detector = IncrementalZoneDetector.validate_and_create(
        struct_type="zone",
        key="my_zone",
        params={"zone_type": "demand", "width_atr": 1.0},
        deps={"swing": mock_swing},
    )

    # Valid keys work
    assert detector.get_value_safe("state") == "none"

    # Invalid key gives helpful error
    try:
        detector.get_value_safe("invalid_key")
        raise AssertionError("Should have raised KeyError")
    except KeyError as e:
        error_msg = str(e)
        assert "has no output 'invalid_key'" in error_msg
        assert "state" in error_msg  # Should list valid keys
        assert "upper" in error_msg
        assert "Fix:" in error_msg

    print("  get_value_safe: PASSED")


def test_get_all_values() -> None:
    """Test get_all_values returns all outputs."""
    print("Testing get_all_values...")

    mock_swing = MockSwingDetector()
    detector = IncrementalZoneDetector.validate_and_create(
        struct_type="zone",
        key="test_zone",
        params={"zone_type": "supply", "width_atr": 2.0},
        deps={"swing": mock_swing},
    )

    # Create supply zone
    mock_swing.set_swing_high(150.0, 7)
    bar = make_bar(idx=10, close=145.0, atr=5.0)
    detector.update(10, bar)

    all_values = detector.get_all_values()
    assert all_values["state"] == "active"
    assert all_values["upper"] == 160.0  # 150 + (5 * 2)
    assert all_values["lower"] == 150.0
    assert all_values["anchor_idx"] == 7

    print("  get_all_values: PASSED")


def run_all_tests() -> bool:
    """Run all validation tests."""
    print("=" * 60)
    print("IncrementalZoneDetector Validation Tests")
    print("=" * 60)
    print()

    tests = [
        test_zone_registered,
        test_validate_zone_type,
        test_validate_width_atr,
        test_missing_swing_dependency,
        test_initial_state,
        test_demand_zone_creation,
        test_supply_zone_creation,
        test_demand_zone_break,
        test_supply_zone_break,
        test_zone_recalculation_on_new_swing,
        test_zone_no_atr,
        test_output_keys,
        test_get_value,
        test_get_value_safe,
        test_get_all_values,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  FAILED: {e}")
            import traceback

            traceback.print_exc()
            failed += 1

    print()
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
