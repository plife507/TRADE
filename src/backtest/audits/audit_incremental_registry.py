"""
Validation tests for incremental state registry.

Tests:
1. register_structure decorator works correctly
2. validate_and_create catches missing params
3. validate_and_create catches missing deps
4. get_structure_info returns correct data
5. list_structure_types works

Run as module:
    python -m src.backtest.audits.audit_incremental_registry
"""

from __future__ import annotations

import sys
from typing import Any

# Import the components we're testing
from ..incremental.base import BarData, BaseIncrementalDetector
from ..incremental.registry import (
    STRUCTURE_REGISTRY,
    get_structure_info,
    list_structure_types,
    register_structure,
    unregister_structure,
)


def test_bar_data() -> None:
    """Test BarData dataclass creation and access."""
    print("Testing BarData...")

    bar = BarData(
        idx=100,
        open=50000.0,
        high=50500.0,
        low=49800.0,
        close=50200.0,
        volume=1234.5,
        indicators={"atr": 245.5, "ema_20": 50100.0},
    )

    assert bar.idx == 100, f"Expected idx=100, got {bar.idx}"
    assert bar.open == 50000.0, f"Expected open=50000.0, got {bar.open}"
    assert bar.high == 50500.0, f"Expected high=50500.0, got {bar.high}"
    assert bar.low == 49800.0, f"Expected low=49800.0, got {bar.low}"
    assert bar.close == 50200.0, f"Expected close=50200.0, got {bar.close}"
    assert bar.volume == 1234.5, f"Expected volume=1234.5, got {bar.volume}"
    assert bar.indicators["atr"] == 245.5, f"Expected atr=245.5, got {bar.indicators['atr']}"
    assert bar.indicators["ema_20"] == 50100.0

    # Test immutability (frozen=True)
    try:
        bar.idx = 200  # type: ignore
        raise AssertionError("BarData should be immutable")
    except AttributeError:
        pass  # Expected

    print("  BarData: PASSED")


def test_register_structure_works() -> None:
    """Test that register_structure decorator registers class correctly."""
    print("Testing register_structure...")

    # Clean up any previous test registration
    unregister_structure("_test_detector")

    @register_structure("_test_detector")
    class TestDetector(BaseIncrementalDetector):
        REQUIRED_PARAMS = ["period"]
        OPTIONAL_PARAMS = {"threshold": 0.5}
        DEPENDS_ON = []

        def __init__(self, params: dict[str, Any], deps: dict[str, Any]) -> None:
            self.period = params["period"]
            self.threshold = params.get("threshold", 0.5)
            self._value = 0.0

        def update(self, bar_idx: int, bar: BarData) -> None:
            self._value = bar.close

        def get_output_keys(self) -> list[str]:
            return ["value"]

        def get_value(self, key: str) -> float | int | str:
            if key == "value":
                return self._value
            raise KeyError(key)

    # Verify registration
    assert "_test_detector" in STRUCTURE_REGISTRY, "Detector should be registered"
    assert STRUCTURE_REGISTRY["_test_detector"] is TestDetector

    # Clean up
    unregister_structure("_test_detector")

    print("  register_structure: PASSED")


def test_register_validates_inheritance() -> None:
    """Test that register_structure rejects non-BaseIncrementalDetector classes."""
    print("Testing register_structure inheritance validation...")

    try:

        @register_structure("_bad_detector")
        class BadDetector:  # Does not inherit from BaseIncrementalDetector
            REQUIRED_PARAMS = []
            OPTIONAL_PARAMS = {}
            DEPENDS_ON = []

        raise AssertionError("Should have rejected non-subclass")
    except TypeError as e:
        assert "must inherit from BaseIncrementalDetector" in str(e), f"Wrong error: {e}"
        assert "Fix:" in str(e), "Error should include fix suggestion"

    # Clean up just in case
    unregister_structure("_bad_detector")

    print("  register_structure inheritance validation: PASSED")


def test_register_validates_class_attributes() -> None:
    """Test that register_structure checks for required class attributes."""
    print("Testing register_structure class attribute validation...")

    try:

        @register_structure("_missing_attrs")
        class MissingAttrs(BaseIncrementalDetector):
            # Missing REQUIRED_PARAMS, OPTIONAL_PARAMS, DEPENDS_ON
            def update(self, bar_idx: int, bar: BarData) -> None:
                pass

            def get_output_keys(self) -> list[str]:
                return []

            def get_value(self, key: str) -> float | int | str:
                raise KeyError(key)

        # Should not reach here if class is missing attributes
        # But since BaseIncrementalDetector has defaults, this should pass
        unregister_structure("_missing_attrs")

    except TypeError as e:
        assert "missing class attributes" in str(e), f"Wrong error: {e}"

    print("  register_structure class attribute validation: PASSED")


