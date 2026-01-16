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

from .timeframe import tf_duration, tf_minutes


# Default safety buffer in number of closes per TF
DEFAULT_HIGH_TF_SAFETY_CLOSES = 10
DEFAULT_MED_TF_SAFETY_CLOSES = 20

# Default tail buffer
DEFAULT_TAIL_LOW_TF_BARS = 2
DEFAULT_TAIL_FUNDING_INTERVALS = 1
FUNDING_INTERVAL_HOURS = 8  # Bybit funding every 8 hours


@dataclass
class WarmupConfig:
    """Configuration for warmup and buffer calculations."""

    # Safety buffer: extra closed candles per TF
    high_tf_safety_closes: int = DEFAULT_HIGH_TF_SAFETY_CLOSES
    med_tf_safety_closes: int = DEFAULT_MED_TF_SAFETY_CLOSES

    # Tail buffer
    tail_low_tf_bars: int = DEFAULT_TAIL_LOW_TF_BARS
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
    warmup_bars_by_tf: dict[str, int]
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


def compute_warmup_bars(max_lookback: int) -> int:
    """
    Compute warmup bars from max indicator lookback.

    Warmup is now computed directly in FeatureSpec.warmup_bars based on
    indicator type, so this function just returns the lookback as-is.

    Args:
        max_lookback: Maximum indicator lookback in bars

    Returns:
        Number of warmup bars needed
    """
    if max_lookback <= 0:
        return 0
    return max_lookback


def compute_warmup_span(
    tf_mapping: dict[str, str],
    indicator_lookbacks: dict[str, int],
    warmup_config: WarmupConfig | None = None,
) -> timedelta:
    """
    Compute total warmup span from TF mapping and indicator lookbacks.

    Formula: warmup_span = max(warmup_bars_tf * tf_duration(tf) for each TF)

    Args:
        tf_mapping: Dict with high_tf, med_tf, low_tf -> tf string
        indicator_lookbacks: Dict with tf -> max lookback bars for that TF
        warmup_config: Optional warmup configuration

    Returns:
        Maximum warmup span as timedelta
    """
    config = warmup_config or WarmupConfig()
    
    max_span = timedelta(0)

    for role, tf in tf_mapping.items():
        lookback = indicator_lookbacks.get(tf, 0)
        warmup_bars = compute_warmup_bars(lookback)
        span = warmup_bars * tf_duration(tf)

        if span > max_span:
            max_span = span

    return max_span


def compute_safety_buffer_span(
    tf_mapping: dict[str, str],
    warmup_config: WarmupConfig | None = None,
) -> timedelta:
    """
    Compute safety buffer span (extra closes to ensure cache readiness).

    Args:
        tf_mapping: Dict with high_tf, med_tf, low_tf -> tf string
        warmup_config: Optional warmup configuration

    Returns:
        Safety buffer as timedelta
    """
    config = warmup_config or WarmupConfig()

    high_tf_buffer = config.high_tf_safety_closes * tf_duration(tf_mapping["high_tf"])
    med_tf_buffer = config.med_tf_safety_closes * tf_duration(tf_mapping["med_tf"])

    # Use the larger buffer
    return max(high_tf_buffer, med_tf_buffer)


def compute_tail_buffer_span(
    tf_mapping: dict[str, str],
    warmup_config: WarmupConfig | None = None,
) -> timedelta:
    """
    Compute tail buffer span (extra bars at end for funding).

    Args:
        tf_mapping: Dict with high_tf, med_tf, low_tf -> tf string
        warmup_config: Optional warmup configuration

    Returns:
        Tail buffer as timedelta
    """
    config = warmup_config or WarmupConfig()

    low_tf_buffer = config.tail_low_tf_bars * tf_duration(tf_mapping["low_tf"])
    funding_buffer = config.tail_funding_intervals * timedelta(hours=FUNDING_INTERVAL_HOURS)
    
    return low_tf_buffer + funding_buffer


