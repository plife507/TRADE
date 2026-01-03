"""
CLI validation tests for incremental state primitives.

Run with: python -m src.backtest.audits.audit_primitives

Tests:
- MonotonicDeque min mode
- MonotonicDeque max mode
- MonotonicDeque window eviction
- RingBuffer push/access
- RingBuffer wrap-around
- RingBuffer is_full

Exit code 0 = all tests pass, 1 = failures.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Callable

from ..incremental.primitives import MonotonicDeque, RingBuffer


@dataclass
class TestResult:
    """Result of a single test."""

    name: str
    passed: bool
    message: str = ""


def run_test(name: str, test_fn: Callable[[], None]) -> TestResult:
    """Run a test function and capture result."""
    try:
        test_fn()
        return TestResult(name=name, passed=True)
    except AssertionError as e:
        return TestResult(name=name, passed=False, message=str(e))
    except Exception as e:
        return TestResult(name=name, passed=False, message=f"Unexpected error: {e}")


# =============================================================================
# MonotonicDeque Tests
# =============================================================================


def test_monotonic_deque_min_mode() -> None:
    """Test MonotonicDeque correctly tracks minimum over window."""
    deque = MonotonicDeque(window_size=3, mode="min")

    # Push values and check min at each step
    deque.push(0, 5.0)
    assert deque.get() == 5.0, f"Expected 5.0, got {deque.get()}"

    deque.push(1, 3.0)
    assert deque.get() == 3.0, f"Expected 3.0, got {deque.get()}"

    deque.push(2, 4.0)
    assert deque.get() == 3.0, f"Expected 3.0, got {deque.get()}"

    # Value 3.0 (idx=1) should be evicted after window_size steps
    deque.push(3, 6.0)
    assert deque.get() == 3.0, f"Expected 3.0 (idx=1 still in window), got {deque.get()}"

    deque.push(4, 7.0)
    # Now window is [4, 6, 7], min is 4.0 (idx=2 evicted)
    assert deque.get() == 4.0, f"Expected 4.0, got {deque.get()}"


def test_monotonic_deque_max_mode() -> None:
    """Test MonotonicDeque correctly tracks maximum over window."""
    deque = MonotonicDeque(window_size=3, mode="max")

    deque.push(0, 5.0)
    assert deque.get() == 5.0, f"Expected 5.0, got {deque.get()}"

    deque.push(1, 7.0)
    assert deque.get() == 7.0, f"Expected 7.0, got {deque.get()}"

    deque.push(2, 6.0)
    assert deque.get() == 7.0, f"Expected 7.0, got {deque.get()}"

    # Value 7.0 (idx=1) should be evicted after window_size steps
    deque.push(3, 4.0)
    assert deque.get() == 7.0, f"Expected 7.0 (idx=1 still in window), got {deque.get()}"

    deque.push(4, 3.0)
    # Now window is [6, 4, 3], max is 6.0 (idx=1 evicted)
    assert deque.get() == 6.0, f"Expected 6.0, got {deque.get()}"


def test_monotonic_deque_window_eviction() -> None:
    """Test MonotonicDeque properly evicts old values outside window."""
    deque = MonotonicDeque(window_size=2, mode="min")

    deque.push(0, 1.0)  # window: [1]
    deque.push(1, 2.0)  # window: [1, 2]
    assert deque.get() == 1.0, f"Expected 1.0, got {deque.get()}"

    deque.push(2, 3.0)  # window: [2, 3], 1.0 evicted
    assert deque.get() == 2.0, f"Expected 2.0 (1.0 evicted), got {deque.get()}"

    deque.push(3, 1.5)  # window: [1.5], 2.0 and 3.0 evicted by monotonic
    assert deque.get() == 1.5, f"Expected 1.5, got {deque.get()}"


def test_monotonic_deque_empty() -> None:
    """Test MonotonicDeque returns None when empty."""
    deque = MonotonicDeque(window_size=3, mode="min")
    assert deque.get() is None, f"Expected None for empty deque, got {deque.get()}"


def test_monotonic_deque_invalid_params() -> None:
    """Test MonotonicDeque raises on invalid parameters."""
    try:
        MonotonicDeque(window_size=0, mode="min")
        raise AssertionError("Expected ValueError for window_size=0")
    except ValueError:
        pass

    try:
        MonotonicDeque(window_size=3, mode="invalid")  # type: ignore
        raise AssertionError("Expected ValueError for invalid mode")
    except ValueError:
        pass


def test_monotonic_deque_single_element_window() -> None:
    """Test MonotonicDeque with window_size=1."""
    deque = MonotonicDeque(window_size=1, mode="min")

    deque.push(0, 5.0)
    assert deque.get() == 5.0

    deque.push(1, 3.0)  # 5.0 evicted immediately
    assert deque.get() == 3.0

    deque.push(2, 7.0)  # 3.0 evicted immediately
    assert deque.get() == 7.0


# =============================================================================
# RingBuffer Tests
# =============================================================================


def test_ring_buffer_push_access() -> None:
    """Test RingBuffer basic push and access (FIFO order)."""
    buf = RingBuffer(size=3)

    buf.push(1.0)
    assert len(buf) == 1
    assert buf[0] == 1.0

    buf.push(2.0)
    assert len(buf) == 2
    assert buf[0] == 1.0
    assert buf[1] == 2.0

    buf.push(3.0)
    assert len(buf) == 3
    assert buf[0] == 1.0
    assert buf[1] == 2.0
    assert buf[2] == 3.0


def test_ring_buffer_wrap_around() -> None:
    """Test RingBuffer correctly wraps around when full."""
    buf = RingBuffer(size=3)

    buf.push(1.0)
    buf.push(2.0)
    buf.push(3.0)
    assert buf.is_full()

    # Push 4.0, should overwrite 1.0
    buf.push(4.0)
    assert len(buf) == 3
    assert buf[0] == 2.0, f"Expected 2.0 (oldest after wrap), got {buf[0]}"
    assert buf[1] == 3.0, f"Expected 3.0, got {buf[1]}"
    assert buf[2] == 4.0, f"Expected 4.0 (newest), got {buf[2]}"

    # Push 5.0, should overwrite 2.0
    buf.push(5.0)
    assert buf[0] == 3.0
    assert buf[1] == 4.0
    assert buf[2] == 5.0


def test_ring_buffer_is_full() -> None:
    """Test RingBuffer is_full accurately tracks capacity."""
    buf = RingBuffer(size=3)

    assert not buf.is_full()
    assert len(buf) == 0

    buf.push(1.0)
    assert not buf.is_full()
    assert len(buf) == 1

    buf.push(2.0)
    assert not buf.is_full()
    assert len(buf) == 2

    buf.push(3.0)
    assert buf.is_full()
    assert len(buf) == 3

    # After wrap, still full
    buf.push(4.0)
    assert buf.is_full()
    assert len(buf) == 3


def test_ring_buffer_index_error() -> None:
    """Test RingBuffer raises IndexError for out-of-range access."""
    buf = RingBuffer(size=3)
    buf.push(1.0)
    buf.push(2.0)

    # Valid: 0 and 1
    _ = buf[0]
    _ = buf[1]

    # Invalid: 2 (not yet pushed)
    try:
        _ = buf[2]
        raise AssertionError("Expected IndexError for index 2")
    except IndexError:
        pass

    # Invalid: negative
    try:
        _ = buf[-1]
        raise AssertionError("Expected IndexError for negative index")
    except IndexError:
        pass


def test_ring_buffer_invalid_size() -> None:
    """Test RingBuffer raises on invalid size."""
    try:
        RingBuffer(size=0)
        raise AssertionError("Expected ValueError for size=0")
    except ValueError:
        pass

    try:
        RingBuffer(size=-1)
        raise AssertionError("Expected ValueError for size=-1")
    except ValueError:
        pass


def test_ring_buffer_to_array() -> None:
    """Test RingBuffer to_array returns correct order."""
    buf = RingBuffer(size=3)

    buf.push(1.0)
    buf.push(2.0)
    arr = buf.to_array()
    assert list(arr) == [1.0, 2.0]

    buf.push(3.0)
    buf.push(4.0)  # Wraps, now [2, 3, 4]
    arr = buf.to_array()
    assert list(arr) == [2.0, 3.0, 4.0]


def test_ring_buffer_clear() -> None:
    """Test RingBuffer clear resets state."""
    buf = RingBuffer(size=3)
    buf.push(1.0)
    buf.push(2.0)
    buf.push(3.0)

    assert buf.is_full()
    buf.clear()

    assert len(buf) == 0
    assert not buf.is_full()
    assert buf.to_array().tolist() == []


# =============================================================================
# Test Runner
# =============================================================================


def run_all_tests() -> list[TestResult]:
    """Run all primitive tests and return results."""
    tests = [
        # MonotonicDeque tests
        ("MonotonicDeque min mode", test_monotonic_deque_min_mode),
        ("MonotonicDeque max mode", test_monotonic_deque_max_mode),
        ("MonotonicDeque window eviction", test_monotonic_deque_window_eviction),
        ("MonotonicDeque empty", test_monotonic_deque_empty),
        ("MonotonicDeque invalid params", test_monotonic_deque_invalid_params),
        ("MonotonicDeque single element window", test_monotonic_deque_single_element_window),
        # RingBuffer tests
        ("RingBuffer push/access", test_ring_buffer_push_access),
        ("RingBuffer wrap-around", test_ring_buffer_wrap_around),
        ("RingBuffer is_full", test_ring_buffer_is_full),
        ("RingBuffer index error", test_ring_buffer_index_error),
        ("RingBuffer invalid size", test_ring_buffer_invalid_size),
        ("RingBuffer to_array", test_ring_buffer_to_array),
        ("RingBuffer clear", test_ring_buffer_clear),
    ]

    results = []
    for name, test_fn in tests:
        result = run_test(name, test_fn)
        results.append(result)

    return results


def print_results(results: list[TestResult]) -> int:
    """Print test results and return exit code."""
    print("\n" + "=" * 60)
    print("Incremental Primitives Test Suite")
    print("=" * 60 + "\n")

    passed = 0
    failed = 0

    for result in results:
        status = "[PASS]" if result.passed else "[FAIL]"
        print(f"  {status} {result.name}")
        if not result.passed and result.message:
            print(f"         {result.message}")
        if result.passed:
            passed += 1
        else:
            failed += 1

    print("\n" + "-" * 60)
    print(f"Results: {passed} passed, {failed} failed, {len(results)} total")
    print("-" * 60 + "\n")

    return 0 if failed == 0 else 1


def main() -> int:
    """Main entry point for CLI validation."""
    results = run_all_tests()
    return print_results(results)


if __name__ == "__main__":
    sys.exit(main())