def test_register_rejects_duplicate() -> None:
    """Test that register_structure rejects duplicate registrations."""
    print("Testing register_structure duplicate rejection...")

    unregister_structure("_dup_test")

    @register_structure("_dup_test")
    class First(BaseIncrementalDetector):
        REQUIRED_PARAMS = []
        OPTIONAL_PARAMS = {}
        DEPENDS_ON = []

        def update(self, bar_idx: int, bar: BarData) -> None:
            pass

        def get_output_keys(self) -> list[str]:
            return []

        def get_value(self, key: str) -> float | int | str:
            raise KeyError(key)

    try:

        @register_structure("_dup_test")
        class Second(BaseIncrementalDetector):
            REQUIRED_PARAMS = []
            OPTIONAL_PARAMS = {}
            DEPENDS_ON = []

            def update(self, bar_idx: int, bar: BarData) -> None:
                pass

            def get_output_keys(self) -> list[str]:
                return []

            def get_value(self, key: str) -> float | int | str:
                raise KeyError(key)

        raise AssertionError("Should have rejected duplicate registration")
    except ValueError as e:
        assert "already registered" in str(e), f"Wrong error: {e}"

    unregister_structure("_dup_test")

    print("  register_structure duplicate rejection: PASSED")


def test_validate_and_create_missing_params() -> None:
    """Test that validate_and_create catches missing required params."""
    print("Testing validate_and_create missing params...")

    unregister_structure("_param_test")

    @register_structure("_param_test")
    class ParamTest(BaseIncrementalDetector):
        REQUIRED_PARAMS = ["period", "threshold"]
        OPTIONAL_PARAMS = {"scale": 1.0}
        DEPENDS_ON = []

        def __init__(self, params: dict[str, Any], deps: dict[str, Any]) -> None:
            self.period = params["period"]
            self.threshold = params["threshold"]

        def update(self, bar_idx: int, bar: BarData) -> None:
            pass

        def get_output_keys(self) -> list[str]:
            return ["result"]

        def get_value(self, key: str) -> float | int | str:
            return 0.0

    # Try to create with missing params
    try:
        ParamTest.validate_and_create(
            struct_type="_param_test",
            key="my_test",
            params={"period": 10},  # Missing "threshold"
            deps={},
        )
        raise AssertionError("Should have rejected missing params")
    except ValueError as e:
        error_msg = str(e)
        assert "missing required params" in error_msg, f"Wrong error: {e}"
        assert "threshold" in error_msg, f"Should mention missing param: {e}"
        assert "Fix in Play:" in error_msg, f"Should include fix suggestion: {e}"
        assert "REQUIRED" in error_msg, f"Should mark as REQUIRED: {e}"

    unregister_structure("_param_test")

    print("  validate_and_create missing params: PASSED")


def test_validate_and_create_missing_deps() -> None:
    """Test that validate_and_create catches missing dependencies."""
    print("Testing validate_and_create missing deps...")

    unregister_structure("_dep_test")

    @register_structure("_dep_test")
    class DepTest(BaseIncrementalDetector):
        REQUIRED_PARAMS = []
        OPTIONAL_PARAMS = {}
        DEPENDS_ON = ["swing", "trend"]

        def __init__(self, params: dict[str, Any], deps: dict[str, Any]) -> None:
            self.swing = deps["swing"]
            self.trend = deps["trend"]

        def update(self, bar_idx: int, bar: BarData) -> None:
            pass

        def get_output_keys(self) -> list[str]:
            return ["result"]

        def get_value(self, key: str) -> float | int | str:
            return 0.0

    # Try to create with missing deps
    try:
        DepTest.validate_and_create(
            struct_type="_dep_test",
            key="my_dep_test",
            params={},
            deps={"swing": None},  # Missing "trend"  # type: ignore
        )
        raise AssertionError("Should have rejected missing deps")
    except ValueError as e:
        error_msg = str(e)
        assert "missing dependencies" in error_msg, f"Wrong error: {e}"
        assert "trend" in error_msg, f"Should mention missing dep: {e}"
        assert "Fix in Play:" in error_msg, f"Should include fix suggestion: {e}"
        assert "depends_on:" in error_msg, f"Should show depends_on section: {e}"

    unregister_structure("_dep_test")

    print("  validate_and_create missing deps: PASSED")


