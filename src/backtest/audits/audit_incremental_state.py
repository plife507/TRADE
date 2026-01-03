"""
Audit tests for TFIncrementalState and MultiTFIncrementalState.

Run with:
    python -c "from src.backtest.audits.audit_incremental_state import run_all_tests; run_all_tests()"

Or run specific tests:
    python -c "from src.backtest.audits.audit_incremental_state import test_tf_state_basic; test_tf_state_basic()"
"""

from __future__ import annotations

import math


def test_tf_state_basic() -> None:
    """Test basic TFIncrementalState creation and updates."""
    from ..incremental.base import BarData
    from ..incremental.state import TFIncrementalState

    print("Testing TFIncrementalState basic operations...")
    print("-" * 60)

    # Create state with swing detector only
    specs = [
        {"type": "swing", "key": "swing", "params": {"left": 2, "right": 2}},
    ]

    state = TFIncrementalState("15m", specs)

    # Verify structure was created
    assert "swing" in state.structures, "Swing structure should be created"
    assert state.timeframe == "15m", "Timeframe should be '15m'"

    # Create sample bars
    bars = [
        BarData(idx=0, open=100.0, high=102.0, low=99.0, close=101.0, volume=100.0, indicators={}),
        BarData(idx=1, open=101.0, high=105.0, low=100.0, close=104.0, volume=100.0, indicators={}),
        BarData(idx=2, open=104.0, high=110.0, low=103.0, close=108.0, volume=100.0, indicators={}),  # Potential swing high
        BarData(idx=3, open=108.0, high=107.0, low=102.0, close=103.0, volume=100.0, indicators={}),
        BarData(idx=4, open=103.0, high=104.0, low=95.0, close=96.0, volume=100.0, indicators={}),   # Confirms bar 2 as swing high
    ]

    # Update with each bar
    for bar in bars:
        state.update(bar)

    # After bar 4, bar 2 should be confirmed as swing high (high=110)
    high_level = state.get_value("swing", "high_level")
    high_idx = state.get_value("swing", "high_idx")

    print(f"Swing high level: {high_level} at idx {high_idx}")

    assert high_level == 110.0, f"Expected swing high of 110.0, got {high_level}"
    assert high_idx == 2, f"Expected swing high at idx 2, got {high_idx}"

    print("TFIncrementalState basic test PASSED")
    print()


