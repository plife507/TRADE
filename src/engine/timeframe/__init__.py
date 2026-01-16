"""
Shared timeframe management module for unified engine.

This module provides the HTFIndexManager for managing HTF/MTF forward-fill
indices across both BacktestEngine and PlayEngine, ensuring identical
forward-fill behavior without duplicate code.

Key Classes:
    HTFIndexManager: Manages HTF/MTF index tracking with forward-fill logic

Usage:
    from src.engine.timeframe import HTFIndexManager, HTFIndexUpdate

    manager = HTFIndexManager(
        htf_feed=htf_feed,
        mtf_feed=mtf_feed,
        exec_feed=exec_feed,
    )

    # Each bar close:
    update = manager.update_indices(exec_ts_close)
    if update.htf_changed:
        # HTF bar just closed - update incremental state
        ...
"""

from .index_manager import HTFIndexManager, HTFIndexUpdate

__all__ = ["HTFIndexManager", "HTFIndexUpdate"]