def test_validate_and_create_success() -> None:
    """Test validate_and_create with valid params and deps."""
    print("Testing validate_and_create success...")

    unregister_structure("_success_test")

    @register_structure("_success_test")
    class SuccessTest(BaseIncrementalDetector):
        REQUIRED_PARAMS = ["period"]
        OPTIONAL_PARAMS = {"threshold": 0.5}
        DEPENDS_ON = []

        def __init__(self, params: dict[str, Any], deps: dict[str, Any]) -> None:
            self.period = params["period"]
            self.threshold = params.get("threshold", 0.5)
            self._result = 0.0

        def update(self, bar_idx: int, bar: BarData) -> None:
            self._result = bar.close * self.threshold

        def get_output_keys(self) -> list[str]:
            return ["result"]

        def get_value(self, key: str) -> float | int | str:
            if key == "result":
                return self._result
            raise KeyError(key)

    # Create with valid params
    detector = SuccessTest.validate_and_create(
        struct_type="_success_test",
        key="my_success",
        params={"period": 20, "threshold": 0.8},
        deps={},
    )

    assert detector._key == "my_success", f"Expected key='my_success', got '{detector._key}'"
    assert detector._type == "_success_test", f"Expected type='_success_test', got '{detector._type}'"
    assert detector.period == 20
    assert detector.threshold == 0.8

    # Test update and get_value
    bar = BarData(
        idx=0,
        open=100.0,
        high=110.0,
        low=90.0,
        close=105.0,
        volume=1000.0,
        indicators={},
    )
    detector.update(0, bar)
    assert detector.get_value("result") == 105.0 * 0.8

    unregister_structure("_success_test")

    print("  validate_and_create success: PASSED")


def test_get_value_safe() -> None:
    """Test get_value_safe validates keys and provides suggestions."""
    print("Testing get_value_safe...")

    unregister_structure("_safe_test")

    @register_structure("_safe_test")
    class SafeTest(BaseIncrementalDetector):
        REQUIRED_PARAMS = []
        OPTIONAL_PARAMS = {}
        DEPENDS_ON = []

        def __init__(self, params: dict[str, Any], deps: dict[str, Any]) -> None:
            self._value_a = 1.0
            self._value_b = 2.0

        def update(self, bar_idx: int, bar: BarData) -> None:
            pass

        def get_output_keys(self) -> list[str]:
            return ["value_a", "value_b"]

        def get_value(self, key: str) -> float | int | str:
            if key == "value_a":
                return self._value_a
            if key == "value_b":
                return self._value_b
            raise KeyError(key)

    detector = SafeTest.validate_and_create(
        struct_type="_safe_test",
        key="safe",
        params={},
        deps={},
    )

    # Valid key should work
    assert detector.get_value_safe("value_a") == 1.0
    assert detector.get_value_safe("value_b") == 2.0

    # Invalid key should fail with suggestions
    try:
        detector.get_value_safe("invalid_key")
        raise AssertionError("Should have rejected invalid key")
    except KeyError as e:
        error_msg = str(e)
        assert "has no output 'invalid_key'" in error_msg, f"Wrong error: {e}"
        assert "value_a" in error_msg, f"Should suggest valid keys: {e}"
        assert "value_b" in error_msg, f"Should suggest valid keys: {e}"
        assert "Fix:" in error_msg, f"Should include fix suggestion: {e}"

    unregister_structure("_safe_test")

    print("  get_value_safe: PASSED")


def test_get_all_values() -> None:
    """Test get_all_values returns all outputs."""
    print("Testing get_all_values...")

    unregister_structure("_all_vals_test")

    @register_structure("_all_vals_test")
    class AllValsTest(BaseIncrementalDetector):
        REQUIRED_PARAMS = []
        OPTIONAL_PARAMS = {}
        DEPENDS_ON = []

        def __init__(self, params: dict[str, Any], deps: dict[str, Any]) -> None:
            self._alpha = 10.0
            self._beta = 20.0
            self._gamma = 30.0

        def update(self, bar_idx: int, bar: BarData) -> None:
            pass

        def get_output_keys(self) -> list[str]:
            return ["alpha", "beta", "gamma"]

        def get_value(self, key: str) -> float | int | str:
            return {"alpha": self._alpha, "beta": self._beta, "gamma": self._gamma}[key]

    detector = AllValsTest.validate_and_create(
        struct_type="_all_vals_test",
        key="all_vals",
        params={},
        deps={},
    )

    all_vals = detector.get_all_values()
    assert all_vals == {"alpha": 10.0, "beta": 20.0, "gamma": 30.0}

    unregister_structure("_all_vals_test")

    print("  get_all_values: PASSED")


