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
- QuoteState: 1m-driven price feed for quote/ticker proxy

Submodules:
- types: Core runtime types (Bar, RuntimeSnapshot, etc.)
- timeframe: Timeframe utilities (tf_duration)
- windowing: Load window computation
- data_health: Data health checks and gap detection
- snapshot_builder: RuntimeSnapshot construction
- snapshot_view: View-based snapshot (performance)
- feed_store: Precomputed array storage
- cache: Multi-timeframe feature caching
- quote_state: 1m price feed for px.last/px.mark

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
from .indicator_metadata import (
    IndicatorMetadata,
    canonicalize_params,
    compute_feature_spec_id,
    find_first_valid_idx,
    get_pandas_ta_version,
    get_code_version,
    validate_metadata_coverage,
    validate_feature_spec_ids,
    MetadataValidationResult,
    export_metadata_jsonl,
    export_metadata_json,
    export_metadata_csv,
)
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
from .quote_state import (
    QuoteState,
    QUOTE_KEYS,
    quote_to_packet_dict,
)
from .rollup_bucket import (
    ExecRollupBucket,
    ROLLUP_KEYS,
    create_empty_rollup_dict,
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
    # Indicator metadata (provenance tracking)
    "IndicatorMetadata",
    "canonicalize_params",
    "compute_feature_spec_id",
    "find_first_valid_idx",
    "get_pandas_ta_version",
    "get_code_version",
    "validate_metadata_coverage",
    "validate_feature_spec_ids",
    "MetadataValidationResult",
    "export_metadata_jsonl",
    "export_metadata_json",
    "export_metadata_csv",
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
    # Quote state (1m price feed)
    "QuoteState",
    "QUOTE_KEYS",
    "quote_to_packet_dict",
    # Rollup bucket (1m aggregates)
    "ExecRollupBucket",
    "ROLLUP_KEYS",
    "create_empty_rollup_dict",
]

