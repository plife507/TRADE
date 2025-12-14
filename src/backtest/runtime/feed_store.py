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
"""

import numpy as np
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional, Set, List, TYPE_CHECKING
import pandas as pd

if TYPE_CHECKING:
    from ..features.feature_frame_builder import FeatureArrays


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
        
        # Close timestamp set for cache detection
        close_ts_set: Set of close timestamps (for is_close detection)
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
    
    # Close ts set for cache detection
    close_ts_set: Set[datetime] = field(default_factory=set)
    
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
        
        # Build close_ts_set
        close_ts_set = set()
        for ts in ts_close:
            if isinstance(ts, np.datetime64):
                close_ts_set.add(pd.Timestamp(ts).to_pydatetime())
            else:
                close_ts_set.add(ts)
        
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
        
        # Build close_ts_set
        close_ts_set = set()
        for ts in ts_close:
            if isinstance(ts, np.datetime64):
                close_ts_set.add(pd.Timestamp(ts).to_pydatetime())
            else:
                close_ts_set.add(ts)
        
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
            close_ts_set=close_ts_set,
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
