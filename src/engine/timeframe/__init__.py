"""
Shared timeframe management module for 3-feed + exec role system.

This module provides TFIndexManager for managing low_tf/med_tf/high_tf indices
relative to the exec role. Used by PlayEngine for both backtest and live modes.

Key Classes:
    TFIndexManager: Manages TF index tracking for 3-feed system
    TFIndexUpdate: Result dataclass with change flags and indices

Usage:
    from src.engine.timeframe import TFIndexManager, TFIndexUpdate

    manager = TFIndexManager(
        low_tf_feed=low_tf_feed,
        med_tf_feed=med_tf_feed,
        high_tf_feed=high_tf_feed,
        exec_role="low_tf",  # or "med_tf" or "high_tf"
    )

    # Each bar close:
    update = manager.update_indices(exec_ts_close, exec_idx)
    if update.high_tf_changed:
        # high_tf bar just closed - update incremental state
        ...
"""

from .index_manager import (
    TFIndexManager,
    TFIndexUpdate,
)

__all__ = [
    "TFIndexManager",
    "TFIndexUpdate",
]