def test_tf_state_dependency_chain() -> None:
    """Test TFIncrementalState with swing -> fib -> trend dependency chain."""
    from ..incremental.base import BarData
    from .state import TFIncrementalState

    print("Testing TFIncrementalState with dependency chain...")
    print("-" * 60)

    # Create state with swing -> fib + trend chain
    specs = [
        {"type": "swing", "key": "swing", "params": {"left": 2, "right": 2}},
        {
            "type": "fibonacci",
            "key": "fib",
            "depends_on": {"swing": "swing"},
            "params": {"levels": [0.382, 0.5, 0.618], "mode": "retracement"},
        },
        {
            "type": "trend",
            "key": "trend",
            "depends_on": {"swing": "swing"},
        },
    ]

    state = TFIncrementalState("15m", specs)

    # Verify all structures created
    assert "swing" in state.structures
    assert "fib" in state.structures
    assert "trend" in state.structures

    # Verify update order (dependencies must come first)
    assert state._update_order == ["swing", "fib", "trend"]

    # Create bars that establish swing high and swing low
    # Pattern: rise to high, fall to low
    bars = [
        BarData(idx=0, open=100.0, high=102.0, low=99.0, close=101.0, volume=100.0, indicators={}),
        BarData(idx=1, open=101.0, high=104.0, low=100.0, close=103.0, volume=100.0, indicators={}),
        BarData(idx=2, open=103.0, high=110.0, low=102.0, close=108.0, volume=100.0, indicators={}),  # Swing high = 110
        BarData(idx=3, open=108.0, high=106.0, low=101.0, close=102.0, volume=100.0, indicators={}),
        BarData(idx=4, open=102.0, high=103.0, low=95.0, close=96.0, volume=100.0, indicators={}),   # Confirms swing high
        BarData(idx=5, open=96.0, high=97.0, low=90.0, close=91.0, volume=100.0, indicators={}),     # Swing low = 90
        BarData(idx=6, open=91.0, high=93.0, low=89.0, close=92.0, volume=100.0, indicators={}),
        BarData(idx=7, open=92.0, high=95.0, low=91.0, close=94.0, volume=100.0, indicators={}),     # Confirms swing low
    ]

    for bar in bars:
        state.update(bar)

    # Check swing values
    high_level = state.get_value("swing", "high_level")
    low_level = state.get_value("swing", "low_level")
    print(f"Swing: high={high_level}, low={low_level}")

    # Check Fibonacci levels
    fib_382 = state.get_value("fib", "level_0.382")
    fib_500 = state.get_value("fib", "level_0.5")
    fib_618 = state.get_value("fib", "level_0.618")

    # Expected: range = 110 - 90 = 20
    # 0.382 retracement: 110 - (20 * 0.382) = 110 - 7.64 = 102.36
    # 0.5 retracement: 110 - (20 * 0.5) = 100
    # 0.618 retracement: 110 - (20 * 0.618) = 110 - 12.36 = 97.64

    if not math.isnan(high_level) and not math.isnan(low_level):
        expected_range = high_level - low_level
        expected_382 = high_level - (expected_range * 0.382)
        expected_500 = high_level - (expected_range * 0.5)
        expected_618 = high_level - (expected_range * 0.618)

        print(f"Fibonacci 0.382: {fib_382} (expected {expected_382})")
        print(f"Fibonacci 0.5: {fib_500} (expected {expected_500})")
        print(f"Fibonacci 0.618: {fib_618} (expected {expected_618})")

        # Allow small floating-point tolerance
        assert abs(fib_382 - expected_382) < 0.001, f"Fib 0.382 mismatch"
        assert abs(fib_500 - expected_500) < 0.001, f"Fib 0.5 mismatch"
        assert abs(fib_618 - expected_618) < 0.001, f"Fib 0.618 mismatch"

    # Check trend direction
    trend_dir = state.get_value("trend", "direction")
    print(f"Trend direction: {trend_dir}")

    print("TFIncrementalState dependency chain test PASSED")
    print()


def test_multi_tf_state_basic() -> None:
    """Test basic MultiTFIncrementalState creation and path access."""
    from ..incremental.base import BarData
    from .state import MultiTFIncrementalState

    print("Testing MultiTFIncrementalState basic operations...")
    print("-" * 60)

    # Create multi-TF state with exec and one HTF
    exec_specs = [
        {"type": "swing", "key": "swing", "params": {"left": 2, "right": 2}},
        {"type": "trend", "key": "trend", "depends_on": {"swing": "swing"}},
    ]

    htf_configs = {
        "1h": [
            {"type": "swing", "key": "swing_1h", "params": {"left": 3, "right": 3}},
            {"type": "trend", "key": "trend_1h", "depends_on": {"swing": "swing_1h"}},
        ],
    }

    multi = MultiTFIncrementalState("15m", exec_specs, htf_configs)

    # Verify structure
    assert multi.exec_tf == "15m"
    assert "swing" in multi.exec.structures
    assert "trend" in multi.exec.structures
    assert "1h" in multi.htf
    assert "swing_1h" in multi.htf["1h"].structures
    assert "trend_1h" in multi.htf["1h"].structures

    print(f"Multi-TF state: {multi}")
    print(f"All paths: {multi.list_all_paths()}")

    # Create sample bars for exec TF
    exec_bars = [
        BarData(idx=0, open=100.0, high=102.0, low=99.0, close=101.0, volume=100.0, indicators={}),
        BarData(idx=1, open=101.0, high=105.0, low=100.0, close=104.0, volume=100.0, indicators={}),
        BarData(idx=2, open=104.0, high=110.0, low=103.0, close=108.0, volume=100.0, indicators={}),
        BarData(idx=3, open=108.0, high=107.0, low=102.0, close=103.0, volume=100.0, indicators={}),
        BarData(idx=4, open=103.0, high=104.0, low=95.0, close=96.0, volume=100.0, indicators={}),
    ]

    # Create sample bars for 1h TF
    htf_bars = [
        BarData(idx=0, open=100.0, high=110.0, low=95.0, close=105.0, volume=400.0, indicators={}),
    ]

    # Update exec TF
    for bar in exec_bars:
        multi.update_exec(bar)

    # Update HTF
    for bar in htf_bars:
        multi.update_htf("1h", bar)

    # Access via paths
    exec_high = multi.get_value("exec.swing.high_level")
    exec_dir = multi.get_value("exec.trend.direction")

    print(f"Exec swing high: {exec_high}")
    print(f"Exec trend direction: {exec_dir}")

    # Note: 1h swing won't be confirmed yet with just 1 bar
    htf_high = multi.get_value("htf_1h.swing_1h.high_level")
    print(f"HTF 1h swing high: {htf_high} (NaN expected with insufficient bars)")

    print("MultiTFIncrementalState basic test PASSED")
    print()


