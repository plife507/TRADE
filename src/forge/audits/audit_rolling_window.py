"""
Audit tests for IncrementalRollingWindow detector.

Run with:
    python -m src.backtest.audits.audit_rolling_window

These tests validate:
1. Parameter validation (size, field, mode)
2. Correct min/max tracking over window
3. Window eviction behavior
4. All OHLCV fields work correctly
5. Integration with registry and base class
"""

import sys


def test_registration():
    """Test that rolling_window is registered in the structure registry."""
    from src.structures import STRUCTURE_REGISTRY, get_structure_info

    # Import triggers registration
    from src.structures import IncrementalRollingWindow

    assert "rolling_window" in STRUCTURE_REGISTRY, "rolling_window not registered"
    assert STRUCTURE_REGISTRY["rolling_window"] is IncrementalRollingWindow

    # Check metadata
    info = get_structure_info("rolling_window")
    assert info["required_params"] == ["size", "field", "mode"]
    assert info["optional_params"] == {}
    assert info["depends_on"] == []
    assert info["class_name"] == "IncrementalRollingWindow"

    print("[PASS] test_registration")


def test_param_validation_size():
    """Test size parameter validation."""
    from src.structures import IncrementalRollingWindow

    # Valid size
    detector = IncrementalRollingWindow.validate_and_create(
        struct_type="rolling_window",
        key="test",
        params={"size": 10, "field": "low", "mode": "min"},
        deps={},
    )
    assert detector.size == 10

    # Size must be >= 1
    try:
        IncrementalRollingWindow.validate_and_create(
            struct_type="rolling_window",
            key="test",
            params={"size": 0, "field": "low", "mode": "min"},
            deps={},
        )
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "size" in str(e)
        assert "integer >= 1" in str(e)

    # Size must be integer
    try:
        IncrementalRollingWindow.validate_and_create(
            struct_type="rolling_window",
            key="test",
            params={"size": 10.5, "field": "low", "mode": "min"},
            deps={},
        )
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "size" in str(e)
        assert "integer" in str(e)

    print("[PASS] test_param_validation_size")


def test_param_validation_field():
    """Test field parameter validation."""
    from src.structures import IncrementalRollingWindow

    # Valid fields
    for field in ["open", "high", "low", "close", "volume"]:
        detector = IncrementalRollingWindow.validate_and_create(
            struct_type="rolling_window",
            key="test",
            params={"size": 10, "field": field, "mode": "min"},
            deps={},
        )
        assert detector.field == field

    # Invalid field
    try:
        IncrementalRollingWindow.validate_and_create(
            struct_type="rolling_window",
            key="test",
            params={"size": 10, "field": "invalid", "mode": "min"},
            deps={},
        )
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "field" in str(e)
        assert "invalid" in str(e)

    print("[PASS] test_param_validation_field")


def test_param_validation_mode():
    """Test mode parameter validation."""
    from src.structures import IncrementalRollingWindow

    # Valid modes
    for mode in ["min", "max"]:
        detector = IncrementalRollingWindow.validate_and_create(
            struct_type="rolling_window",
            key="test",
            params={"size": 10, "field": "low", "mode": mode},
            deps={},
        )
        assert detector.mode == mode

    # Invalid mode
    try:
        IncrementalRollingWindow.validate_and_create(
            struct_type="rolling_window",
            key="test",
            params={"size": 10, "field": "low", "mode": "average"},
            deps={},
        )
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "mode" in str(e)
        assert "'min' or 'max'" in str(e)

    print("[PASS] test_param_validation_mode")


def test_missing_params():
    """Test error when required params are missing."""
    from src.structures import IncrementalRollingWindow

    # Missing size
    try:
        IncrementalRollingWindow.validate_and_create(
            struct_type="rolling_window",
            key="test",
            params={"field": "low", "mode": "min"},
            deps={},
        )
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "missing required params" in str(e)
        assert "size" in str(e)

    # Missing all params
    try:
        IncrementalRollingWindow.validate_and_create(
            struct_type="rolling_window",
            key="test",
            params={},
            deps={},
        )
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "missing required params" in str(e)

    print("[PASS] test_missing_params")


def test_rolling_min():
    """Test rolling minimum calculation."""
    from src.structures import BarData
    from src.structures import IncrementalRollingWindow

    detector = IncrementalRollingWindow.validate_and_create(
        struct_type="rolling_window",
        key="low_3",
        params={"size": 3, "field": "low", "mode": "min"},
        deps={},
    )

    # Helper to create bar data
    def make_bar(idx: int, low: float) -> BarData:
        return BarData(
            idx=idx,
            open=100.0,
            high=100.0,
            low=low,
            close=100.0,
            volume=1000.0,
            indicators={},
        )

    # Push some bars
    detector.update(0, make_bar(0, 50.0))
    assert detector.get_value("value") == 50.0, "First bar, min should be 50"

    detector.update(1, make_bar(1, 45.0))
    assert detector.get_value("value") == 45.0, "Second bar, min should be 45"

    detector.update(2, make_bar(2, 48.0))
    assert detector.get_value("value") == 45.0, "Third bar, min should still be 45"

    detector.update(3, make_bar(3, 47.0))
    # Window now [45, 48, 47] -> [48, 47] after 45 evicted -> wait, idx 1 evicted
    # Window = [idx 1, 2, 3] = [45, 48, 47] - but size=3, so idx 0 evicted
    # Actually: idx=3 means window covers [1, 2, 3] since 0 <= 3 - 3
    # So values are [45, 48, 47], min = 45
    assert detector.get_value("value") == 45.0, "Fourth bar, window [45,48,47], min=45"

    detector.update(4, make_bar(4, 49.0))
    # Window covers [2, 3, 4] = [48, 47, 49], min = 47
    assert detector.get_value("value") == 47.0, "Fifth bar, window [48,47,49], min=47"

    print("[PASS] test_rolling_min")


