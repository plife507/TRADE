"""
Backtest runtime module.

Provides the core runtime types and utilities for backtesting:
- Bar: Canonical OHLCV bar with explicit ts_open/ts_close
- RuntimeSnapshot: Point-in-time state visible to strategy
- RuntimeSnapshotView: View-based snapshot for hot-loop performance
- FeatureSnapshot: Indicator features per timeframe
- ExchangeState: Immutable exchange state snapshot
- HistoryConfig: Configuration for snapshot history depth
- FeedStore: Precomputed arrays for O(1) access

Submodules:
- types: Core runtime types (Bar, RuntimeSnapshot, etc.)
- timeframe: Timeframe utilities (tf_duration)
- windowing: Load window computation
- data_health: Data health checks and gap detection
- snapshot_builder: RuntimeSnapshot construction
- snapshot_view: View-based snapshot (performance)
- feed_store: Precomputed array storage
- cache: Multi-timeframe feature caching

PERFORMANCE CONTRACT:
- Snapshot creation is O(1) per bar
- All indicator access is O(1) array lookup
- No DataFrame operations in hot loop
- History via index offset (deque for rolling windows)
"""

from .types import (
    Bar,
    FeatureSnapshot,
    ExchangeState,
    RuntimeSnapshot,
    HistoryConfig,
    DEFAULT_HISTORY_CONFIG,
)

from .feed_store import FeedStore, MultiTFFeedStore
from .snapshot_view import RuntimeSnapshotView, TFContext
from .preflight import (
    PreflightStatus,
    GapInfo,
    TFPreflightResult,
    PreflightReport,
    ToolCallRecord,
    AutoSyncConfig,
    AutoSyncResult,
    parse_tf_to_minutes,
    calculate_warmup_start,
    validate_tf_data,
    run_preflight_gate,
)

__all__ = [
    # Core types
    "Bar",
    "FeatureSnapshot",
    "ExchangeState",
    "RuntimeSnapshot",
    "HistoryConfig",
    "DEFAULT_HISTORY_CONFIG",
    # View-based (performance)
    "FeedStore",
    "MultiTFFeedStore",
    "RuntimeSnapshotView",
    "TFContext",
    # Preflight gate (Phase 7.5)
    "PreflightStatus",
    "GapInfo",
    "TFPreflightResult",
    "PreflightReport",
    "ToolCallRecord",
    "AutoSyncConfig",
    "AutoSyncResult",
    "parse_tf_to_minutes",
    "calculate_warmup_start",
    "validate_tf_data",
    "run_preflight_gate",
]