def test_multi_tf_full_chain() -> None:
    """Test MultiTFIncrementalState with full swing + fib + trend chain."""
    from ..incremental.base import BarData
    from .state import MultiTFIncrementalState

    print("Testing MultiTFIncrementalState with full dependency chain...")
    print("-" * 60)

    # Create exec specs with full chain
    exec_specs = [
        {"type": "swing", "key": "swing", "params": {"left": 2, "right": 2}},
        {
            "type": "fibonacci",
            "key": "fib",
            "depends_on": {"swing": "swing"},
            "params": {"levels": [0.382, 0.618], "mode": "retracement"},
        },
        {"type": "trend", "key": "trend", "depends_on": {"swing": "swing"}},
    ]

    # Create 1h HTF with same chain
    htf_configs = {
        "1h": [
            {"type": "swing", "key": "swing", "params": {"left": 2, "right": 2}},
            {
                "type": "fibonacci",
                "key": "fib",
                "depends_on": {"swing": "swing"},
                "params": {"levels": [0.5], "mode": "retracement"},
            },
            {"type": "trend", "key": "trend", "depends_on": {"swing": "swing"}},
        ],
    }

    multi = MultiTFIncrementalState("15m", exec_specs, htf_configs)

    print(f"Created: {multi}")
    print(f"All paths ({len(multi.list_all_paths())}): {multi.list_all_paths()}")

    # Build bars for both timeframes
    # For swing detection with left=2, right=2:
    # - Need 5 bars in window (left + pivot + right)
    # - Swing is confirmed at bar (pivot_bar + right)
    # - For swing high: pivot bar's high must be > all neighbors
    # - For swing low: pivot bar's low must be < all neighbors

    # Exec TF bars (15m): clear swing high at bar 2 (confirmed at bar 4), swing low at bar 6 (confirmed at bar 8)
    # Bar sequence:
    # idx 0: high=102, low=99
    # idx 1: high=105, low=100
    # idx 2: high=115, low=103  <-- SWING HIGH (115 > 102, 105, 107, 103)
    # idx 3: high=107, low=96
    # idx 4: high=103, low=95   <-- Confirms swing high at bar 2
    # idx 5: high=98, low=93
    # idx 6: high=95, low=88    <-- SWING LOW (88 < 95, 93, 92, 91)
    # idx 7: high=97, low=92
    # idx 8: high=100, low=91   <-- Confirms swing low at bar 6
    exec_bars = [
        BarData(idx=0, open=100.0, high=102.0, low=99.0, close=101.0, volume=100.0, indicators={}),
        BarData(idx=1, open=101.0, high=105.0, low=100.0, close=104.0, volume=100.0, indicators={}),
        BarData(idx=2, open=104.0, high=115.0, low=103.0, close=112.0, volume=100.0, indicators={}),  # Swing high=115
        BarData(idx=3, open=112.0, high=107.0, low=96.0, close=98.0, volume=100.0, indicators={}),
        BarData(idx=4, open=98.0, high=103.0, low=95.0, close=96.0, volume=100.0, indicators={}),     # Confirms high
        BarData(idx=5, open=96.0, high=98.0, low=93.0, close=94.0, volume=100.0, indicators={}),
        BarData(idx=6, open=94.0, high=95.0, low=88.0, close=90.0, volume=100.0, indicators={}),      # Swing low=88
        BarData(idx=7, open=90.0, high=97.0, low=92.0, close=95.0, volume=100.0, indicators={}),
        BarData(idx=8, open=95.0, high=100.0, low=91.0, close=98.0, volume=100.0, indicators={}),     # Confirms low
    ]

    # HTF bars (1h): same pattern
    htf_bars = [
        BarData(idx=0, open=100.0, high=102.0, low=99.0, close=101.0, volume=400.0, indicators={}),
        BarData(idx=1, open=101.0, high=105.0, low=100.0, close=104.0, volume=400.0, indicators={}),
        BarData(idx=2, open=104.0, high=115.0, low=103.0, close=112.0, volume=400.0, indicators={}),  # Swing high=115
        BarData(idx=3, open=112.0, high=107.0, low=96.0, close=98.0, volume=400.0, indicators={}),
        BarData(idx=4, open=98.0, high=103.0, low=95.0, close=96.0, volume=400.0, indicators={}),     # Confirms high
        BarData(idx=5, open=96.0, high=98.0, low=93.0, close=94.0, volume=400.0, indicators={}),
        BarData(idx=6, open=94.0, high=95.0, low=88.0, close=90.0, volume=400.0, indicators={}),      # Swing low=88
        BarData(idx=7, open=90.0, high=97.0, low=92.0, close=95.0, volume=400.0, indicators={}),
        BarData(idx=8, open=95.0, high=100.0, low=91.0, close=98.0, volume=400.0, indicators={}),     # Confirms low
    ]

    # Update both TFs
    for bar in exec_bars:
        multi.update_exec(bar)

    for bar in htf_bars:
        multi.update_htf("1h", bar)

    # Read values via path API
    print("\n--- Reading values via get_value(path) ---")

    exec_swing_high = multi.get_value("exec.swing.high_level")
    exec_swing_low = multi.get_value("exec.swing.low_level")
    exec_fib_382 = multi.get_value("exec.fib.level_0.382")
    exec_fib_618 = multi.get_value("exec.fib.level_0.618")
    exec_trend = multi.get_value("exec.trend.direction")

    print(f"Exec swing high: {exec_swing_high}")
    print(f"Exec swing low: {exec_swing_low}")
    print(f"Exec fib 0.382: {exec_fib_382}")
    print(f"Exec fib 0.618: {exec_fib_618}")
    print(f"Exec trend: {exec_trend}")

    htf_swing_high = multi.get_value("htf_1h.swing.high_level")
    htf_swing_low = multi.get_value("htf_1h.swing.low_level")
    htf_fib_50 = multi.get_value("htf_1h.fib.level_0.5")
    htf_trend = multi.get_value("htf_1h.trend.direction")

    print(f"HTF 1h swing high: {htf_swing_high}")
    print(f"HTF 1h swing low: {htf_swing_low}")
    print(f"HTF 1h fib 0.5: {htf_fib_50}")
    print(f"HTF 1h trend: {htf_trend}")

    # Verify exec values
    assert exec_swing_high == 115.0, f"Expected exec swing high 115.0, got {exec_swing_high}"
    assert exec_swing_low == 88.0, f"Expected exec swing low 88.0, got {exec_swing_low}"

    # Verify exec fib levels
    if not math.isnan(exec_swing_high) and not math.isnan(exec_swing_low):
        range_val = exec_swing_high - exec_swing_low  # 115 - 88 = 27
        expected_382 = exec_swing_high - (range_val * 0.382)  # 115 - 10.314 = 104.686
        expected_618 = exec_swing_high - (range_val * 0.618)  # 115 - 16.686 = 98.314

        print(f"Expected fib 0.382: {expected_382}")
        print(f"Expected fib 0.618: {expected_618}")

        assert abs(exec_fib_382 - expected_382) < 0.001, f"Exec fib 0.382 mismatch: got {exec_fib_382}"
        assert abs(exec_fib_618 - expected_618) < 0.001, f"Exec fib 0.618 mismatch: got {exec_fib_618}"

    # Verify HTF values
    assert htf_swing_high == 115.0, f"Expected HTF swing high 115.0, got {htf_swing_high}"
    assert htf_swing_low == 88.0, f"Expected HTF swing low 88.0, got {htf_swing_low}"

    print("\nMultiTFIncrementalState full chain test PASSED")
    print()


