"""
Audit tests for IncrementalFibonacci detector.

Tests:
1. Parameter validation (levels, mode)
2. Dependency validation
3. Level calculation (retracement and extension modes)
4. Recalculation only when swings change
5. Output key generation

Run as module:
    python -m src.backtest.audits.audit_fibonacci
"""

from __future__ import annotations

import math
import sys
from typing import Any

from src.structures import (
    BarData,
    BaseIncrementalDetector,
    unregister_structure,
    IncrementalFibonacci,
)


class MockSwingDetector(BaseIncrementalDetector):
    """
    Mock swing detector for testing Fibonacci dependency.

    Allows manual setting of swing high/low levels and indices
    to test Fibonacci recalculation logic.
    """

    REQUIRED_PARAMS: list[str] = []
    OPTIONAL_PARAMS: dict[str, Any] = {}
    DEPENDS_ON: list[str] = []

    def __init__(
        self,
        params: dict[str, Any] | None = None,
        deps: dict[str, Any] | None = None,
    ) -> None:
        self.high_level: float = float("nan")
        self.high_idx: int = -1
        self.low_level: float = float("nan")
        self.low_idx: int = -1

    def set_swing(
        self,
        high_level: float,
        high_idx: int,
        low_level: float,
        low_idx: int,
    ) -> None:
        """Set swing values for testing."""
        self.high_level = high_level
        self.high_idx = high_idx
        self.low_level = low_level
        self.low_idx = low_idx

    def update(self, bar_idx: int, bar: BarData) -> None:
        pass

    def get_output_keys(self) -> list[str]:
        return ["high_level", "high_idx", "low_level", "low_idx"]

    def get_value(self, key: str) -> float | int:
        return getattr(self, key)


def make_bar(idx: int, close: float = 100.0) -> BarData:
    """Create a minimal bar for testing."""
    return BarData(
        idx=idx,
        open=close,
        high=close + 1,
        low=close - 1,
        close=close,
        volume=1000.0,
        indicators={},
    )


def test_validate_params_levels_required() -> None:
    """Test that levels parameter is required and must be non-empty list."""
    print("Testing validate_params levels required...")

    # Missing levels
    try:
        IncrementalFibonacci.validate_and_create(
            struct_type="fibonacci",
            key="fib",
            params={},  # Missing levels
            deps={"swing": MockSwingDetector()},
        )
        raise AssertionError("Should have rejected missing levels")
    except ValueError as e:
        assert "missing required params" in str(e), f"Wrong error: {e}"
        assert "levels" in str(e), f"Should mention levels: {e}"

    print("  validate_params levels required: PASSED")


def test_validate_params_levels_non_empty() -> None:
    """Test that levels must be non-empty list."""
    print("Testing validate_params levels non-empty...")

    # Empty list
    try:
        IncrementalFibonacci.validate_and_create(
            struct_type="fibonacci",
            key="fib",
            params={"levels": []},
            deps={"swing": MockSwingDetector()},
        )
        raise AssertionError("Should have rejected empty levels")
    except ValueError as e:
        assert "non-empty list" in str(e), f"Wrong error: {e}"
        assert "Fix:" in str(e), f"Should include fix suggestion: {e}"

    print("  validate_params levels non-empty: PASSED")


def test_validate_params_levels_must_be_numbers() -> None:
    """Test that levels must be numbers."""
    print("Testing validate_params levels must be numbers...")

    # Non-numeric level
    try:
        IncrementalFibonacci.validate_and_create(
            struct_type="fibonacci",
            key="fib",
            params={"levels": [0.382, "0.618", 0.786]},  # String in list
            deps={"swing": MockSwingDetector()},
        )
        raise AssertionError("Should have rejected non-numeric level")
    except ValueError as e:
        assert "must be a number" in str(e), f"Wrong error: {e}"
        assert "levels[1]" in str(e), f"Should identify which level: {e}"

    print("  validate_params levels must be numbers: PASSED")


def test_validate_params_levels_must_be_positive() -> None:
    """Test that levels must be positive numbers."""
    print("Testing validate_params levels must be positive...")

    # Negative level
    try:
        IncrementalFibonacci.validate_and_create(
            struct_type="fibonacci",
            key="fib",
            params={"levels": [0.382, -0.618, 0.786]},
            deps={"swing": MockSwingDetector()},
        )
        raise AssertionError("Should have rejected negative level")
    except ValueError as e:
        assert "must be positive" in str(e), f"Wrong error: {e}"
        assert "levels[1]" in str(e), f"Should identify which level: {e}"

    # Zero level
    try:
        IncrementalFibonacci.validate_and_create(
            struct_type="fibonacci",
            key="fib",
            params={"levels": [0.0, 0.618]},
            deps={"swing": MockSwingDetector()},
        )
        raise AssertionError("Should have rejected zero level")
    except ValueError as e:
        assert "must be positive" in str(e), f"Wrong error: {e}"

    print("  validate_params levels must be positive: PASSED")


