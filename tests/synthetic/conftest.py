"""
Pytest configuration for synthetic tests.
"""

import pytest
from tests.synthetic.harness.snapshot import SyntheticSnapshot


@pytest.fixture
def empty_snapshot() -> SyntheticSnapshot:
    """Empty snapshot for basic tests."""
    return SyntheticSnapshot()


@pytest.fixture
def simple_snapshot() -> SyntheticSnapshot:
    """Simple snapshot with common features."""
    return SyntheticSnapshot.with_features({
        "ema_9": 52.0,
        "ema_21": 50.0,
        "rsi_14": 45.0,
        "close": 50000.0,
    })


@pytest.fixture
def crossover_snapshot() -> SyntheticSnapshot:
    """Snapshot with history for crossover tests."""
    return SyntheticSnapshot.with_history({
        "ema_9": [48.0, 49.0, 51.0],   # Crosses above at current bar
        "ema_21": [50.0, 50.0, 50.0],  # Constant
    })
