"""
Feed store for precomputed indicator arrays.

Provides O(1) array access for the hot loop:
- OHLCV arrays (open, high, low, close, volume)
- Indicator arrays (ema_fast, ema_slow, rsi, atr, etc.)
- ts_open / ts_close arrays

All data is precomputed outside the hot loop.
The FeedStore is immutable once built.

PERFORMANCE CONTRACT:
- No DataFrame operations in hot loop
- No indicator computation in hot loop
- All access via array[index] is O(1)
- Prefer float32 for indicator arrays (memory efficiency)

METADATA:
- Indicator metadata provides provenance and reproducibility tracking
- Stored in-memory only (not persisted to DB)
- Accessed via indicator_metadata dict (keyed by indicator_key)
"""

import bisect
import numpy as np
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional, Set, List, TYPE_CHECKING
import pandas as pd

if TYPE_CHECKING:
    from ..features.feature_frame_builder import FeatureArrays
    from .indicator_metadata import IndicatorMetadata
    from ..market_structure.builder import StructureStore


@dataclass
class FeedStore:
    """
    Immutable store of precomputed arrays for one timeframe.
    
    Built once from a DataFrame with indicators or FeatureArrays.
    Provides O(1) access to any bar's data via index.
    
    Attributes:
        tf: Timeframe string
        symbol: Trading symbol
        
        # Core OHLCV arrays
        ts_open: Array of open timestamps (numpy datetime64)
        ts_close: Array of close timestamps (numpy datetime64)
        open: Array of open prices
        high: Array of high prices
        low: Array of low prices
        close: Array of close prices
        volume: Array of volumes
        
        # Indicator arrays (keyed by name)
        indicators: Dict of indicator_name -> numpy array (float32 or float64)
        
        # Indicator metadata (keyed by name, in-memory only)
        indicator_metadata: Dict of indicator_name -> IndicatorMetadata
        
        # Close timestamp set for cache detection
        close_ts_set: Set of close timestamps (for is_close detection)
        
        # O(1) ts_close->index mapping (epoch ms -> array index)
        ts_close_ms_to_idx: Dict of epoch_ms (int) -> index (int)
    """
    tf: str
    symbol: str
    
    # Core OHLCV as numpy arrays
    ts_open: np.ndarray  # datetime64
    ts_close: np.ndarray  # datetime64
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray
    
    # Indicator arrays (float32 preferred for memory efficiency)
    indicators: Dict[str, np.ndarray] = field(default_factory=dict)
    
    # Indicator metadata (in-memory provenance tracking)
    indicator_metadata: Dict[str, "IndicatorMetadata"] = field(default_factory=dict)

    # Structure stores (keyed by block_id)
    # Populated by StructureBuilder; provides structure.* namespace
    structures: Dict[str, "StructureStore"] = field(default_factory=dict)

    # Structure key map (block_key -> block_id) for resolution
    structure_key_map: Dict[str, str] = field(default_factory=dict)

    # Close ts set for cache detection
    close_ts_set: Set[datetime] = field(default_factory=set)
    
    # O(1) ts_close->index mapping (epoch ms -> array index)
    # Used for MTF/HTF forward-fill lookups
    ts_close_ms_to_idx: Dict[int, int] = field(default_factory=dict)

    # Sorted list of close timestamps (ms) for O(log n) binary search
    # Built once in __post_init__, used by get_last_closed_idx_at_or_before()
    _sorted_close_ms: List[int] = field(default_factory=list)

    # Length
    length: int = 0

    # Warmup bars (first valid indicator index)
    warmup_bars: int = 0

    def __post_init__(self):
        """Validate arrays have consistent length."""
        if self.length == 0:
            self.length = len(self.close)
        
        assert len(self.ts_open) == self.length, "ts_open length mismatch"
        assert len(self.ts_close) == self.length, "ts_close length mismatch"
        assert len(self.open) == self.length, "open length mismatch"
        assert len(self.high) == self.length, "high length mismatch"
        assert len(self.low) == self.length, "low length mismatch"
        assert len(self.close) == self.length, "close length mismatch"
        assert len(self.volume) == self.length, "volume length mismatch"
        
        for name, arr in self.indicators.items():
            assert len(arr) == self.length, f"indicator {name} length mismatch"
        
        # Metadata coverage check (if metadata is provided, it must match indicators)
        # NOTE: This is a soft check - legacy paths may not have metadata
        if self.indicator_metadata:
            indicator_keys = set(self.indicators.keys())
            metadata_keys = set(self.indicator_metadata.keys())
            if indicator_keys != metadata_keys:
                missing = indicator_keys - metadata_keys
                extra = metadata_keys - indicator_keys
                # Log warning but don't fail for backward compatibility
                import logging
                logger = logging.getLogger(__name__)
                if missing:
                    logger.warning(f"FeedStore: Missing metadata for indicators: {missing}")
                if extra:
                    logger.warning(f"FeedStore: Extra metadata without indicators: {extra}")

        # Build sorted list of close timestamps for O(log n) binary search
        # This is built once and cached for get_last_closed_idx_at_or_before()
        if self.ts_close_ms_to_idx and not self._sorted_close_ms:
            self._sorted_close_ms = sorted(self.ts_close_ms_to_idx.keys())
    
    @property
    def indicator_keys(self) -> List[str]:
        """Get all indicator keys."""
        return list(self.indicators.keys())
    
    def get_ts_close_datetime(self, idx: int) -> datetime:
        """Get ts_close as Python datetime at index."""
        ts = self.ts_close[idx]
        if isinstance(ts, np.datetime64):
            return pd.Timestamp(ts).to_pydatetime()
        return ts
    
    def get_ts_open_datetime(self, idx: int) -> datetime:
        """Get ts_open as Python datetime at index."""
        ts = self.ts_open[idx]
        if isinstance(ts, np.datetime64):
            return pd.Timestamp(ts).to_pydatetime()
        return ts
    
    def is_close_at(self, ts: datetime) -> bool:
        """Check if ts is a close timestamp for this TF."""
        return ts in self.close_ts_set
    
    def get_idx_at_ts_close(self, ts: datetime) -> Optional[int]:
        """
        Get array index for a given ts_close timestamp.
        
        O(1) lookup using precomputed ts_close_ms_to_idx mapping.
        
        Args:
            ts: Close timestamp to look up
            
        Returns:
            Array index or None if not found
        """
        # Convert to epoch ms
        if isinstance(ts, np.datetime64):
            ts_ms = int(pd.Timestamp(ts).timestamp() * 1000)
        else:
            ts_ms = int(ts.timestamp() * 1000)
        return self.ts_close_ms_to_idx.get(ts_ms)
    
    def get_last_closed_idx_at_or_before(self, ts: datetime) -> Optional[int]:
        """
        Get the last closed bar index at or before a given timestamp.

        Used for forward-fill semantics in MTF/HTF.
        O(log n) via binary search on cached sorted timestamp list.

        Args:
            ts: Reference timestamp

        Returns:
            Array index of last closed bar, or None if none found
        """
        if not self._sorted_close_ms:
            return None

        if isinstance(ts, np.datetime64):
            ts_ms = int(pd.Timestamp(ts).timestamp() * 1000)
        else:
            ts_ms = int(ts.timestamp() * 1000)

        # Binary search: find rightmost value <= ts_ms
        # bisect_right returns insertion point, so pos-1 is the last value <= ts_ms
        pos = bisect.bisect_right(self._sorted_close_ms, ts_ms)

        if pos == 0:
            return None  # All timestamps are after ts

        # pos-1 is the index of the largest timestamp <= ts_ms
        close_ms = self._sorted_close_ms[pos - 1]
        return self.ts_close_ms_to_idx[close_ms]
    
    def _get_ts_close_ms_at(self, idx: int) -> int:
        """Get ts_close in epoch ms at a given index."""
        ts = self.ts_close[idx]
        if isinstance(ts, np.datetime64):
            return int(pd.Timestamp(ts).timestamp() * 1000)
        return int(ts.timestamp() * 1000)

    def get_structure_field(
        self,
        block_key: str,
        field_name: str,
        bar_idx: int,
    ) -> Optional[float]:
        """
        Get structure field value at specific bar index.

        Args:
            block_key: User-facing block key (e.g., "ms_5m")
            field_name: Public field name (e.g., "swing_high_level")
            bar_idx: Bar index to retrieve

        Returns:
            Field value or None if not available

        Raises:
            ValueError: If block_key or field_name is unknown
        """
        # Resolve block_key to block_id
        block_id = self.structure_key_map.get(block_key)
        if block_id is None:
            raise ValueError(
                f"Unknown structure block_key '{block_key}'. "
                f"Available: {list(self.structure_key_map.keys())}"
            )

        # Get store
        store = self.structures.get(block_id)
        if store is None:
            raise ValueError(
                f"Structure store not found for block_id '{block_id}'"
            )

        # Get field value
        return store.get_field(field_name, bar_idx)

    def has_structure(self, block_key: str) -> bool:
        """Check if a structure block exists."""
        return block_key in self.structure_key_map

    def get_structure_fields(self, block_key: str) -> List[str]:
        """Get list of available fields for a structure block."""
        block_id = self.structure_key_map.get(block_key)
        if block_id is None:
            return []
        store = self.structures.get(block_id)
        if store is None:
            return []
        return list(store.fields.keys())

    def get_zone_field(
        self,
        block_key: str,
        zone_key: str,
        field_name: str,
        bar_idx: int,
    ) -> Optional[float]:
        """
        Get zone field value at specific bar index.

        Stage 5: Zones are children of structure blocks.

        Args:
            block_key: Parent structure block key (e.g., "ms_5m")
            zone_key: Zone key (e.g., "demand_1")
            field_name: Field name (e.g., "lower", "state")
            bar_idx: Bar index to retrieve

        Returns:
            Field value or None if not available

        Raises:
            ValueError: If block_key, zone_key, or field_name is unknown
        """
        # Resolve block_key to block_id
        block_id = self.structure_key_map.get(block_key)
        if block_id is None:
            raise ValueError(
                f"Unknown structure block_key '{block_key}'. "
                f"Available: {list(self.structure_key_map.keys())}"
            )

        # Get store
        store = self.structures.get(block_id)
        if store is None:
            raise ValueError(
                f"Structure store not found for block_id '{block_id}'"
            )

        # Delegate to store's zone field accessor
        return store.get_zone_field(zone_key, field_name, bar_idx)

    def has_zone(self, block_key: str, zone_key: str) -> bool:
        """Check if a zone exists under a structure block."""
        block_id = self.structure_key_map.get(block_key)
        if block_id is None:
            return False
        store = self.structures.get(block_id)
        if store is None:
            return False
        return store.has_zone(zone_key)

    def get_zone_fields(self, block_key: str, zone_key: str) -> List[str]:
        """Get available fields for a zone."""
        block_id = self.structure_key_map.get(block_key)
        if block_id is None:
            return []
        store = self.structures.get(block_id)
        if store is None:
            return []
        return store.get_zone_fields(zone_key)

    @classmethod
    def from_dataframe(
        cls,
        df: pd.DataFrame,
        tf: str,
        symbol: str,
        indicator_columns: Optional[List[str]] = None,
        prefer_float32: bool = False,
    ) -> "FeedStore":
        """
        Build FeedStore from DataFrame with indicators.
        
        IMPORTANT: No implicit/default indicators. If indicator_columns is None
        or empty, no indicators will be extracted. Use FeatureFrameBuilder for
        explicit indicator computation.
        
        Args:
            df: DataFrame with OHLCV and indicator columns
            tf: Timeframe string
            symbol: Trading symbol
            indicator_columns: List of indicator column names to extract.
                              If None or empty, no indicators are extracted.
                              NO DEFAULTS — explicit only.
            prefer_float32: If True, use float32 for indicator arrays (default: False)
        
        Returns:
            FeedStore with all data as numpy arrays
        """
        # NO IMPLICIT DEFAULTS — indicator_columns must be explicitly provided
        # If None or empty, no indicators are extracted
        if indicator_columns is None:
            indicator_columns = []
        
        # Ensure sorted by timestamp
        df = df.sort_values("timestamp").reset_index(drop=True)
        
        # Extract OHLCV
        ts_open = df["timestamp"].values
        
        # ts_close must exist or be computed
        if "ts_close" in df.columns:
            ts_close = df["ts_close"].values
        else:
            # Compute from tf_duration if not present
            from .timeframe import tf_duration
            delta = tf_duration(tf)
            ts_close = np.array([
                (pd.Timestamp(t) + delta).to_pydatetime()
                for t in df["timestamp"]
            ])
        
        # Build close_ts_set and ts_close_ms_to_idx mapping
        close_ts_set = set()
        ts_close_ms_to_idx: Dict[int, int] = {}
        for i, ts in enumerate(ts_close):
            if isinstance(ts, np.datetime64):
                dt = pd.Timestamp(ts).to_pydatetime()
                ts_ms = int(pd.Timestamp(ts).timestamp() * 1000)
            else:
                dt = ts
                ts_ms = int(ts.timestamp() * 1000)
            close_ts_set.add(dt)
            ts_close_ms_to_idx[ts_ms] = i
        
        # Extract indicators
        dtype = np.float32 if prefer_float32 else np.float64
        indicators = {}
        for col in indicator_columns:
            if col in df.columns:
                indicators[col] = df[col].values.astype(dtype)
        
        return cls(
            tf=tf,
            symbol=symbol,
            ts_open=ts_open,
            ts_close=ts_close,
            open=df["open"].values.astype(np.float64),
            high=df["high"].values.astype(np.float64),
            low=df["low"].values.astype(np.float64),
            close=df["close"].values.astype(np.float64),
            volume=df["volume"].values.astype(np.float64),
            indicators=indicators,
            close_ts_set=close_ts_set,
            ts_close_ms_to_idx=ts_close_ms_to_idx,
            length=len(df),
        )
    
    @classmethod
    def from_dataframe_with_features(
        cls,
        df: pd.DataFrame,
        tf: str,
        symbol: str,
        feature_arrays: "FeatureArrays",
    ) -> "FeedStore":
        """
        Build FeedStore from DataFrame + precomputed FeatureArrays.
        
        This is the preferred method when using FeatureFrameBuilder.
        OHLCV comes from the DataFrame, indicators from FeatureArrays.
        
        Args:
            df: OHLCV DataFrame
            tf: Timeframe string
            symbol: Trading symbol
            feature_arrays: Precomputed FeatureArrays from FeatureFrameBuilder
            
        Returns:
            FeedStore with OHLCV and indicator arrays
        """
        # Ensure sorted by timestamp
        df = df.sort_values("timestamp").reset_index(drop=True)
        
        if len(df) != feature_arrays.length:
            raise ValueError(
                f"DataFrame length {len(df)} != FeatureArrays length {feature_arrays.length}"
            )
        
        # Extract timestamps
        ts_open = df["timestamp"].values
        
        # ts_close must exist or be computed
        if "ts_close" in df.columns:
            ts_close = df["ts_close"].values
        else:
            from .timeframe import tf_duration
            delta = tf_duration(tf)
            ts_close = np.array([
                (pd.Timestamp(t) + delta).to_pydatetime()
                for t in df["timestamp"]
            ])
        
        # Build close_ts_set and ts_close_ms_to_idx mapping
        close_ts_set = set()
        ts_close_ms_to_idx: Dict[int, int] = {}
        for i, ts in enumerate(ts_close):
            if isinstance(ts, np.datetime64):
                dt = pd.Timestamp(ts).to_pydatetime()
                ts_ms = int(pd.Timestamp(ts).timestamp() * 1000)
            else:
                dt = ts
                ts_ms = int(ts.timestamp() * 1000)
            close_ts_set.add(dt)
            ts_close_ms_to_idx[ts_ms] = i
        
        return cls(
            tf=tf,
            symbol=symbol,
            ts_open=ts_open,
            ts_close=ts_close,
            open=df["open"].values.astype(np.float64),
            high=df["high"].values.astype(np.float64),
            low=df["low"].values.astype(np.float64),
            close=df["close"].values.astype(np.float64),
            volume=df["volume"].values.astype(np.float64),
            indicators=feature_arrays.arrays,  # Already float32
            indicator_metadata=feature_arrays.metadata,  # Provenance tracking
            close_ts_set=close_ts_set,
            ts_close_ms_to_idx=ts_close_ms_to_idx,
            length=len(df),
            warmup_bars=feature_arrays.warmup_bars,
        )


@dataclass
class MultiTFFeedStore:
    """
    Container for multiple FeedStores (HTF, MTF, Exec).
    
    Provides unified access to all timeframe data.
    """
    exec_feed: FeedStore
    htf_feed: Optional[FeedStore] = None
    mtf_feed: Optional[FeedStore] = None
    
    # TF mapping
    tf_mapping: Dict[str, str] = field(default_factory=dict)
    
    def get_feed(self, role: str) -> Optional[FeedStore]:
        """Get feed by role (htf, mtf, ltf/exec)."""
        if role in ("ltf", "exec"):
            return self.exec_feed
        elif role == "htf":
            return self.htf_feed
        elif role == "mtf":
            return self.mtf_feed
        return None
