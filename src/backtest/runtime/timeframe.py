"""
Timeframe utilities for the backtest runtime.

Provides timeframe duration calculation and validation.
Uses TF_MINUTES from the data store as the source of truth.

Note: Close detection is data-driven (via close_ts maps), not modulo-based.
This module only provides duration helpers for warmup/buffer calculations.
"""

from datetime import timedelta
from typing import Dict

# Import TF_MINUTES from data store (canonical source)
from ...data.historical_data_store import TF_MINUTES


def tf_duration(tf: str) -> timedelta:
    """
    Get the duration of a timeframe as a timedelta.
    
    Args:
        tf: Timeframe string (e.g., "5m", "1h", "D", "W")
        
    Returns:
        Timedelta representing the timeframe duration
        
    Raises:
        ValueError: If timeframe is not recognized
    """
    tf_key = tf.lower()
    
    if tf_key not in TF_MINUTES:
        raise ValueError(
            f"Unknown timeframe '{tf}'. "
            f"Supported: {list(TF_MINUTES.keys())}"
        )
    
    minutes = TF_MINUTES[tf_key]
    return timedelta(minutes=minutes)


def tf_minutes(tf: str) -> int:
    """
    Get the duration of a timeframe in minutes.
    
    Args:
        tf: Timeframe string
        
    Returns:
        Duration in minutes
        
    Raises:
        ValueError: If timeframe is not recognized
    """
    tf_key = tf.lower()
    
    if tf_key not in TF_MINUTES:
        raise ValueError(
            f"Unknown timeframe '{tf}'. "
            f"Supported: {list(TF_MINUTES.keys())}"
        )
    
    return TF_MINUTES[tf_key]


def validate_tf_mapping(tf_mapping: Dict[str, str]) -> None:
    """
    Validate a timeframe mapping (htf/mtf/ltf -> tf string).
    
    Ensures all specified timeframes are valid and HTF >= MTF >= LTF.
    
    Args:
        tf_mapping: Dict with keys htf, mtf, ltf and tf string values
        
    Raises:
        ValueError: If mapping is invalid or timeframes don't follow hierarchy
    """
    required_keys = {"htf", "mtf", "ltf"}
    missing = required_keys - set(tf_mapping.keys())
    if missing:
        raise ValueError(f"Missing required tf_mapping keys: {missing}")
    
    # Validate each timeframe exists
    for role, tf in tf_mapping.items():
        if tf.lower() not in TF_MINUTES:
            raise ValueError(
                f"Unknown timeframe '{tf}' for role '{role}'. "
                f"Supported: {list(TF_MINUTES.keys())}"
            )
    
    # Validate hierarchy: HTF >= MTF >= LTF (in minutes)
    htf_min = tf_minutes(tf_mapping["htf"])
    mtf_min = tf_minutes(tf_mapping["mtf"])
    ltf_min = tf_minutes(tf_mapping["ltf"])
    
    if not (htf_min >= mtf_min >= ltf_min):
        raise ValueError(
            f"Invalid tf_mapping hierarchy: HTF ({tf_mapping['htf']}={htf_min}m) "
            f"must be >= MTF ({tf_mapping['mtf']}={mtf_min}m) "
            f"must be >= LTF ({tf_mapping['ltf']}={ltf_min}m)"
        )


def get_supported_timeframes() -> Dict[str, int]:
    """
    Get all supported timeframes and their durations in minutes.
    
    Returns:
        Dict of tf string -> minutes
    """
    return dict(TF_MINUTES)

