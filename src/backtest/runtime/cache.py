"""
Multi-timeframe feature caching.

Caches the last closed FeatureSnapshot for high_tf and med_tf timeframes.
Updates are triggered only when current_ts_close is in the respective close-ts map.

Ordering at each exec_tf step:
1. Refresh high_tf (if closed)
2. Refresh med_tf (if closed)
3. Compute/select exec_tf features
4. Build snapshot
5. Evaluate strategy

Close detection is data-driven (via close_ts maps), not modulo-based.
"""

from datetime import datetime
from collections.abc import Callable

from .types import Bar, FeatureSnapshot


class TimeframeCache:
    """
    Caches FeatureSnapshots for high_tf and med_tf timeframes.

    Uses data-driven close detection via close_ts maps.
    Carry-forward semantics: between closes, cached value is returned unchanged.
    """

    def __init__(self):
        """Initialize empty cache."""
        self._high_tf_snapshot: FeatureSnapshot | None = None
        self._med_tf_snapshot: FeatureSnapshot | None = None

        # Close timestamp lookup sets (populated during data loading)
        self._high_tf_close_ts: set[datetime] = set()
        self._med_tf_close_ts: set[datetime] = set()

        # Tracking
        self._high_tf: str | None = None
        self._med_tf: str | None = None
        self._last_high_tf_update_ts: datetime | None = None
        self._last_med_tf_update_ts: datetime | None = None

    def set_close_ts_maps(
        self,
        high_tf_close_ts: set[datetime],
        med_tf_close_ts: set[datetime],
        high_tf: str,
        med_tf: str,
    ) -> None:
        """
        Set the close timestamp lookup sets from data loading.

        Args:
            high_tf_close_ts: Set of high_tf close timestamps
            med_tf_close_ts: Set of med_tf close timestamps
            high_tf: high_tf timeframe string
            med_tf: med_tf timeframe string
        """
        self._high_tf_close_ts = high_tf_close_ts
        self._med_tf_close_ts = med_tf_close_ts
        self._high_tf = high_tf
        self._med_tf = med_tf

    def is_high_tf_close(self, current_ts_close: datetime) -> bool:
        """Check if current step is a high_tf close."""
        return current_ts_close in self._high_tf_close_ts

    def is_med_tf_close(self, current_ts_close: datetime) -> bool:
        """Check if current step is a med_tf close."""
        return current_ts_close in self._med_tf_close_ts

    def update_high_tf(self, snapshot: FeatureSnapshot) -> None:
        """
        Update high_tf cache with new snapshot.

        Should only be called when is_high_tf_close() returns True.

        Args:
            snapshot: New high_tf feature snapshot
        """
        self._high_tf_snapshot = snapshot
        self._last_high_tf_update_ts = snapshot.ts_close

    def update_med_tf(self, snapshot: FeatureSnapshot) -> None:
        """
        Update med_tf cache with new snapshot.

        Should only be called when is_med_tf_close() returns True.

        Args:
            snapshot: New med_tf feature snapshot
        """
        self._med_tf_snapshot = snapshot
        self._last_med_tf_update_ts = snapshot.ts_close

    def get_high_tf(self) -> FeatureSnapshot | None:
        """Get cached high_tf snapshot (carry-forward)."""
        return self._high_tf_snapshot

    def get_med_tf(self) -> FeatureSnapshot | None:
        """Get cached med_tf snapshot (carry-forward)."""
        return self._med_tf_snapshot

    @property
    def high_tf_ready(self) -> bool:
        """Check if high_tf cache has a valid snapshot."""
        return self._high_tf_snapshot is not None and self._high_tf_snapshot.ready

    @property
    def med_tf_ready(self) -> bool:
        """Check if med_tf cache has a valid snapshot."""
        return self._med_tf_snapshot is not None and self._med_tf_snapshot.ready

    @property
    def all_ready(self) -> bool:
        """Check if both high_tf and med_tf caches are ready."""
        return self.high_tf_ready and self.med_tf_ready

    def get_not_ready_reasons(self) -> list:
        """Get list of reasons why caches are not ready."""
        reasons = []
        if not self.high_tf_ready:
            if self._high_tf_snapshot is None:
                reasons.append(f"high_tf ({self._high_tf}): no snapshot yet")
            elif not self._high_tf_snapshot.ready:
                reasons.append(f"high_tf ({self._high_tf}): {self._high_tf_snapshot.not_ready_reason}")
        if not self.med_tf_ready:
            if self._med_tf_snapshot is None:
                reasons.append(f"med_tf ({self._med_tf}): no snapshot yet")
            elif not self._med_tf_snapshot.ready:
                reasons.append(f"med_tf ({self._med_tf}): {self._med_tf_snapshot.not_ready_reason}")
        return reasons

    def refresh_step(
        self,
        current_ts_close: datetime,
        high_tf_snapshot_factory: Callable[[], FeatureSnapshot],
        med_tf_snapshot_factory: Callable[[], FeatureSnapshot],
    ) -> tuple[bool, bool]:
        """
        Refresh caches for current step.

        Applies updates in order: high_tf first, then med_tf.
        Returns (high_tf_updated, med_tf_updated) booleans.

        Args:
            current_ts_close: Current exec_tf close timestamp
            high_tf_snapshot_factory: Callable returning high_tf FeatureSnapshot
            med_tf_snapshot_factory: Callable returning med_tf FeatureSnapshot

        Returns:
            Tuple of (high_tf_updated, med_tf_updated)
        """
        high_tf_updated = False
        med_tf_updated = False

        # 1. Refresh high_tf (if closed)
        if self.is_high_tf_close(current_ts_close):
            snapshot = high_tf_snapshot_factory()
            self.update_high_tf(snapshot)
            high_tf_updated = True

        # 2. Refresh med_tf (if closed)
        if self.is_med_tf_close(current_ts_close):
            snapshot = med_tf_snapshot_factory()
            self.update_med_tf(snapshot)
            med_tf_updated = True

        return (high_tf_updated, med_tf_updated)

    def reset(self) -> None:
        """Reset cache to initial state."""
        self._high_tf_snapshot = None
        self._med_tf_snapshot = None
        self._last_high_tf_update_ts = None
        self._last_med_tf_update_ts = None

    def to_dict(self) -> dict:
        """Get cache state as dict for debugging."""
        return {
            "high_tf": self._high_tf,
            "med_tf": self._med_tf,
            "high_tf_ready": self.high_tf_ready,
            "med_tf_ready": self.med_tf_ready,
            "last_high_tf_update_ts": (
                self._last_high_tf_update_ts.isoformat()
                if self._last_high_tf_update_ts else None
            ),
            "last_med_tf_update_ts": (
                self._last_med_tf_update_ts.isoformat()
                if self._last_med_tf_update_ts else None
            ),
            "high_tf_close_count": len(self._high_tf_close_ts),
            "med_tf_close_count": len(self._med_tf_close_ts),
        }


def build_close_ts_map(
    bars: list,
) -> set[datetime]:
    """
    Build a set of close timestamps from a list of Bars.
    
    Args:
        bars: List of Bar objects
        
    Returns:
        Set of ts_close datetimes
    """
    return {bar.ts_close for bar in bars}


def build_close_ts_map_from_df(
    df,
    ts_close_column: str = "ts_close",
) -> set[datetime]:
    """
    Build a set of close timestamps from a DataFrame.
    
    Args:
        df: DataFrame with ts_close column
        ts_close_column: Name of the ts_close column
        
    Returns:
        Set of ts_close datetimes
    """
    if ts_close_column not in df.columns:
        raise ValueError(f"Column '{ts_close_column}' not in DataFrame")
    
    close_ts = set()
    for ts in df[ts_close_column]:
        if hasattr(ts, "to_pydatetime"):
            ts = ts.to_pydatetime()
        close_ts.add(ts)
    
    return close_ts