def test_error_handling() -> None:
    """Test fail-loud error handling with actionable suggestions."""
    from ..incremental.base import BarData
    from .state import MultiTFIncrementalState, TFIncrementalState

    print("Testing error handling...")
    print("-" * 60)

    # Test 1: Invalid structure type
    print("Test 1: Invalid structure type...")
    try:
        TFIncrementalState("15m", [{"type": "invalid_type", "key": "test", "params": {}}])
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Unknown structure type" in str(e)
        assert "Available types" in str(e)
        print(f"  OK: Raised ValueError with suggestions")

    # Test 2: Missing dependency
    print("Test 2: Missing dependency...")
    try:
        TFIncrementalState("15m", [
            {"type": "trend", "key": "trend", "depends_on": {"swing": "swing"}}
        ])
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "not yet defined" in str(e)
        assert "Fix:" in str(e)
        print(f"  OK: Raised ValueError with fix suggestion")

    # Test 3: Duplicate key
    print("Test 3: Duplicate structure key...")
    try:
        TFIncrementalState("15m", [
            {"type": "swing", "key": "swing", "params": {"left": 2, "right": 2}},
            {"type": "swing", "key": "swing", "params": {"left": 3, "right": 3}},
        ])
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Duplicate structure key" in str(e)
        print(f"  OK: Raised ValueError for duplicate key")

    # Test 4: Invalid path in get_value
    print("Test 4: Invalid path format...")
    multi = MultiTFIncrementalState(
        "15m",
        [{"type": "swing", "key": "swing", "params": {"left": 2, "right": 2}}],
        {},
    )

    try:
        multi.get_value("invalid.path")  # Only 2 parts
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "at least 3 parts" in str(e)
        print(f"  OK: Raised ValueError for short path")

    # Test 5: Invalid tf_role
    print("Test 5: Invalid tf_role in path...")
    try:
        multi.get_value("unknown.swing.high_level")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Invalid tf_role" in str(e)
        assert "exec" in str(e) or "htf_" in str(e)
        print(f"  OK: Raised ValueError with valid prefixes")

    # Test 6: Unknown structure key
    print("Test 6: Unknown structure key...")
    try:
        multi.get_value("exec.unknown_struct.value")
        assert False, "Should have raised KeyError"
    except KeyError as e:
        assert "not defined" in str(e)
        print(f"  OK: Raised KeyError with available structures")

    # Test 7: Unknown output key
    print("Test 7: Unknown output key...")
    try:
        multi.get_value("exec.swing.unknown_output")
        assert False, "Should have raised KeyError"
    except KeyError as e:
        assert "has no output" in str(e)
        assert "Available outputs" in str(e)
        print(f"  OK: Raised KeyError with available outputs")

    # Test 8: Unknown HTF
    print("Test 8: Unknown HTF in update_htf...")
    try:
        multi.update_htf("4h", BarData(idx=0, open=100.0, high=102.0, low=99.0, close=101.0, volume=100.0, indicators={}))
        assert False, "Should have raised KeyError"
    except KeyError as e:
        assert "not configured" in str(e)
        print(f"  OK: Raised KeyError for unknown HTF")

    # Test 9: Non-monotonic bar index
    print("Test 9: Non-monotonic bar index...")
    state = TFIncrementalState("15m", [{"type": "swing", "key": "swing", "params": {"left": 2, "right": 2}}])
    state.update(BarData(idx=0, open=100.0, high=102.0, low=99.0, close=101.0, volume=100.0, indicators={}))
    state.update(BarData(idx=1, open=101.0, high=103.0, low=100.0, close=102.0, volume=100.0, indicators={}))
    try:
        state.update(BarData(idx=1, open=102.0, high=104.0, low=101.0, close=103.0, volume=100.0, indicators={}))  # Same idx
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "monotonically" in str(e)
        print(f"  OK: Raised ValueError for non-monotonic index")

    print("\nError handling tests PASSED")
    print()


def run_all_tests() -> None:
    """Run all Phase 4 state container tests."""
    print("=" * 60)
    print("PHASE 4: TFIncrementalState + MultiTFIncrementalState Tests")
    print("=" * 60)
    print()

    test_tf_state_basic()
    test_tf_state_dependency_chain()
    test_multi_tf_state_basic()
    test_multi_tf_full_chain()
    test_error_handling()

    print("=" * 60)
    print("ALL PHASE 4 TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
