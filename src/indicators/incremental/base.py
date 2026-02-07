"""
Base class and shared imports for incremental indicators.

All incremental indicators inherit from IncrementalIndicator, which defines
the O(1) per-bar update interface: update(), reset(), value, is_ready.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import numpy as np


class IncrementalIndicator(ABC):
    """Base class for incremental indicators."""

    @abstractmethod
    def update(self, **kwargs: Any) -> None:
        """Update with new data."""
        ...

    @abstractmethod
    def reset(self) -> None:
        """Reset state to initial."""
        ...

    @property
    @abstractmethod
    def value(self) -> float:
        """Current indicator value."""
        ...

    @property
    @abstractmethod
    def is_ready(self) -> bool:
        """True when warmup period complete."""
        ...