def test_validate_params_mode() -> None:
    """Test that mode must be retracement or extension."""
    print("Testing validate_params mode...")

    # Invalid mode
    try:
        IncrementalFibonacci.validate_and_create(
            struct_type="fibonacci",
            key="fib",
            params={"levels": [0.618], "mode": "invalid"},
            deps={"swing": MockSwingDetector()},
        )
        raise AssertionError("Should have rejected invalid mode")
    except ValueError as e:
        assert "must be 'retracement' or 'extension'" in str(e), f"Wrong error: {e}"
        assert "Fix:" in str(e), f"Should include fix suggestion: {e}"

    print("  validate_params mode: PASSED")


def test_validate_depends_on_swing() -> None:
    """Test that swing dependency is required."""
    print("Testing validate depends_on swing...")

    try:
        IncrementalFibonacci.validate_and_create(
            struct_type="fibonacci",
            key="fib",
            params={"levels": [0.618]},
            deps={},  # Missing swing
        )
        raise AssertionError("Should have rejected missing swing")
    except ValueError as e:
        assert "missing dependencies" in str(e), f"Wrong error: {e}"
        assert "swing" in str(e), f"Should mention swing: {e}"

    print("  validate depends_on swing: PASSED")


def test_output_keys_dynamic() -> None:
    """Test that output keys are dynamically generated from levels."""
    print("Testing output_keys dynamic...")

    detector = IncrementalFibonacci.validate_and_create(
        struct_type="fibonacci",
        key="fib",
        params={"levels": [0.236, 0.382, 0.618]},
        deps={"swing": MockSwingDetector()},
    )

    keys = detector.get_output_keys()
    assert keys == ["level_0.236", "level_0.382", "level_0.618"], f"Got: {keys}"

    # Test with integer level
    detector2 = IncrementalFibonacci.validate_and_create(
        struct_type="fibonacci",
        key="fib2",
        params={"levels": [0.5, 1.0, 1.618]},
        deps={"swing": MockSwingDetector()},
    )

    keys2 = detector2.get_output_keys()
    assert keys2 == ["level_0.5", "level_1", "level_1.618"], f"Got: {keys2}"

    print("  output_keys dynamic: PASSED")


def test_retracement_calculation() -> None:
    """Test Fibonacci retracement level calculation."""
    print("Testing retracement calculation...")

    swing = MockSwingDetector()
    swing.set_swing(
        high_level=100.0,
        high_idx=10,
        low_level=50.0,
        low_idx=5,
    )

    detector = IncrementalFibonacci.validate_and_create(
        struct_type="fibonacci",
        key="fib",
        params={"levels": [0.236, 0.382, 0.5, 0.618], "mode": "retracement"},
        deps={"swing": swing},
    )

    # Update to trigger calculation
    detector.update(0, make_bar(0))

    # Range = 100 - 50 = 50
    # Retracement: high - (range * level)
    # 0.236: 100 - (50 * 0.236) = 100 - 11.8 = 88.2
    # 0.382: 100 - (50 * 0.382) = 100 - 19.1 = 80.9
    # 0.5:   100 - (50 * 0.5) = 100 - 25 = 75.0
    # 0.618: 100 - (50 * 0.618) = 100 - 30.9 = 69.1

    assert abs(detector.get_value("level_0.236") - 88.2) < 0.01, f"Got: {detector.get_value('level_0.236')}"
    assert abs(detector.get_value("level_0.382") - 80.9) < 0.01, f"Got: {detector.get_value('level_0.382')}"
    assert abs(detector.get_value("level_0.5") - 75.0) < 0.01, f"Got: {detector.get_value('level_0.5')}"
    assert abs(detector.get_value("level_0.618") - 69.1) < 0.01, f"Got: {detector.get_value('level_0.618')}"

    print("  retracement calculation: PASSED")


