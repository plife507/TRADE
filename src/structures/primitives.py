"""
Incremental state primitives for O(1) hot-loop operations.

Provides low-level data structures for efficient incremental computation:
- MonotonicDeque: O(1) amortized sliding window min/max
- RingBuffer: Fixed-size circular buffer for swing detection

These primitives are building blocks for the structure detectors
(swing, trend, zone, rolling_window) that power market structure analysis.

Performance Contract:
- MonotonicDeque.push(): O(1) amortized
- MonotonicDeque.get(): O(1)
- RingBuffer.push(): O(1)
- RingBuffer.__getitem__(): O(1)
"""

from __future__ import annotations

from collections import deque
from typing import Literal

import numpy as np


class MonotonicDeque:
    """
    O(1) amortized sliding window min or max.

    Maintains a monotonic invariant so the front element is always
    the min (or max) within the current window.

    Algorithm:
    - MIN mode: deque values increase (front = smallest)
    - MAX mode: deque values decrease (front = largest)

    Each element is pushed at most once and popped at most once,
    giving O(1) amortized cost per push.

    Example:
        >>> deque = MonotonicDeque(window_size=3, mode="min")
        >>> deque.push(0, 5.0)  # window: [5]
        >>> deque.push(1, 3.0)  # window: [3]
        >>> deque.push(2, 4.0)  # window: [3, 4]
        >>> deque.get()
        3.0
        >>> deque.push(3, 2.0)  # window: [2], 3 evicted by window, rest by monotonic
        >>> deque.get()
        2.0

    Attributes:
        window_size: Number of elements in the sliding window.
        mode: "min" for minimum tracking, "max" for maximum tracking.
    """

    __slots__ = ("window_size", "mode", "_deque")

    def __init__(self, window_size: int, mode: Literal["min", "max"]) -> None:
        """
        Initialize monotonic deque.

        Args:
            window_size: Size of the sliding window (must be >= 1).
            mode: "min" to track minimum, "max" to track maximum.

        Raises:
            ValueError: If window_size < 1 or mode is invalid.
        """
        if window_size < 1:
            raise ValueError(
                f"window_size must be >= 1, got {window_size}\n"
                f"\n"
                f"Fix: MonotonicDeque(window_size=20, mode='min')"
            )
        if mode not in ("min", "max"):
            raise ValueError(
                f"mode must be 'min' or 'max', got '{mode}'\n"
                f"\n"
                f"Fix: MonotonicDeque(window_size=20, mode='min')"
            )
        self.window_size = window_size
        self.mode = mode
        self._deque: deque[tuple[int, float]] = deque()

    def push(self, idx: int, value: float) -> None:
        """
        Add a value to the window at the given index.

        The index must be monotonically increasing across calls.
        Elements outside the window are evicted automatically.

        Args:
            idx: Bar index (must increase with each call).
            value: Value to add to the window.
        """
        # Evict entries outside window (by index)
        while self._deque and self._deque[0][0] <= idx - self.window_size:
            self._deque.popleft()

        # Maintain monotonic property
        if self.mode == "min":
            # For min: remove all elements >= value from back
            while self._deque and self._deque[-1][1] >= value:
                self._deque.pop()
        else:
            # For max: remove all elements <= value from back
            while self._deque and self._deque[-1][1] <= value:
                self._deque.pop()

        self._deque.append((idx, value))

    def get(self) -> float | None:
        """
        Get the current min or max value in the window.

        Returns:
            The minimum (or maximum) value in the current window,
            or None if the window is empty.
        """
        if not self._deque:
            return None
        return self._deque[0][1]

    def get_or_raise(self) -> float:
        """
        Get the current min or max value in the window, raising if empty.

        P3-002: Type-safe accessor that guarantees a float return.

        Returns:
            The minimum (or maximum) value in the current window.

        Raises:
            ValueError: If the window is empty.
        """
        if not self._deque:
            raise ValueError(
                f"MonotonicDeque is empty (mode={self.mode}, "
                f"window_size={self.window_size}). "
                f"Ensure at least one value has been pushed."
            )
        return self._deque[0][1]

    def __len__(self) -> int:
        """Return the number of elements currently in the deque."""
        return len(self._deque)

    def clear(self) -> None:
        """Clear all elements from the deque."""
        self._deque.clear()


class RingBuffer:
    """
    Fixed-size circular buffer for O(1) push and index access.

    Used for swing detection where we need to look back a fixed
    number of bars to compare values (e.g., is the middle element
    the highest of all elements in the window?).

    Elements are accessed by index where 0 is the oldest element
    and len-1 is the most recently pushed element.

    Example:
        >>> buf = RingBuffer(size=3)
        >>> buf.push(1.0)
        >>> buf.push(2.0)
        >>> buf.push(3.0)
        >>> buf.is_full()
        True
        >>> buf[0]  # oldest
        1.0
        >>> buf[2]  # newest
        3.0
        >>> buf.push(4.0)  # overwrites 1.0
        >>> buf[0]
        2.0
        >>> buf[2]
        4.0

    Attributes:
        size: Maximum number of elements the buffer can hold.
    """

    __slots__ = ("size", "_buffer", "_head", "_count")

    def __init__(self, size: int) -> None:
        """
        Initialize ring buffer with fixed size.

        Args:
            size: Maximum number of elements (must be >= 1).

        Raises:
            ValueError: If size < 1.
        """
        if size < 1:
            raise ValueError(
                f"size must be >= 1, got {size}\n"
                f"\n"
                f"Fix: RingBuffer(size=5)"
            )
        self.size = size
        self._buffer = np.full(size, np.nan, dtype=np.float64)
        self._head = 0  # Next write position
        self._count = 0  # Number of elements stored

    def push(self, value: float) -> None:
        """
        Add a value to the buffer, overwriting oldest if full.

        Args:
            value: Value to add.
        """
        self._buffer[self._head] = value
        self._head = (self._head + 1) % self.size
        if self._count < self.size:
            self._count += 1

    def __getitem__(self, idx: int) -> float:
        """
        Get element by logical index (0 = oldest, count-1 = newest).

        Args:
            idx: Logical index into the buffer.

        Returns:
            The value at the given index.

        Raises:
            IndexError: If idx is out of range.
        """
        if idx < 0 or idx >= self._count:
            raise IndexError(
                f"Index {idx} out of range [0, {self._count})\n"
                f"\n"
                f"Buffer has {self._count} elements."
            )
        # Physical index: oldest element is at (_head - _count) mod size
        physical = (self._head - self._count + idx) % self.size
        return float(self._buffer[physical])

    def is_full(self) -> bool:
        """
        Check if buffer has reached capacity.

        Returns:
            True if buffer contains exactly 'size' elements.
        """
        return self._count == self.size

    def __len__(self) -> int:
        """Return the number of elements currently in the buffer."""
        return self._count

    def clear(self) -> None:
        """Clear all elements from the buffer."""
        self._buffer.fill(np.nan)
        self._head = 0
        self._count = 0

    def to_array(self) -> np.ndarray:
        """
        Return a copy of the buffer contents in logical order.

        Returns:
            numpy array with oldest element first, newest last.
            Length equals current count (not size).
        """
        if self._count == 0:
            return np.array([], dtype=np.float64)

        result = np.empty(self._count, dtype=np.float64)
        for i in range(self._count):
            physical = (self._head - self._count + i) % self.size
            result[i] = self._buffer[physical]
        return result
