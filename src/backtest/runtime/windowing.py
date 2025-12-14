"""
Load window computation for backtest runs.

Computes the required data window for a backtest run based on:
- Test window (start/end from config)
- Warmup span (derived from indicator lookbacks and TF durations)
- Safety buffers (extra closed candles for cache reliability)
- Tail buffer (extra bars at end for funding intervals)

Formula:
    load_start = test_start - warmup_span - safety_buffer
    load_end = test_end + tail_buffer

All buffers are config-driven with sensible defaults.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Optional, List

from .timeframe import tf_duration, tf_minutes


# Default warmup multiplier for EMA stabilization
# Recommended: 4N (preferred), minimum 3N for EMA(N)
DEFAULT_WARMUP_MULTIPLIER = 4

# Default safety buffer in number of closes per TF
DEFAULT_HTF_SAFETY_CLOSES = 10
DEFAULT_MTF_SAFETY_CLOSES = 20

# Default tail buffer
DEFAULT_TAIL_LTF_BARS = 2
DEFAULT_TAIL_FUNDING_INTERVALS = 1
FUNDING_INTERVAL_HOURS = 8  # Bybit funding every 8 hours


@dataclass
class WarmupConfig:
    """Configuration for warmup and buffer calculations."""
    
    # Warmup multiplier for indicator stabilization
    # warmup_bars = max_lookback * warmup_multiplier
    warmup_multiplier: int = DEFAULT_WARMUP_MULTIPLIER
    
    # Safety buffer: extra closed candles per TF
    htf_safety_closes: int = DEFAULT_HTF_SAFETY_CLOSES
    mtf_safety_closes: int = DEFAULT_MTF_SAFETY_CLOSES
    
    # Tail buffer
    tail_ltf_bars: int = DEFAULT_TAIL_LTF_BARS
    tail_funding_intervals: int = DEFAULT_TAIL_FUNDING_INTERVALS


@dataclass
class LoadWindow:
    """Computed load window for a backtest run."""
    
    # Requested test window
    test_start: datetime
    test_end: datetime
    
    # Computed load window (extended for warmup/buffers)
    load_start: datetime
    load_end: datetime
    
    # Components (for debugging/logging)
    warmup_span: timedelta
    safety_buffer_span: timedelta
    tail_buffer_span: timedelta
    
    # Metadata
    warmup_bars_by_tf: Dict[str, int]
    max_lookback_bars: int
    
    def to_dict(self) -> dict:
        """Convert to dict for serialization."""
        return {
            "test_start": self.test_start.isoformat(),
            "test_end": self.test_end.isoformat(),
            "load_start": self.load_start.isoformat(),
            "load_end": self.load_end.isoformat(),
            "warmup_span_seconds": self.warmup_span.total_seconds(),
            "safety_buffer_span_seconds": self.safety_buffer_span.total_seconds(),
            "tail_buffer_span_seconds": self.tail_buffer_span.total_seconds(),
            "warmup_bars_by_tf": self.warmup_bars_by_tf,
            "max_lookback_bars": self.max_lookback_bars,
        }


def compute_warmup_bars(
    max_lookback: int,
    warmup_multiplier: int = DEFAULT_WARMUP_MULTIPLIER,
) -> int:
    """
    Compute warmup bars from max indicator lookback.
    
    Formula: warmup_bars = max_lookback * warmup_multiplier
    
    Recommended heuristic for EMA(N):
    - warmup_bars = 4N (preferred)
    - minimum 3N for stability
    
    Args:
        max_lookback: Maximum indicator lookback in bars
        warmup_multiplier: Multiplier for stabilization
        
    Returns:
        Number of warmup bars needed
    """
    if max_lookback <= 0:
        return 0
    return max_lookback * warmup_multiplier


def compute_warmup_span(
    tf_mapping: Dict[str, str],
    indicator_lookbacks: Dict[str, int],
    warmup_config: Optional[WarmupConfig] = None,
) -> timedelta:
    """
    Compute total warmup span from TF mapping and indicator lookbacks.
    
    Formula: warmup_span = max(warmup_bars_tf * tf_duration(tf) for each TF)
    
    Args:
        tf_mapping: Dict with htf, mtf, ltf -> tf string
        indicator_lookbacks: Dict with tf -> max lookback bars for that TF
        warmup_config: Optional warmup configuration
        
    Returns:
        Maximum warmup span as timedelta
    """
    config = warmup_config or WarmupConfig()
    
    max_span = timedelta(0)
    
    for role, tf in tf_mapping.items():
        lookback = indicator_lookbacks.get(tf, 0)
        warmup_bars = compute_warmup_bars(lookback, config.warmup_multiplier)
        span = warmup_bars * tf_duration(tf)
        
        if span > max_span:
            max_span = span
    
    return max_span


def compute_safety_buffer_span(
    tf_mapping: Dict[str, str],
    warmup_config: Optional[WarmupConfig] = None,
) -> timedelta:
    """
    Compute safety buffer span (extra closes to ensure cache readiness).
    
    Args:
        tf_mapping: Dict with htf, mtf, ltf -> tf string
        warmup_config: Optional warmup configuration
        
    Returns:
        Safety buffer as timedelta
    """
    config = warmup_config or WarmupConfig()
    
    htf_buffer = config.htf_safety_closes * tf_duration(tf_mapping["htf"])
    mtf_buffer = config.mtf_safety_closes * tf_duration(tf_mapping["mtf"])
    
    # Use the larger buffer
    return max(htf_buffer, mtf_buffer)


def compute_tail_buffer_span(
    tf_mapping: Dict[str, str],
    warmup_config: Optional[WarmupConfig] = None,
) -> timedelta:
    """
    Compute tail buffer span (extra bars at end for funding).
    
    Args:
        tf_mapping: Dict with htf, mtf, ltf -> tf string
        warmup_config: Optional warmup configuration
        
    Returns:
        Tail buffer as timedelta
    """
    config = warmup_config or WarmupConfig()
    
    ltf_buffer = config.tail_ltf_bars * tf_duration(tf_mapping["ltf"])
    funding_buffer = config.tail_funding_intervals * timedelta(hours=FUNDING_INTERVAL_HOURS)
    
    return ltf_buffer + funding_buffer


def compute_load_window(
    test_start: datetime,
    test_end: datetime,
    tf_mapping: Dict[str, str],
    indicator_lookbacks: Dict[str, int],
    warmup_config: Optional[WarmupConfig] = None,
) -> LoadWindow:
    """
    Compute the full load window for a backtest run.
    
    Formula:
        load_start = test_start - warmup_span - safety_buffer
        load_end = test_end + tail_buffer
    
    Args:
        test_start: Test window start (from config)
        test_end: Test window end (from config)
        tf_mapping: Dict with htf, mtf, ltf -> tf string
        indicator_lookbacks: Dict with tf -> max lookback bars
        warmup_config: Optional warmup configuration
        
    Returns:
        LoadWindow with computed boundaries and metadata
    """
    config = warmup_config or WarmupConfig()
    
    # Compute warmup span
    warmup_span = compute_warmup_span(tf_mapping, indicator_lookbacks, config)
    
    # Compute safety buffer
    safety_buffer = compute_safety_buffer_span(tf_mapping, config)
    
    # Compute tail buffer
    tail_buffer = compute_tail_buffer_span(tf_mapping, config)
    
    # Compute load boundaries
    load_start = test_start - warmup_span - safety_buffer
    load_end = test_end + tail_buffer
    
    # Compute warmup bars per TF (for metadata)
    warmup_bars_by_tf = {}
    max_lookback = 0
    for tf, lookback in indicator_lookbacks.items():
        warmup_bars_by_tf[tf] = compute_warmup_bars(lookback, config.warmup_multiplier)
        if lookback > max_lookback:
            max_lookback = lookback
    
    return LoadWindow(
        test_start=test_start,
        test_end=test_end,
        load_start=load_start,
        load_end=load_end,
        warmup_span=warmup_span,
        safety_buffer_span=safety_buffer,
        tail_buffer_span=tail_buffer,
        warmup_bars_by_tf=warmup_bars_by_tf,
        max_lookback_bars=max_lookback,
    )


def compute_simple_load_window(
    test_start: datetime,
    test_end: datetime,
    tf: str,
    max_lookback: int,
    warmup_multiplier: int = DEFAULT_WARMUP_MULTIPLIER,
) -> LoadWindow:
    """
    Compute load window for single-TF backtest (simplified API).
    
    Args:
        test_start: Test window start
        test_end: Test window end
        tf: Single timeframe string
        max_lookback: Maximum indicator lookback in bars
        warmup_multiplier: Warmup multiplier
        
    Returns:
        LoadWindow with computed boundaries
    """
    tf_mapping = {"htf": tf, "mtf": tf, "ltf": tf}
    indicator_lookbacks = {tf: max_lookback}
    config = WarmupConfig(
        warmup_multiplier=warmup_multiplier,
        htf_safety_closes=0,  # No HTF/MTF safety for single TF
        mtf_safety_closes=0,
    )
    
    return compute_load_window(
        test_start=test_start,
        test_end=test_end,
        tf_mapping=tf_mapping,
        indicator_lookbacks=indicator_lookbacks,
        warmup_config=config,
    )

