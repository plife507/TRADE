"""
SyntheticSnapshot - Controlled test snapshot for DSL validation.

Provides a simple interface that mimics RuntimeSnapshotView for testing DSL
conditions with controlled inputs and known expected outputs.

Usage:
    # Single bar with specific feature values
    snapshot = SyntheticSnapshot.with_features({
        "ema_9": 52.0,
        "ema_21": 50.0,
        "rsi_14": 45.0,
    })

    # Multiple bars for window/crossover tests (most recent last)
    snapshot = SyntheticSnapshot.with_history({
        "ema_9":  [48.0, 49.0, 51.0],  # 3 bars, current=51.0
        "ema_21": [50.0, 50.0, 50.0],
    })

    # Structure fields with dot notation
    snapshot = SyntheticSnapshot.with_features({
        "swing.high_level": 100.0,
        "swing.low_level": 80.0,
        "zone.state": "active",
    })
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class SyntheticSnapshot:
    """
    Test snapshot with controlled feature values.

    Implements the same interface as RuntimeSnapshotView for DSL evaluation:
    - get_feature_value(feature_id, field, offset)
    - get(path) for simple path access
    - get_with_offset(path, offset) for history access

    History is stored most-recent-last: [oldest, ..., current]
    Offset 0 = current bar (last element)
    Offset 1 = previous bar (second to last)
    """

    # Current values: {"ema_9": 52.0} or {"swing.high_level": 100.0}
    _features: dict[str, Any] = field(default_factory=dict)

    # History: {"ema_9": [48.0, 49.0, 51.0]} (most recent last)
    _history: dict[str, list[Any]] = field(default_factory=dict)

    # Simulated timestamp
    ts_close: datetime = field(default_factory=datetime.now)

    # Current bar close price (for price-based conditions)
    close: float = 50000.0

    @classmethod
    def with_features(cls, features: dict[str, Any], **kwargs) -> "SyntheticSnapshot":
        """
        Create snapshot with specific feature values.

        Args:
            features: Dict of feature values, e.g., {"ema_9": 52.0, "swing.high_level": 100.0}
            **kwargs: Additional snapshot properties (ts_close, close, etc.)

        Returns:
            SyntheticSnapshot with the given features
        """
        return cls(_features=features, **kwargs)

    @classmethod
    def with_history(
        cls,
        history: dict[str, list[Any]],
        **kwargs
    ) -> "SyntheticSnapshot":
        """
        Create snapshot with feature history for window/crossover tests.

        History is most-recent-last: [oldest, ..., current]

        Args:
            history: Dict of feature histories, e.g., {"ema_9": [48.0, 49.0, 51.0]}
            **kwargs: Additional snapshot properties

        Returns:
            SyntheticSnapshot with history
        """
        # Extract current values (last element of each history)
        features = {key: values[-1] for key, values in history.items() if values}
        return cls(_features=features, _history=history, **kwargs)

    @classmethod
    def with_ohlcv(
        cls,
        ohlcv: list[dict[str, float]],
        **kwargs
    ) -> "SyntheticSnapshot":
        """
        Create snapshot with full OHLCV data for structure detection tests.

        Args:
            ohlcv: List of OHLCV dicts, e.g., [{"open": 100, "high": 105, ...}, ...]
            **kwargs: Additional snapshot properties

        Returns:
            SyntheticSnapshot with OHLCV history

        Note:
            For structure tests, you typically pass this to a detector directly
            rather than using the snapshot's feature access.
        """
        if not ohlcv:
            return cls(**kwargs)

        # Extract current bar values
        current = ohlcv[-1]
        features = {
            "open": current.get("open", 0.0),
            "high": current.get("high", 0.0),
            "low": current.get("low", 0.0),
            "close": current.get("close", 0.0),
            "volume": current.get("volume", 0.0),
        }

        # Build history for each OHLCV field
        history = {
            "open": [bar.get("open", 0.0) for bar in ohlcv],
            "high": [bar.get("high", 0.0) for bar in ohlcv],
            "low": [bar.get("low", 0.0) for bar in ohlcv],
            "close": [bar.get("close", 0.0) for bar in ohlcv],
            "volume": [bar.get("volume", 0.0) for bar in ohlcv],
        }

        return cls(
            _features=features,
            _history=history,
            close=current.get("close", 0.0),
            **kwargs
        )

    def get_feature_value(
        self,
        feature_id: str,
        field: str | None = None,
        offset: int = 0
    ) -> Any:
        """
        Get feature value, matching RuntimeSnapshotView interface.

        Args:
            feature_id: Feature identifier (e.g., "ema_9", "swing")
            field: Optional field within feature (e.g., "high_level")
            offset: Bar offset (0 = current, 1 = previous, etc.)

        Returns:
            Feature value or None if not found
        """
        # Build path
        # Note: FeatureRef defaults to field="value" for simple features.
        # We treat field=None or field="value" as "just the feature_id".
        if field and field != "value":
            path = f"{feature_id}.{field}"
        else:
            path = feature_id

        return self.get_with_offset(path, offset)

    def get(self, path: str) -> Any:
        """
        Get current value by path.

        Args:
            path: Feature path, e.g., "ema_9" or "swing.high_level"

        Returns:
            Current value or None if not found
        """
        return self.get_with_offset(path, offset=0)

    def get_with_offset(self, path: str, offset: int = 0) -> Any:
        """
        Get value at specified offset.

        Args:
            path: Feature path
            offset: Bar offset (0 = current, 1 = previous, etc.)

        Returns:
            Value at offset or None if not available
        """
        # Check history first for offset lookups
        if path in self._history:
            history = self._history[path]
            idx = len(history) - 1 - offset
            if 0 <= idx < len(history):
                return history[idx]
            return None

        # For offset=0, check current features
        if offset == 0:
            return self._features.get(path)

        # No history and offset > 0 = not available
        return None

    def has_feature(self, path: str) -> bool:
        """Check if feature exists."""
        return path in self._features or path in self._history

    def add_feature(self, path: str, value: Any) -> "SyntheticSnapshot":
        """
        Add a feature value (mutates and returns self for chaining).

        Args:
            path: Feature path
            value: Value to set

        Returns:
            self for chaining
        """
        self._features[path] = value
        return self

    def add_history(self, path: str, values: list[Any]) -> "SyntheticSnapshot":
        """
        Add feature history (mutates and returns self for chaining).

        Args:
            path: Feature path
            values: History values (most recent last)

        Returns:
            self for chaining
        """
        self._history[path] = values
        if values:
            self._features[path] = values[-1]  # Keep current in sync
        return self
