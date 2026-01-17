"""
Snapshot building module for BacktestEngine.

This module handles snapshot construction for the array-backed hot loop:
- build_snapshot_view_impl: Build RuntimeSnapshotView (O(1) creation)
- update_high_tf_med_tf_indices_impl: Update high_tf/med_tf forward-fill indices
- refresh_tf_caches_impl: Refresh TF caches with factory functions

All functions accept engine state as parameters and return snapshot-related results.
The BacktestEngine delegates to these functions, maintaining the same public API.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING

from .runtime.types import FeatureSnapshot, HistoryConfig
from .runtime.feed_store import FeedStore, MultiTFFeedStore
from .runtime.snapshot_view import RuntimeSnapshotView
from .runtime.cache import TimeframeCache
from .sim import StepResult

if TYPE_CHECKING:
    from .sim import SimulatedExchange
    from .system_config import RiskProfileConfig
    from .incremental.state import MultiTFIncrementalState
    from .feature_registry import FeatureRegistry
    from .rationalization import RationalizedState


def update_high_tf_med_tf_indices_impl(
    exec_ts_close: datetime,
    high_tf_feed: FeedStore | None,
    med_tf_feed: FeedStore | None,
    exec_feed: FeedStore,
    current_high_tf_idx: int,
    current_med_tf_idx: int,
) -> tuple[bool, bool, int, int]:
    """
    Update high_tf/med_tf forward-fill indices for RuntimeSnapshotView.

    Uses O(1) ts_close_ms_to_idx mapping from FeedStore.
    Called at each exec bar close to update forward-filled indices.

    Args:
        exec_ts_close: Current exec bar's ts_close
        high_tf_feed: high_tf FeedStore (may be None or same as exec_feed)
        med_tf_feed: med_tf FeedStore (may be None or same as exec_feed)
        exec_feed: Exec FeedStore
        current_high_tf_idx: Current high_tf index
        current_med_tf_idx: Current med_tf index

    Returns:
        Tuple of (high_tf_updated, med_tf_updated, new_high_tf_idx, new_med_tf_idx)
    """
    high_tf_updated = False
    med_tf_updated = False
    new_high_tf_idx = current_high_tf_idx
    new_med_tf_idx = current_med_tf_idx

    if high_tf_feed is not None and high_tf_feed is not exec_feed:
        # Check if this exec ts_close aligns with a high_tf close
        high_tf_idx = high_tf_feed.get_idx_at_ts_close(exec_ts_close)
        # Bounds check: index must be valid within feed data
        if high_tf_idx is not None and 0 <= high_tf_idx < len(high_tf_feed.ts_close):
            new_high_tf_idx = high_tf_idx
            high_tf_updated = True

    if med_tf_feed is not None and med_tf_feed is not exec_feed:
        # Check if this exec ts_close aligns with a med_tf close
        med_tf_idx = med_tf_feed.get_idx_at_ts_close(exec_ts_close)
        # Bounds check: index must be valid within feed data
        if med_tf_idx is not None and 0 <= med_tf_idx < len(med_tf_feed.ts_close):
            new_med_tf_idx = med_tf_idx
            med_tf_updated = True

    return high_tf_updated, med_tf_updated, new_high_tf_idx, new_med_tf_idx


def refresh_tf_caches_impl(
    ts_close: datetime,
    tf_mapping: dict[str, str],
    tf_cache: TimeframeCache,
    get_tf_features_func: Callable[[str, datetime], FeatureSnapshot],
) -> tuple[bool, bool]:
    """
    Refresh high_tf/med_tf caches at current bar close.

    Phase 3: Uses TimeframeCache.refresh_step() with factory functions
    that build FeatureSnapshots from the precomputed TF DataFrames.

    Updates are deterministic: high_tf first, then med_tf.

    Args:
        ts_close: Current exec_tf close timestamp
        tf_mapping: Dict mapping high_tf/med_tf/low_tf to timeframe strings + exec -> role
        tf_cache: TimeframeCache instance
        get_tf_features_func: Function to get features at close (tf, ts_close) -> FeatureSnapshot

    Returns:
        Tuple of (high_tf_updated, med_tf_updated) booleans
    """
    high_tf = tf_mapping["high_tf"]
    med_tf = tf_mapping["med_tf"]

    # Factory function for high_tf snapshot
    def high_tf_factory() -> FeatureSnapshot:
        return get_tf_features_func(high_tf, ts_close)

    # Factory function for med_tf snapshot
    def med_tf_factory() -> FeatureSnapshot:
        return get_tf_features_func(med_tf, ts_close)

    return tf_cache.refresh_step(ts_close, high_tf_factory, med_tf_factory)


def build_snapshot_view_impl(
    exec_idx: int,
    multi_tf_feed_store: MultiTFFeedStore,
    exec_feed: FeedStore,
    high_tf_feed: FeedStore | None,
    med_tf_feed: FeedStore | None,
    exchange: SimulatedExchange,
    multi_tf_mode: bool,
    current_high_tf_idx: int,
    current_med_tf_idx: int,
    history_config: HistoryConfig,
    is_history_ready: bool,
    risk_profile: RiskProfileConfig,
    step_result: StepResult | None = None,
    rollups: dict[str, float] | None = None,
    mark_price_override: float | None = None,
    last_price: float | None = None,
    prev_last_price: float | None = None,
    incremental_state: "MultiTFIncrementalState | None" = None,
    feature_registry: "FeatureRegistry | None" = None,
    rationalized_state: "RationalizedState | None" = None,
    quote_feed: "FeedStore | None" = None,
    quote_idx: int | None = None,
) -> RuntimeSnapshotView:
    """
    Build RuntimeSnapshotView for array-backed hot loop.

    O(1) snapshot creation - just sets indices, no data copying.

    Args:
        exec_idx: Current exec bar index
        multi_tf_feed_store: MultiTFFeedStore with all feeds
        exec_feed: Exec FeedStore
        high_tf_feed: high_tf FeedStore (may be None or same as exec_feed)
        med_tf_feed: med_tf FeedStore (may be None or same as exec_feed)
        exchange: SimulatedExchange instance
        multi_tf_mode: Whether this is true multi-TF mode
        current_high_tf_idx: Current high_tf forward-fill index
        current_med_tf_idx: Current med_tf forward-fill index
        history_config: HistoryConfig for snapshot
        is_history_ready: Whether history is ready
        risk_profile: RiskProfileConfig for mark_price_source
        step_result: Optional StepResult from exchange (for mark_price)
        rollups: Optional px.rollup.* values from 1m accumulation
        mark_price_override: Optional override for mark_price (1m evaluation)
        last_price: 1m action price (ticker close). Passed to snapshot for DSL access.
        prev_last_price: Previous 1m action price (for crossover operators).
        incremental_state: Optional MultiTFIncrementalState for structure access
        feature_registry: Optional FeatureRegistry for feature_id-based access
        rationalized_state: Optional RationalizedState for Layer 2 access
        quote_feed: Optional 1m FeedStore for arbitrary last_price offset lookups.
        quote_idx: Current 1m bar index in quote_feed.

    Returns:
        RuntimeSnapshotView ready for strategy evaluation
    """
    # Get mark_price: override > step_result > exec close
    if mark_price_override is not None:
        mark_price = mark_price_override
        mark_price_source = "1m_close"  # 1m evaluation mode
    elif step_result is not None and step_result.mark_price is not None:
        mark_price = step_result.mark_price
        mark_price_source = step_result.mark_price_source
    else:
        mark_price = float(exec_feed.close[exec_idx])
        mark_price_source = risk_profile.mark_price_source

    # For single-TF mode, high_tf/med_tf indices = exec index
    high_tf_idx = current_high_tf_idx if multi_tf_mode else exec_idx
    med_tf_idx = current_med_tf_idx if multi_tf_mode else exec_idx

    return RuntimeSnapshotView(
        feeds=multi_tf_feed_store,
        exec_idx=exec_idx,
        htf_idx=high_tf_idx if high_tf_feed is not exec_feed else None,
        mtf_idx=med_tf_idx if med_tf_feed is not exec_feed else None,
        exchange=exchange,
        mark_price=mark_price,
        mark_price_source=mark_price_source,
        history_config=history_config,
        history_ready=is_history_ready,
        rollups=rollups,
        incremental_state=incremental_state,
        feature_registry=feature_registry,
        rationalized_state=rationalized_state,
        last_price=last_price,
        prev_last_price=prev_last_price,
        quote_feed=quote_feed,
        quote_idx=quote_idx,
    )
