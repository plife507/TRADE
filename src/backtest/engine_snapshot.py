"""
Snapshot building module for BacktestEngine.

This module handles snapshot construction for the array-backed hot loop:
- build_snapshot_view_impl: Build RuntimeSnapshotView (O(1) creation)
- update_htf_mtf_indices_impl: Update HTF/MTF forward-fill indices
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


def update_htf_mtf_indices_impl(
    exec_ts_close: datetime,
    htf_feed: FeedStore | None,
    mtf_feed: FeedStore | None,
    exec_feed: FeedStore,
    current_htf_idx: int,
    current_mtf_idx: int,
) -> tuple[bool, bool, int, int]:
    """
    Update HTF/MTF forward-fill indices for RuntimeSnapshotView.

    Uses O(1) ts_close_ms_to_idx mapping from FeedStore.
    Called at each exec bar close to update forward-filled indices.

    Args:
        exec_ts_close: Current exec bar's ts_close
        htf_feed: HTF FeedStore (may be None or same as exec_feed)
        mtf_feed: MTF FeedStore (may be None or same as exec_feed)
        exec_feed: Exec FeedStore
        current_htf_idx: Current HTF index
        current_mtf_idx: Current MTF index

    Returns:
        Tuple of (htf_updated, mtf_updated, new_htf_idx, new_mtf_idx)
    """
    htf_updated = False
    mtf_updated = False
    new_htf_idx = current_htf_idx
    new_mtf_idx = current_mtf_idx

    if htf_feed is not None and htf_feed is not exec_feed:
        # Check if this exec ts_close aligns with an HTF close
        htf_idx = htf_feed.get_idx_at_ts_close(exec_ts_close)
        # Bounds check: index must be valid within feed data
        if htf_idx is not None and 0 <= htf_idx < len(htf_feed.ts_close):
            new_htf_idx = htf_idx
            htf_updated = True

    if mtf_feed is not None and mtf_feed is not exec_feed:
        # Check if this exec ts_close aligns with an MTF close
        mtf_idx = mtf_feed.get_idx_at_ts_close(exec_ts_close)
        # Bounds check: index must be valid within feed data
        if mtf_idx is not None and 0 <= mtf_idx < len(mtf_feed.ts_close):
            new_mtf_idx = mtf_idx
            mtf_updated = True

    return htf_updated, mtf_updated, new_htf_idx, new_mtf_idx


def refresh_tf_caches_impl(
    ts_close: datetime,
    tf_mapping: dict[str, str],
    tf_cache: TimeframeCache,
    get_tf_features_func: Callable[[str, datetime], FeatureSnapshot],
) -> tuple[bool, bool]:
    """
    Refresh HTF/MTF caches at current bar close.

    Phase 3: Uses TimeframeCache.refresh_step() with factory functions
    that build FeatureSnapshots from the precomputed TF DataFrames.

    Updates are deterministic: HTF first, then MTF.

    Args:
        ts_close: Current LTF close timestamp
        tf_mapping: Dict mapping htf/mtf/ltf to timeframe strings
        tf_cache: TimeframeCache instance
        get_tf_features_func: Function to get features at close (tf, ts_close) -> FeatureSnapshot

    Returns:
        Tuple of (high_tf_updated, med_tf_updated) booleans
    """
    high_tf = tf_mapping["high_tf"]
    med_tf = tf_mapping["med_tf"]

    # Factory function for HighTF snapshot
    def htf_factory() -> FeatureSnapshot:
        return get_tf_features_func(high_tf, ts_close)

    # Factory function for MedTF snapshot
    def mtf_factory() -> FeatureSnapshot:
        return get_tf_features_func(med_tf, ts_close)

    return tf_cache.refresh_step(ts_close, htf_factory, mtf_factory)


def build_snapshot_view_impl(
    exec_idx: int,
    multi_tf_feed_store: MultiTFFeedStore,
    exec_feed: FeedStore,
    htf_feed: FeedStore | None,
    mtf_feed: FeedStore | None,
    exchange: SimulatedExchange,
    multi_tf_mode: bool,
    current_htf_idx: int,
    current_mtf_idx: int,
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
        htf_feed: HTF FeedStore (may be None or same as exec_feed)
        mtf_feed: MTF FeedStore (may be None or same as exec_feed)
        exchange: SimulatedExchange instance
        multi_tf_mode: Whether this is true multi-TF mode
        current_htf_idx: Current HTF forward-fill index
        current_mtf_idx: Current MTF forward-fill index
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

    # For single-TF mode, HTF/MTF indices = exec index
    htf_idx = current_htf_idx if multi_tf_mode else exec_idx
    mtf_idx = current_mtf_idx if multi_tf_mode else exec_idx

    return RuntimeSnapshotView(
        feeds=multi_tf_feed_store,
        exec_idx=exec_idx,
        htf_idx=htf_idx if htf_feed is not exec_feed else None,
        mtf_idx=mtf_idx if mtf_feed is not exec_feed else None,
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