def test_extension_calculation() -> None:
    """Test Fibonacci extension level calculation."""
    print("Testing extension calculation...")

    swing = MockSwingDetector()
    swing.set_swing(
        high_level=100.0,
        high_idx=10,
        low_level=50.0,
        low_idx=5,
    )

    detector = IncrementalFibonacci.validate_and_create(
        struct_type="fibonacci",
        key="fib",
        params={"levels": [0.618, 1.0, 1.618], "mode": "extension"},
        deps={"swing": swing},
    )

    # Update to trigger calculation
    detector.update(0, make_bar(0))

    # Range = 100 - 50 = 50
    # Extension: high + (range * level)
    # 0.618: 100 + (50 * 0.618) = 100 + 30.9 = 130.9
    # 1.0:   100 + (50 * 1.0) = 100 + 50 = 150.0
    # 1.618: 100 + (50 * 1.618) = 100 + 80.9 = 180.9

    assert abs(detector.get_value("level_0.618") - 130.9) < 0.01, f"Got: {detector.get_value('level_0.618')}"
    assert abs(detector.get_value("level_1") - 150.0) < 0.01, f"Got: {detector.get_value('level_1')}"
    assert abs(detector.get_value("level_1.618") - 180.9) < 0.01, f"Got: {detector.get_value('level_1.618')}"

    print("  extension calculation: PASSED")


def test_recalculation_on_swing_change() -> None:
    """Test that levels are recalculated only when swings change."""
    print("Testing recalculation on swing change...")

    swing = MockSwingDetector()
    swing.set_swing(high_level=100.0, high_idx=10, low_level=50.0, low_idx=5)

    detector = IncrementalFibonacci.validate_and_create(
        struct_type="fibonacci",
        key="fib",
        params={"levels": [0.5], "mode": "retracement"},
        deps={"swing": swing},
    )

    # Initial update
    detector.update(0, make_bar(0))
    initial_value = detector.get_value("level_0.5")
    assert initial_value == 75.0, f"Expected 75.0, got {initial_value}"

    # Update without swing change - should not recalculate
    detector.update(1, make_bar(1))
    assert detector.get_value("level_0.5") == 75.0

    # Change swing high
    swing.set_swing(high_level=120.0, high_idx=15, low_level=50.0, low_idx=5)
    detector.update(2, make_bar(2))

    # Range = 120 - 50 = 70
    # 0.5: 120 - (70 * 0.5) = 120 - 35 = 85.0
    assert detector.get_value("level_0.5") == 85.0, f"Got: {detector.get_value('level_0.5')}"

    print("  recalculation on swing change: PASSED")


def test_nan_before_swings_set() -> None:
    """Test that levels are NaN before swings are detected."""
    print("Testing NaN before swings set...")

    swing = MockSwingDetector()
    # Swing not set, values are NaN

    detector = IncrementalFibonacci.validate_and_create(
        struct_type="fibonacci",
        key="fib",
        params={"levels": [0.618]},
        deps={"swing": swing},
    )

    detector.update(0, make_bar(0))
    value = detector.get_value("level_0.618")
    assert math.isnan(value), f"Expected NaN, got {value}"

    print("  NaN before swings set: PASSED")


def test_get_value_invalid_key() -> None:
    """Test that get_value raises KeyError for invalid keys."""
    print("Testing get_value invalid key...")

    swing = MockSwingDetector()
    swing.set_swing(high_level=100.0, high_idx=10, low_level=50.0, low_idx=5)

    detector = IncrementalFibonacci.validate_and_create(
        struct_type="fibonacci",
        key="fib",
        params={"levels": [0.618]},
        deps={"swing": swing},
    )

    try:
        detector.get_value("level_0.5")  # Not in levels
        raise AssertionError("Should have raised KeyError")
    except KeyError:
        pass  # Expected

    # get_value_safe should provide helpful error
    try:
        detector.get_value_safe("invalid_key")
        raise AssertionError("Should have raised KeyError")
    except KeyError as e:
        assert "has no output 'invalid_key'" in str(e), f"Wrong error: {e}"
        assert "level_0.618" in str(e), f"Should list available keys: {e}"

    print("  get_value invalid key: PASSED")


def test_repr() -> None:
    """Test __repr__ for debugging."""
    print("Testing __repr__...")

    detector = IncrementalFibonacci.validate_and_create(
        struct_type="fibonacci",
        key="fib",
        params={"levels": [0.382, 0.618], "mode": "extension"},
        deps={"swing": MockSwingDetector()},
    )

    repr_str = repr(detector)
    assert "IncrementalFibonacci" in repr_str
    assert "0.382" in repr_str
    assert "0.618" in repr_str
    assert "extension" in repr_str

    print("  __repr__: PASSED")


def run_all_tests() -> bool:
    """Run all validation tests."""
    print("=" * 60)
    print("IncrementalFibonacci Validation Tests")
    print("=" * 60)
    print()

    tests = [
        test_validate_params_levels_required,
        test_validate_params_levels_non_empty,
        test_validate_params_levels_must_be_numbers,
        test_validate_params_levels_must_be_positive,
        test_validate_params_mode,
        test_validate_depends_on_swing,
        test_output_keys_dynamic,
        test_retracement_calculation,
        test_extension_calculation,
        test_recalculation_on_swing_change,
        test_nan_before_swings_set,
        test_get_value_invalid_key,
        test_repr,
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