def test_rolling_max():
    """Test rolling maximum calculation."""
    from src.structures import BarData
    from src.structures import IncrementalRollingWindow

    detector = IncrementalRollingWindow.validate_and_create(
        struct_type="rolling_window",
        key="high_3",
        params={"size": 3, "field": "high", "mode": "max"},
        deps={},
    )

    def make_bar(idx: int, high: float) -> BarData:
        return BarData(
            idx=idx,
            open=100.0,
            high=high,
            low=100.0,
            close=100.0,
            volume=1000.0,
            indicators={},
        )

    detector.update(0, make_bar(0, 100.0))
    assert detector.get_value("value") == 100.0

    detector.update(1, make_bar(1, 105.0))
    assert detector.get_value("value") == 105.0

    detector.update(2, make_bar(2, 103.0))
    assert detector.get_value("value") == 105.0

    detector.update(3, make_bar(3, 102.0))
    # Window [1,2,3] = [105, 103, 102], max = 105
    assert detector.get_value("value") == 105.0

    detector.update(4, make_bar(4, 101.0))
    # Window [2,3,4] = [103, 102, 101], max = 103
    assert detector.get_value("value") == 103.0

    print("[PASS] test_rolling_max")


def test_output_keys():
    """Test get_output_keys returns correct keys."""
    from src.structures import IncrementalRollingWindow

    detector = IncrementalRollingWindow.validate_and_create(
        struct_type="rolling_window",
        key="test",
        params={"size": 10, "field": "low", "mode": "min"},
        deps={},
    )

    assert detector.get_output_keys() == ["value"]

    print("[PASS] test_output_keys")


def test_get_value_safe():
    """Test get_value_safe validates key and provides helpful errors."""
    from src.structures import IncrementalRollingWindow

    detector = IncrementalRollingWindow.validate_and_create(
        struct_type="rolling_window",
        key="test_key",
        params={"size": 10, "field": "low", "mode": "min"},
        deps={},
    )

    # Valid key works
    result = detector.get_value_safe("value")
    assert result is None  # Empty window

    # Invalid key gives helpful error
    try:
        detector.get_value_safe("invalid_key")
        assert False, "Should have raised KeyError"
    except KeyError as e:
        error_msg = str(e)
        assert "test_key" in error_msg
        assert "invalid_key" in error_msg
        assert "value" in error_msg  # Shows available keys

    print("[PASS] test_get_value_safe")


def test_all_fields():
    """Test that all OHLCV fields can be tracked."""
    from src.structures import BarData
    from src.structures import IncrementalRollingWindow

    bar = BarData(
        idx=0,
        open=100.0,
        high=105.0,
        low=95.0,
        close=102.0,
        volume=1234.0,
        indicators={},
    )

    for field, expected in [
        ("open", 100.0),
        ("high", 105.0),
        ("low", 95.0),
        ("close", 102.0),
        ("volume", 1234.0),
    ]:
        detector = IncrementalRollingWindow.validate_and_create(
            struct_type="rolling_window",
            key=f"test_{field}",
            params={"size": 5, "field": field, "mode": "min"},
            deps={},
        )
        detector.update(0, bar)
        assert detector.get_value("value") == expected, f"Field {field} mismatch"

    print("[PASS] test_all_fields")


def test_repr():
    """Test string representation."""
    from src.structures import IncrementalRollingWindow

    detector = IncrementalRollingWindow.validate_and_create(
        struct_type="rolling_window",
        key="test",
        params={"size": 20, "field": "low", "mode": "min"},
        deps={},
    )

    repr_str = repr(detector)
    assert "IncrementalRollingWindow" in repr_str
    assert "size=20" in repr_str
    assert "field='low'" in repr_str
    assert "mode='min'" in repr_str

    print("[PASS] test_repr")


def run_all_tests():
    """Run all tests and report results."""
    print("=" * 60)
    print("IncrementalRollingWindow Tests")
    print("=" * 60)

    tests = [
        test_registration,
        test_param_validation_size,
        test_param_validation_field,
        test_param_validation_mode,
        test_missing_params,
        test_rolling_min,
        test_rolling_max,
        test_output_keys,
        test_get_value_safe,
        test_all_fields,
        test_repr,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"[FAIL] {test.__name__}: {e}")
            failed += 1

    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