def compute_load_window(
    test_start: datetime,
    test_end: datetime,
    tf_mapping: dict[str, str],
    indicator_lookbacks: dict[str, int],
    warmup_config: WarmupConfig | None = None,
) -> LoadWindow:
    """
    Compute the full load window for a backtest run.
    
    Formula:
        load_start = test_start - warmup_span - safety_buffer
        load_end = test_end + tail_buffer
    
    Args:
        test_start: Test window start (from config)
        test_end: Test window end (from config)
        tf_mapping: Dict with high_tf, med_tf, low_tf -> tf string
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
        warmup_bars_by_tf[tf] = compute_warmup_bars(lookback)
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
) -> LoadWindow:
    """
    Compute load window for single-TF backtest (simplified API).

    Args:
        test_start: Test window start
        test_end: Test window end
        tf: Single timeframe string
        max_lookback: Maximum indicator lookback in bars

    Returns:
        LoadWindow with computed boundaries
    """
    tf_mapping = {"high_tf": tf, "med_tf": tf, "low_tf": tf}
    indicator_lookbacks = {tf: max_lookback}
    config = WarmupConfig(
        high_tf_safety_closes=0,  # No HighTF/MedTF safety for single TF
        med_tf_safety_closes=0,
    )

    return compute_load_window(
        test_start=test_start,
        test_end=test_end,
        tf_mapping=tf_mapping,
        indicator_lookbacks=indicator_lookbacks,
        warmup_config=config,
    )


# =============================================================================
# Simple API for Preflight-computed warmup
# =============================================================================
# The functions above work with indicator lookbacks to compute warmup.
# The functions below work with pre-computed warmup_bars_by_role from Preflight.

@dataclass
class DataWindow:
    """Simple data window computed from Preflight warmup requirements."""
    
    # Requested test window
    test_start: datetime
    test_end: datetime
    
    # Computed data window (extended for warmup)
    data_start: datetime
    data_end: datetime
    
    # Component spans (for debugging)
    warmup_span: timedelta
    htf_warmup_span: timedelta | None = None
    
    def to_dict(self) -> dict:
        """Convert to dict for serialization."""
        result = {
            "test_start": self.test_start.isoformat(),
            "test_end": self.test_end.isoformat(),
            "data_start": self.data_start.isoformat(),
            "data_end": self.data_end.isoformat(),
            "warmup_span_seconds": self.warmup_span.total_seconds(),
        }
        if self.htf_warmup_span:
            result["htf_warmup_span_seconds"] = self.htf_warmup_span.total_seconds()
        return result


def compute_data_window(
    window_start: datetime,
    window_end: datetime,
    warmup_bars_by_role: dict[str, int],
    tf_by_role: dict[str, str],
    safety_buffer_bars: int = 0,
) -> DataWindow:
    """
    Compute data window from Preflight-computed warmup requirements.
    
    This is the canonical function for computing data fetch boundaries.
    Both Preflight and Engine should use this for consistency.
    
    Formula:
        data_start = min(
            window_start - (exec_warmup_bars + safety_buffer) * exec_tf_duration,
            window_start - (htf_warmup_bars + safety_buffer) * htf_tf_duration,  # if HTF exists
        )
        data_end = window_end
    
    Args:
        window_start: Test window start (evaluation start)
        window_end: Test window end
        warmup_bars_by_role: Dict with role -> warmup bars (from Preflight)
        tf_by_role: Dict with role -> timeframe string
        safety_buffer_bars: Extra bars buffer (default 0)
        
    Returns:
        DataWindow with computed boundaries
    """
    # Compute exec TF warmup span
    exec_tf = tf_by_role.get('exec') or tf_by_role.get('ltf')
    if not exec_tf:
        raise ValueError("tf_by_role must contain 'exec' or 'ltf' key")
    
    exec_warmup_bars = warmup_bars_by_role.get('exec', 0)
    exec_tf_delta = tf_duration(exec_tf)
    exec_warmup_span = exec_tf_delta * (exec_warmup_bars + safety_buffer_bars)
    exec_data_start = window_start - exec_warmup_span
    
    # Compute MTF warmup span if present
    mtf_warmup_span = None
    mtf_data_start = exec_data_start

    mtf_tf = tf_by_role.get('mtf')
    if mtf_tf and mtf_tf != exec_tf:
        mtf_warmup_bars = warmup_bars_by_role.get('mtf', 0)
        if mtf_warmup_bars > 0:
            mtf_tf_delta = tf_duration(mtf_tf)
            mtf_warmup_span = mtf_tf_delta * (mtf_warmup_bars + safety_buffer_bars)
            mtf_data_start = window_start - mtf_warmup_span

    # Compute HTF warmup span if present
    htf_warmup_span = None
    htf_data_start = exec_data_start

    htf_tf = tf_by_role.get('htf')
    if htf_tf and htf_tf != exec_tf:
        htf_warmup_bars = warmup_bars_by_role.get('htf', 0)
        if htf_warmup_bars > 0:
            htf_tf_delta = tf_duration(htf_tf)
            htf_warmup_span = htf_tf_delta * (htf_warmup_bars + safety_buffer_bars)
            htf_data_start = window_start - htf_warmup_span

    # Use the earliest start (largest warmup wins across all TFs)
    data_start = min(exec_data_start, mtf_data_start, htf_data_start)
    
    return DataWindow(
        test_start=window_start,
        test_end=window_end,
        data_start=data_start,
        data_end=window_end,
        warmup_span=exec_warmup_span,
        htf_warmup_span=htf_warmup_span,
    )


def compute_warmup_start_simple(
    window_start: datetime,
    warmup_bars: int,
    tf: str,
    safety_buffer_bars: int = 0,
) -> datetime:
    """
    Compute the data start timestamp for a single TF.
    
    This is a convenience function for single-TF cases.
    
    Args:
        window_start: Test window start
        warmup_bars: Number of warmup bars
        tf: Timeframe string
        safety_buffer_bars: Extra bars buffer
        
    Returns:
        Data start timestamp
    """
    tf_delta = tf_duration(tf)
    warmup_span = tf_delta * (warmup_bars + safety_buffer_bars)
    return window_start - warmup_span
