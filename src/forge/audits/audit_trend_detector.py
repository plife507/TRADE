"""
Audit tests for IncrementalTrend.

Tests validate:
1. Registration in STRUCTURE_REGISTRY
2. Uptrend detection (HH + HL)
3. Downtrend detection (LH + LL)
4. Ranging detection (mixed signals)
5. bars_in_trend counting and reset
6. Dependency validation

Run: python -m src.backtest.audits.audit_trend_detector
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


def run_tests() -> None:
    """Run all trend detector tests."""
    print("=" * 60)
    print("IncrementalTrend Tests")
    print("=" * 60)

    test_registration()
    test_uptrend_detection()
    test_downtrend_detection()
    test_ranging_detection()
    test_bars_in_trend_tracking()
    test_missing_dependency_error()

    print("=" * 60)
    print("All tests passed!")
    print("=" * 60)


def test_registration() -> None:
    """Test that trend detector is registered."""
    from src.structures import STRUCTURE_REGISTRY, get_structure_info

    assert "trend" in STRUCTURE_REGISTRY, "trend not registered"

    info = get_structure_info("trend")
    assert info["required_params"] == [], f"Expected no required params, got {info['required_params']}"
    assert info["depends_on"] == ["swing"], f"Expected depends_on=['swing'], got {info['depends_on']}"
    assert info["class_name"] == "IncrementalTrend"

    print("[PASS] test_registration")


@dataclass
class MockSwingDetector:
    """Mock swing detector for testing trend detector."""

    high_level: float = float("nan")
    high_idx: int = -1
    low_level: float = float("nan")
    low_idx: int = -1


def create_trend_detector(swing: MockSwingDetector) -> Any:
    """Create a trend detector with mock swing dependency."""
    # G6.1.2: Fix broken relative import
    from src.structures import IncrementalTrend

    params: dict[str, Any] = {}
    deps = {"swing": swing}
    return IncrementalTrend(params, deps)


def test_uptrend_detection() -> None:
    """Test uptrend detection: higher highs + higher lows."""
    from src.structures import BarData

    swing = MockSwingDetector()
    detector = create_trend_detector(swing)

    # Initial state: no trend
    assert detector.direction == 0, "Initial direction should be 0"
    assert detector.bars_in_trend == 0, "Initial bars_in_trend should be 0"

    # Bar 0: First swing high at 100
    swing.high_level = 100.0
    swing.high_idx = 0
    bar = BarData(idx=0, open=98.0, high=100.0, low=97.0, close=99.0, volume=1000.0, indicators={})
    detector.update(0, bar)

    # Still ranging (need both HH and HL)
    assert detector.direction == 0, "Direction should still be 0 after first swing"

    # Bar 1: First swing low at 95
    swing.low_level = 95.0
    swing.low_idx = 1
    bar = BarData(idx=1, open=99.0, high=99.5, low=95.0, close=96.0, volume=1000.0, indicators={})
    detector.update(1, bar)

    # Still ranging (need HH + HL, not just first swings)
    assert detector.direction == 0, "Direction should be 0 after first HL"

    # Bar 10: Higher high at 105
    swing.high_level = 105.0
    swing.high_idx = 10
    bar = BarData(idx=10, open=102.0, high=105.0, low=101.0, close=104.0, volume=1000.0, indicators={})
    detector.update(10, bar)

    # Still ranging (need HL too)
    assert detector.direction == 0, "Direction should be 0 with only HH"

    # Bar 15: Higher low at 98
    swing.low_level = 98.0
    swing.low_idx = 15
    bar = BarData(idx=15, open=102.0, high=103.0, low=98.0, close=100.0, volume=1000.0, indicators={})
    detector.update(15, bar)

    # Now we have HH + HL = uptrend
    assert detector.direction == 1, f"Direction should be 1 (uptrend) after HH+HL, got {detector.direction}"

    print("[PASS] test_uptrend_detection")


def test_downtrend_detection() -> None:
    """Test downtrend detection: lower highs + lower lows."""
    from src.structures import BarData

    swing = MockSwingDetector()
    detector = create_trend_detector(swing)

    # First swing high at 100
    swing.high_level = 100.0
    swing.high_idx = 0
    bar = BarData(idx=0, open=98.0, high=100.0, low=97.0, close=99.0, volume=1000.0, indicators={})
    detector.update(0, bar)

    # First swing low at 95
    swing.low_level = 95.0
    swing.low_idx = 1
    bar = BarData(idx=1, open=99.0, high=99.5, low=95.0, close=96.0, volume=1000.0, indicators={})
    detector.update(1, bar)

    # Lower high at 98 (< 100)
    swing.high_level = 98.0
    swing.high_idx = 10
    bar = BarData(idx=10, open=96.0, high=98.0, low=93.0, close=94.0, volume=1000.0, indicators={})
    detector.update(10, bar)

    # Lower low at 90 (< 95)
    swing.low_level = 90.0
    swing.low_idx = 15
    bar = BarData(idx=15, open=94.0, high=95.0, low=90.0, close=91.0, volume=1000.0, indicators={})
    detector.update(15, bar)

    # Now we have LH + LL = downtrend
    assert detector.direction == -1, f"Direction should be -1 (downtrend) after LH+LL, got {detector.direction}"

    print("[PASS] test_downtrend_detection")


def test_ranging_detection() -> None:
    """Test ranging detection: mixed signals (HH but LL, or LH but HL)."""
    from src.structures import BarData

    swing = MockSwingDetector()
    detector = create_trend_detector(swing)

    # First swing high at 100
    swing.high_level = 100.0
    swing.high_idx = 0
    bar = BarData(idx=0, open=98.0, high=100.0, low=97.0, close=99.0, volume=1000.0, indicators={})
    detector.update(0, bar)

    # First swing low at 95
    swing.low_level = 95.0
    swing.low_idx = 1
    bar = BarData(idx=1, open=99.0, high=99.5, low=95.0, close=96.0, volume=1000.0, indicators={})
    detector.update(1, bar)

    # Higher high at 105
    swing.high_level = 105.0
    swing.high_idx = 10
    bar = BarData(idx=10, open=102.0, high=105.0, low=101.0, close=104.0, volume=1000.0, indicators={})
    detector.update(10, bar)

    # Lower low at 90 (mixed: HH but LL)
    swing.low_level = 90.0
    swing.low_idx = 15
    bar = BarData(idx=15, open=102.0, high=103.0, low=90.0, close=92.0, volume=1000.0, indicators={})
    detector.update(15, bar)

    # Mixed signals = ranging
    assert detector.direction == 0, f"Direction should be 0 (ranging) with HH+LL, got {detector.direction}"

    print("[PASS] test_ranging_detection")


def test_bars_in_trend_tracking() -> None:
    """Test bars_in_trend increments and resets correctly."""
    from src.structures import BarData

    swing = MockSwingDetector()
    detector = create_trend_detector(swing)

    # Initial state
    assert detector.bars_in_trend == 0, "Initial bars_in_trend should be 0"

    # Process a bar with no swing changes
    bar = BarData(idx=0, open=100.0, high=101.0, low=99.0, close=100.5, volume=1000.0, indicators={})
    detector.update(0, bar)
    assert detector.bars_in_trend == 1, "bars_in_trend should be 1 after first bar"

    # Another bar with no swing changes
    bar = BarData(idx=1, open=100.5, high=102.0, low=100.0, close=101.5, volume=1000.0, indicators={})
    detector.update(1, bar)
    assert detector.bars_in_trend == 2, "bars_in_trend should be 2 after second bar"

    # First swing high
    swing.high_level = 105.0
    swing.high_idx = 2
    bar = BarData(idx=2, open=101.5, high=105.0, low=101.0, close=104.0, volume=1000.0, indicators={})
    detector.update(2, bar)
    # Direction is still 0 (ranging), bars_in_trend should be 0 or 1 depending on logic

    # First swing low
    swing.low_level = 98.0
    swing.low_idx = 3
    bar = BarData(idx=3, open=104.0, high=104.5, low=98.0, close=99.0, volume=1000.0, indicators={})
    detector.update(3, bar)

    # Get HH (higher than 105)
    swing.high_level = 110.0
    swing.high_idx = 4
    bar = BarData(idx=4, open=99.0, high=110.0, low=98.5, close=109.0, volume=1000.0, indicators={})
    detector.update(4, bar)

    # Get HL (higher than 98) - this triggers uptrend
    swing.low_level = 102.0
    swing.low_idx = 5
    bar = BarData(idx=5, open=109.0, high=109.5, low=102.0, close=104.0, volume=1000.0, indicators={})
    detector.update(5, bar)

    prev_direction = detector.direction
    prev_bars = detector.bars_in_trend

    # Now get LH + LL to trigger downtrend
    swing.high_level = 108.0  # Lower than 110
    swing.high_idx = 6
    bar = BarData(idx=6, open=104.0, high=108.0, low=103.0, close=105.0, volume=1000.0, indicators={})
    detector.update(6, bar)

    swing.low_level = 100.0  # Lower than 102
    swing.low_idx = 7
    bar = BarData(idx=7, open=105.0, high=106.0, low=100.0, close=101.0, volume=1000.0, indicators={})
    detector.update(7, bar)

    # If direction changed, bars_in_trend should reset to 0
    if detector.direction != prev_direction:
        assert detector.bars_in_trend == 0, f"bars_in_trend should reset to 0 on direction change, got {detector.bars_in_trend}"

    print("[PASS] test_bars_in_trend_tracking")


def test_missing_dependency_error() -> None:
    """Test that missing swing dependency raises proper error."""
    # G6.1.3: Fix broken relative import
    from src.structures import IncrementalTrend

    try:
        # Try to create via validate_and_create without swing dependency
        IncrementalTrend.validate_and_create(
            struct_type="trend",
            key="test_trend",
            params={},
            deps={},  # Missing "swing" dependency
        )
        assert False, "Should have raised ValueError for missing dependency"
    except ValueError as e:
        error_msg = str(e)
        assert "missing dependencies" in error_msg.lower(), f"Error should mention missing dependencies: {error_msg}"
        assert "swing" in error_msg, f"Error should mention 'swing': {error_msg}"

    print("[PASS] test_missing_dependency_error")


if __name__ == "__main__":
    run_tests()