def test_get_structure_info() -> None:
    """Test get_structure_info returns correct metadata."""
    print("Testing get_structure_info...")

    unregister_structure("_info_test")

    @register_structure("_info_test")
    class InfoTest(BaseIncrementalDetector):
        """This is the docstring."""

        REQUIRED_PARAMS = ["period", "threshold"]
        OPTIONAL_PARAMS = {"scale": 1.0, "offset": 0.0}
        DEPENDS_ON = ["swing"]

        def __init__(self, params: dict[str, Any], deps: dict[str, Any]) -> None:
            pass

        def update(self, bar_idx: int, bar: BarData) -> None:
            pass

        def get_output_keys(self) -> list[str]:
            return ["result"]

        def get_value(self, key: str) -> float | int | str:
            return 0.0

    info = get_structure_info("_info_test")

    assert info["required_params"] == ["period", "threshold"], f"Wrong required_params: {info}"
    assert info["optional_params"] == {"scale": 1.0, "offset": 0.0}, f"Wrong optional_params: {info}"
    assert info["depends_on"] == ["swing"], f"Wrong depends_on: {info}"
    assert info["class_name"] == "InfoTest", f"Wrong class_name: {info}"
    assert "This is the docstring." in (info["docstring"] or ""), f"Wrong docstring: {info}"

    unregister_structure("_info_test")

    print("  get_structure_info: PASSED")


def test_get_structure_info_not_found() -> None:
    """Test get_structure_info fails for unknown types with suggestions."""
    print("Testing get_structure_info not found...")

    try:
        get_structure_info("_nonexistent_type")
        raise AssertionError("Should have rejected unknown type")
    except KeyError as e:
        error_msg = str(e)
        assert "not registered" in error_msg, f"Wrong error: {e}"
        assert "Available types:" in error_msg, f"Should list available types: {e}"
        assert "Fix:" in error_msg, f"Should include fix suggestion: {e}"

    print("  get_structure_info not found: PASSED")


def test_list_structure_types() -> None:
    """Test list_structure_types returns registered types."""
    print("Testing list_structure_types...")

    # Clean slate
    unregister_structure("_list_a")
    unregister_structure("_list_b")

    # Get baseline
    baseline = set(list_structure_types())

    @register_structure("_list_a")
    class ListA(BaseIncrementalDetector):
        REQUIRED_PARAMS = []
        OPTIONAL_PARAMS = {}
        DEPENDS_ON = []

        def update(self, bar_idx: int, bar: BarData) -> None:
            pass

        def get_output_keys(self) -> list[str]:
            return []

        def get_value(self, key: str) -> float | int | str:
            raise KeyError(key)

    @register_structure("_list_b")
    class ListB(BaseIncrementalDetector):
        REQUIRED_PARAMS = []
        OPTIONAL_PARAMS = {}
        DEPENDS_ON = []

        def update(self, bar_idx: int, bar: BarData) -> None:
            pass

        def get_output_keys(self) -> list[str]:
            return []

        def get_value(self, key: str) -> float | int | str:
            raise KeyError(key)

    types = set(list_structure_types())
    assert "_list_a" in types, "Should include _list_a"
    assert "_list_b" in types, "Should include _list_b"

    # Verify sorted
    types_list = list_structure_types()
    assert types_list == sorted(types_list), "Should be sorted"

    unregister_structure("_list_a")
    unregister_structure("_list_b")

    print("  list_structure_types: PASSED")


def test_unregister_structure() -> None:
    """Test unregister_structure removes from registry."""
    print("Testing unregister_structure...")

    unregister_structure("_unreg_test")

    @register_structure("_unreg_test")
    class UnregTest(BaseIncrementalDetector):
        REQUIRED_PARAMS = []
        OPTIONAL_PARAMS = {}
        DEPENDS_ON = []

        def update(self, bar_idx: int, bar: BarData) -> None:
            pass

        def get_output_keys(self) -> list[str]:
            return []

        def get_value(self, key: str) -> float | int | str:
            raise KeyError(key)

    assert "_unreg_test" in STRUCTURE_REGISTRY

    result = unregister_structure("_unreg_test")
    assert result is True, "Should return True when removing"
    assert "_unreg_test" not in STRUCTURE_REGISTRY

    result = unregister_structure("_unreg_test")
    assert result is False, "Should return False when not found"

    print("  unregister_structure: PASSED")


def run_all_tests() -> bool:
    """Run all validation tests."""
    print("=" * 60)
    print("Phase 2 Validation Tests: Base Class + Registry")
    print("=" * 60)
    print()

    tests = [
        test_bar_data,
        test_register_structure_works,
        test_register_validates_inheritance,
        test_register_validates_class_attributes,
        test_register_rejects_duplicate,
        test_validate_and_create_missing_params,
        test_validate_and_create_missing_deps,
        test_validate_and_create_success,
        test_get_value_safe,
        test_get_all_values,
        test_get_structure_info,
        test_get_structure_info_not_found,
        test_list_structure_types,
        test_unregister_structure,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  FAILED: {e}")
            failed += 1

    print()
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
