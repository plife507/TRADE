"""
Multi-timeframe feature caching.

Caches the last closed FeatureSnapshot for HTF and MTF timeframes.
Updates are triggered only when current_ts_close is in the respective close-ts map.

Ordering at each LTF step:
1. Refresh HTF (if closed)
2. Refresh MTF (if closed)
3. Compute/select LTF features
4. Build snapshot
5. Evaluate strategy

Close detection is data-driven (via close_ts maps), not modulo-based.
"""

from datetime import datetime
from collections.abc import Callable

from .types import Bar, FeatureSnapshot


class TimeframeCache:
    """
    Caches FeatureSnapshots for HTF and MTF timeframes.
    
    Uses data-driven close detection via close_ts maps.
    Carry-forward semantics: between closes, cached value is returned unchanged.
    """
    
    def __init__(self):
        """Initialize empty cache."""
        self._htf_snapshot: FeatureSnapshot | None = None
        self._mtf_snapshot: FeatureSnapshot | None = None

        # Close timestamp lookup sets (populated during data loading)
        self._htf_close_ts: set[datetime] = set()
        self._mtf_close_ts: set[datetime] = set()

        # Tracking
        self._htf_tf: str | None = None
        self._mtf_tf: str | None = None
        self._last_htf_update_ts: datetime | None = None
        self._last_mtf_update_ts: datetime | None = None
    
    def set_close_ts_maps(
        self,
        htf_close_ts: set[datetime],
        mtf_close_ts: set[datetime],
        htf_tf: str,
        mtf_tf: str,
    ) -> None:
        """
        Set the close timestamp lookup sets from data loading.
        
        Args:
            htf_close_ts: Set of HTF close timestamps
            mtf_close_ts: Set of MTF close timestamps
            htf_tf: HTF timeframe string
            mtf_tf: MTF timeframe string
        """
        self._htf_close_ts = htf_close_ts
        self._mtf_close_ts = mtf_close_ts
        self._htf_tf = htf_tf
        self._mtf_tf = mtf_tf
    
    def is_htf_close(self, current_ts_close: datetime) -> bool:
        """Check if current step is an HTF close."""
        return current_ts_close in self._htf_close_ts
    
    def is_mtf_close(self, current_ts_close: datetime) -> bool:
        """Check if current step is an MTF close."""
        return current_ts_close in self._mtf_close_ts
    
    def update_htf(self, snapshot: FeatureSnapshot) -> None:
        """
        Update HTF cache with new snapshot.
        
        Should only be called when is_htf_close() returns True.
        
        Args:
            snapshot: New HTF feature snapshot
        """
        self._htf_snapshot = snapshot
        self._last_htf_update_ts = snapshot.ts_close
    
    def update_mtf(self, snapshot: FeatureSnapshot) -> None:
        """
        Update MTF cache with new snapshot.
        
        Should only be called when is_mtf_close() returns True.
        
        Args:
            snapshot: New MTF feature snapshot
        """
        self._mtf_snapshot = snapshot
        self._last_mtf_update_ts = snapshot.ts_close
    
    def get_htf(self) -> FeatureSnapshot | None:
        """Get cached HTF snapshot (carry-forward)."""
        return self._htf_snapshot

    def get_mtf(self) -> FeatureSnapshot | None:
        """Get cached MTF snapshot (carry-forward)."""
        return self._mtf_snapshot
    
    @property
    def htf_ready(self) -> bool:
        """Check if HTF cache has a valid snapshot."""
        return self._htf_snapshot is not None and self._htf_snapshot.ready
    
    @property
    def mtf_ready(self) -> bool:
        """Check if MTF cache has a valid snapshot."""
        return self._mtf_snapshot is not None and self._mtf_snapshot.ready
    
    @property
    def all_ready(self) -> bool:
        """Check if both HTF and MTF caches are ready."""
        return self.htf_ready and self.mtf_ready
    
    def get_not_ready_reasons(self) -> list:
        """Get list of reasons why caches are not ready."""
        reasons = []
        if not self.htf_ready:
            if self._htf_snapshot is None:
                reasons.append(f"HTF ({self._htf_tf}): no snapshot yet")
            elif not self._htf_snapshot.ready:
                reasons.append(f"HTF ({self._htf_tf}): {self._htf_snapshot.not_ready_reason}")
        if not self.mtf_ready:
            if self._mtf_snapshot is None:
                reasons.append(f"MTF ({self._mtf_tf}): no snapshot yet")
            elif not self._mtf_snapshot.ready:
                reasons.append(f"MTF ({self._mtf_tf}): {self._mtf_snapshot.not_ready_reason}")
        return reasons
    
    def refresh_step(
        self,
        current_ts_close: datetime,
        htf_snapshot_factory: Callable[[], FeatureSnapshot],
        mtf_snapshot_factory: Callable[[], FeatureSnapshot],
    ) -> tuple[bool, bool]:
        """
        Refresh caches for current step.
        
        Applies updates in order: HTF first, then MTF.
        Returns (htf_updated, mtf_updated) booleans.
        
        Args:
            current_ts_close: Current LTF close timestamp
            htf_snapshot_factory: Callable returning HTF FeatureSnapshot
            mtf_snapshot_factory: Callable returning MTF FeatureSnapshot
            
        Returns:
            Tuple of (htf_updated, mtf_updated)
        """
        htf_updated = False
        mtf_updated = False
        
        # 1. Refresh HTF (if closed)
        if self.is_htf_close(current_ts_close):
            snapshot = htf_snapshot_factory()
            self.update_htf(snapshot)
            htf_updated = True
        
        # 2. Refresh MTF (if closed)
        if self.is_mtf_close(current_ts_close):
            snapshot = mtf_snapshot_factory()
            self.update_mtf(snapshot)
            mtf_updated = True
        
        return (htf_updated, mtf_updated)
    
    def reset(self) -> None:
        """Reset cache to initial state."""
        self._htf_snapshot = None
        self._mtf_snapshot = None
        self._last_htf_update_ts = None
        self._last_mtf_update_ts = None
    
    def to_dict(self) -> dict:
        """Get cache state as dict for debugging."""
        return {
            "htf_tf": self._htf_tf,
            "mtf_tf": self._mtf_tf,
            "htf_ready": self.htf_ready,
            "mtf_ready": self.mtf_ready,
            "last_htf_update_ts": (
                self._last_htf_update_ts.isoformat()
                if self._last_htf_update_ts else None
            ),
            "last_mtf_update_ts": (
                self._last_mtf_update_ts.isoformat()
                if self._last_mtf_update_ts else None
            ),
            "htf_close_count": len(self._htf_close_ts),
            "mtf_close_count": len(self._mtf_close_ts),
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

