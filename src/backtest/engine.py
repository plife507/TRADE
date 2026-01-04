"""
Backtest engine.

Main orchestrator for deterministic backtesting:
1. Load candles from DuckDB (multi-TF support)
2. Compute indicators per TF DataFrame (vectorized, outside hot loop)
3. Build FeedStores for O(1) array access in hot loop
4. Run bar-by-bar simulation with RuntimeSnapshotView (no pandas in loop)
5. Generate structured BacktestResult with metrics
6. Write artifacts (trades.csv, equity.csv, result.json)

ARCHITECTURE (Array-Backed Hot Loop):
- FeedStore: Precomputed numpy arrays for OHLCV + indicators
- RuntimeSnapshotView: O(1) array-backed snapshot (no materialization)
- No pandas ops in hot loop (no df.iloc, no row scanning)
- All feature access via get_feature(tf_role, indicator_key, offset)

MODULAR STRUCTURE (Phase 1 Refactor):
- engine_data_prep.py: Data loading and preparation
- engine.py: Main orchestrator (this file)

Usage:
    from src.backtest import BacktestEngine, load_system_config

    config = load_system_config("SOLUSDT_5m_ema_rsi_atr_pure", "hygiene")
    engine = BacktestEngine(config, "hygiene")
    result = engine.run(strategy)
"""

from collections.abc import Callable
import json
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
import uuid

# Import dataclasses from engine_data_prep module
from .engine_data_prep import (
    PreparedFrame,
    MultiTFPreparedFrames,
    prepare_backtest_frame_impl,
    prepare_multi_tf_frames_impl,
    load_data_impl,
    load_1m_data_impl,
    timeframe_to_timedelta,
    get_tf_features_at_close_impl,
)

# Import from engine_feed_builder module
from .engine_feed_builder import (
    build_feed_stores_impl,
    build_quote_feed_impl,
    get_quote_at_exec_close,
    build_structures_into_feed,
)

# Import from engine_snapshot module
from .engine_snapshot import (
    build_snapshot_view_impl,
    update_htf_mtf_indices_impl,
    refresh_tf_caches_impl,
)

# Import from engine_history module
from .engine_history import HistoryManager, parse_history_config_impl

# Import from engine_stops module
from .engine_stops import (
    StopCheckResult,
    check_all_stop_conditions,
    handle_terminal_stop,
)

# Import from engine_artifacts module
from .engine_artifacts import calculate_drawdowns_impl, write_artifacts_impl

# Import factory functions from engine_factory module
# These are re-exported for backward compatibility
from .engine_factory import (
    run_backtest,
    create_engine_from_idea_card,
    run_engine_with_idea_card,
)

from .types import (
    Trade,
    EquityPoint,
    AccountCurvePoint,
    BacktestMetrics,
    BacktestResult,
    BacktestRunConfigEcho,
    StrategyInstanceSummary,
    WindowConfig,
    StopReason,
)
from .runtime.types import (
    Bar as CanonicalBar,
    FeatureSnapshot,
    RuntimeSnapshot,
    HistoryConfig,
    DEFAULT_HISTORY_CONFIG,
    create_not_ready_feature_snapshot,
)
from .runtime.timeframe import tf_duration, tf_minutes, validate_tf_mapping, ceil_to_tf_close
from .runtime.cache import TimeframeCache
from .runtime.feed_store import FeedStore, MultiTFFeedStore
from .runtime.snapshot_view import RuntimeSnapshotView
from .runtime.rollup_bucket import ExecRollupBucket, create_empty_rollup_dict
from .runtime.state_tracker import StateTracker, create_state_tracker
from .runtime.quote_state import QuoteState
from .system_config import (
    SystemConfig,
    load_system_config,
    RiskProfileConfig,
    validate_usdt_pair,
    validate_margin_mode_isolated,
    validate_quote_ccy_and_instrument_type,
)
from .indicators import (
    apply_feature_spec_indicators,
    get_warmup_from_specs,
    get_max_warmup_from_specs_by_role,
    get_required_indicator_columns_from_specs,
    find_first_valid_bar,
)
from .sim import SimulatedExchange, ExecutionConfig, StepResult
from .simulated_risk_manager import SimulatedRiskManager
from .risk_policy import RiskPolicy, create_risk_policy, RiskDecision
from .metrics import compute_backtest_metrics

# Incremental state imports (Phase 6)
from .incremental.base import BarData
from .incremental.state import MultiTFIncrementalState
from .incremental.registry import list_structure_types

from ..core.risk_manager import Signal
from ..data.historical_data_store import get_historical_store, TF_MINUTES
from ..utils.logger import get_logger

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .feature_registry import FeatureRegistry
    from .idea_card import IdeaCard


class BacktestEngine:
    """
    Deterministic backtest engine.
    
    Execution model:
    - Strategy evaluates at bar close
    - Entry orders fill at next bar open
    - TP/SL checked within each bar with deterministic tie-break
    
    The engine is config-driven: all parameters come from SystemConfig.
    Uses SimulatedRiskManager for position sizing based on risk profile.
    
    Phase 3: Multi-TF support with data-driven caching.
    - Supports explicit tf_mapping (htf, mtf, ltf)
    - Uses TimeframeCache for HTF/MTF carry-forward
    - Data-driven close detection via close_ts maps
    - Readiness gate blocks trading until all TF caches are ready
    """
    
    def __init__(
        self,
        config: SystemConfig,
        window_name: str = "hygiene",
        run_dir: Path | None = None,
        tf_mapping: dict[str, str] | None = None,
        on_snapshot: Callable[["RuntimeSnapshotView", int, int, int], None] | None = None,
        record_state_tracking: bool = False,
        feature_registry: "FeatureRegistry | None" = None,
    ):
        """
        Initialize backtest engine.

        Args:
            config: System configuration (with resolved risk profile)
            window_name: Window to use ("hygiene" or "test")
            run_dir: Optional directory for writing artifacts
            tf_mapping: Optional dict mapping htf/mtf/ltf to timeframe strings.
                        If None, single-TF mode (all roles = config.tf).
            on_snapshot: Optional callback invoked after snapshot build, before strategy.
                        Signature: (snapshot, exec_idx, htf_idx, mtf_idx) -> None
                        Used for Phase 4 plumbing parity audit.
            record_state_tracking: Optional flag to enable Stage 7 state tracking.
                        When True, records signal/action/gate state per bar.
                        Record-only: does not affect trade outcomes.
            feature_registry: Optional FeatureRegistry from IdeaCard.
                        When set, provides unified access to features on any TF.
                        Replaces role-based tf_mapping approach.
        """
        self.config = config

        # Feature Registry (new architecture - replaces role-based TF mapping)
        self._feature_registry = feature_registry or config.feature_registry
        self.window_name = window_name
        self.window = config.get_window(window_name)
        self.run_dir = Path(run_dir) if run_dir else None
        
        self.logger = get_logger()
        
        # =====================================================================
        # Mode Lock Validations (defense in depth)
        # These are also validated at config load time, but we re-validate here
        # to catch any direct instantiation with invalid configs.
        # =====================================================================
        if config.symbol:
            validate_usdt_pair(config.symbol)
        validate_margin_mode_isolated(config.risk_profile.margin_mode)
        validate_quote_ccy_and_instrument_type(
            config.risk_profile.quote_ccy,
            config.risk_profile.instrument_type,
        )
        
        # Create risk policy for signal filtering (if risk_mode=rules)
        self.risk_policy = create_risk_policy(
            config.risk_mode,
            config.risk_profile,
        )
        
        # Create simulated risk manager for sizing
        self.risk_manager = SimulatedRiskManager(config.risk_profile)
        
        # Execution config from params (slippage only; fees come from risk_profile)
        params = config.params
        self.execution_config = ExecutionConfig(
            slippage_bps=params.get("slippage_bps", 5.0),
        )
        
        # State
        self._data: pd.DataFrame | None = None
        self._prepared_frame: PreparedFrame | None = None
        self._mtf_frames: MultiTFPreparedFrames | None = None  # Phase 3
        self._exchange: SimulatedExchange | None = None
        self._equity_curve: list[EquityPoint] = []
        self._started_at: datetime | None = None
        
        # Phase 3: Multi-TF configuration
        # Default to single-TF mode if no explicit mapping provided
        if tf_mapping is None:
            self._tf_mapping = {"htf": config.tf, "mtf": config.tf, "ltf": config.tf}
            self._multi_tf_mode = False
        else:
            # Validate the mapping
            validate_tf_mapping(tf_mapping)
            self._tf_mapping = tf_mapping
            self._multi_tf_mode = tf_mapping["htf"] != tf_mapping["ltf"] or tf_mapping["mtf"] != tf_mapping["ltf"]
        
        # Phase 1: History management (delegated to HistoryManager)
        # Parse history config from system config (if present)
        self._history_config = parse_history_config_impl(config)
        self._history_manager = HistoryManager(self._history_config)

        # Phase 3: TimeframeCache for HTF/MTF carry-forward
        self._tf_cache = TimeframeCache()

        # Phase 3: Indicator DataFrames per TF (populated in prepare_multi_tf_frames)
        self._htf_df: pd.DataFrame | None = None
        self._mtf_df: pd.DataFrame | None = None
        self._ltf_df: pd.DataFrame | None = None

        # Phase 3: Readiness gate tracking
        self._warmup_complete = False
        self._first_ready_bar_index: int | None = None

        # Array-backed hot loop: FeedStores for O(1) array access
        self._multi_tf_feed_store: MultiTFFeedStore | None = None
        self._exec_feed: FeedStore | None = None
        self._htf_feed: FeedStore | None = None
        self._mtf_feed: FeedStore | None = None

        # Phase 3: 1m Quote Feed + Rollup Bucket
        self._quote_feed: FeedStore | None = None
        self._rollup_bucket: ExecRollupBucket = ExecRollupBucket()
        self._current_rollups: dict[str, float] = create_empty_rollup_dict()
        self._last_1m_idx: int = -1  # Track last processed 1m bar index

        # Track forward-fill indices for all TFs slower than exec.
        # These stay constant until their respective TF bar closes.
        # See _update_htf_mtf_indices() for forward-fill semantics.
        self._current_htf_idx: int = 0
        self._current_mtf_idx: int = 0
        
        # Phase 4: Optional snapshot callback for plumbing parity audit
        # Invoked after snapshot build, before strategy evaluation
        self._on_snapshot = on_snapshot

        # Stage 7: Optional state tracking (record-only)
        # When enabled, tracks signal/action/gate state per bar
        self._record_state_tracking = record_state_tracking
        self._state_tracker: StateTracker | None = None
        if record_state_tracking:
            # RiskProfileConfig.max_drawdown_pct is always defined (default: 100.0)
            self._state_tracker = create_state_tracker(
                warmup_bars=0,  # Will be set after prepare_backtest_frame
                max_positions=1,  # Single position per symbol
                max_drawdown_pct=config.risk_profile.max_drawdown_pct,
                cooldown_bars=0,
            )
            # P2-12: Ensure clean state on init (reset clears any stale state)
            self._state_tracker.reset()

        # IdeaCard reference (set by factory, None if created directly)
        # Must be initialized here to avoid AttributeError in _build_structures_into_exec_feed()
        self._idea_card: "IdeaCard | None" = None

        # Phase 6: Incremental state for structure detection (swing, trend, zone, etc.)
        # Built from IdeaCard structure specs after engine creation
        self._incremental_state: MultiTFIncrementalState | None = None

        tf_mode_str = "multi-TF" if self._multi_tf_mode else "single-TF"
        self.logger.info(
            f"BacktestEngine initialized: {config.system_id} / {window_name} / "
            f"risk_mode={config.risk_mode} / initial_equity={config.risk_profile.initial_equity} / "
            f"mode={tf_mode_str} / tf_mapping={self._tf_mapping}"
        )
    
    def _update_history(
        self,
        bar: CanonicalBar,
        features_exec: FeatureSnapshot,
        htf_updated: bool,
        mtf_updated: bool,
        features_htf: FeatureSnapshot | None,
        features_mtf: FeatureSnapshot | None,
    ) -> None:
        """
        Update rolling history windows.

        Delegates to HistoryManager.update().

        Args:
            bar: Current exec-TF bar
            features_exec: Current exec-TF features
            htf_updated: Whether HTF cache was updated this step
            mtf_updated: Whether MTF cache was updated this step
            features_htf: Current HTF features (if updated)
            features_mtf: Current MTF features (if updated)
        """
        self._history_manager.update(
            bar=bar,
            features_exec=features_exec,
            htf_updated=htf_updated,
            mtf_updated=mtf_updated,
            features_htf=features_htf,
            features_mtf=features_mtf,
        )

    def _is_history_ready(self) -> bool:
        """
        Check if required history windows are filled.

        Delegates to HistoryManager.is_ready().

        Returns:
            True if all configured history windows are at required depth,
            or if no history is configured.
        """
        return self._history_manager.is_ready()

    def _build_incremental_state(self) -> MultiTFIncrementalState | None:
        """
        Build incremental state from Feature Registry structure specs.

        Creates MultiTFIncrementalState for O(1) structure access
        in the hot loop. The incremental state is updated bar-by-bar.

        Uses Feature Registry to get structure features and groups them by TF.

        Returns:
            MultiTFIncrementalState if registry has structures, None otherwise.

        Raises:
            ValueError: If structure specs are invalid (fail-loud with fix suggestions).
        """
        # Prefer Feature Registry if available
        registry = self._feature_registry
        if registry is None and self._idea_card is not None:
            registry = self._idea_card.feature_registry

        if registry is None:
            return None

        # Get all structure features from registry
        structures = registry.get_structures()
        if not structures:
            self.logger.debug("No structure features in registry, skipping incremental state build")
            return None

        exec_tf = registry.execution_tf

        # Group structures by TF
        exec_specs: list[dict] = []
        htf_configs: dict[str, list[dict]] = {}

        for feature in structures:
            spec_dict = {
                "type": feature.structure_type,
                "key": feature.id,
                "params": dict(feature.params) if feature.params else {},
            }
            if feature.depends_on:
                spec_dict["depends_on"] = dict(feature.depends_on)

            if feature.tf == exec_tf:
                exec_specs.append(spec_dict)
            else:
                # HTF structure
                if feature.tf not in htf_configs:
                    htf_configs[feature.tf] = []
                htf_configs[feature.tf].append(spec_dict)

        # Create incremental state
        state = MultiTFIncrementalState(
            exec_tf=exec_tf,
            exec_specs=exec_specs,
            htf_configs=htf_configs if htf_configs else None,
        )

        self.logger.info(
            f"Built incremental state: "
            f"exec_structures={state.exec.list_structures()}, "
            f"htfs={state.list_htfs()}"
        )

        return state

    def _get_history_tuples(self) -> tuple:
        """
        Get immutable history tuples for snapshot.

        Delegates to HistoryManager.get_tuples().

        Returns:
            Tuple of (bars_exec, features_exec, features_htf, features_mtf)
        """
        return self._history_manager.get_tuples()
    
    def _timeframe_to_timedelta(self, tf: str) -> timedelta:
        """
        Convert timeframe string to timedelta.

        Raises ValueError on unknown timeframe (fail-fast, no silent defaults).

        Delegates to engine_data_prep.timeframe_to_timedelta().
        """
        return timeframe_to_timedelta(tf)
    
    def prepare_backtest_frame(self) -> PreparedFrame:
        """
        Prepare the backtest DataFrame with proper warm-up.

        This method:
        1. Validates symbol and mode locks (fail fast before data fetch)
        2. Computes warmup_bars based on strategy params and multiplier
        3. Extends the query range by warmup_span before window_start
        4. Loads extended DataFrame from DuckDB
        5. Applies indicators to the full extended DataFrame
        6. Finds the first bar where all required indicators are valid
        7. Sets simulation start to max(first_valid_bar, window_start)
        8. Returns PreparedFrame with all metadata

        Delegates to engine_data_prep.prepare_backtest_frame_impl().

        Returns:
            PreparedFrame with DataFrame and metadata

        Raises:
            ValueError: If not enough data for warm-up + window, or invalid config
        """
        prepared = prepare_backtest_frame_impl(
            config=self.config,
            window=self.window,
            logger=self.logger,
        )

        self._prepared_frame = prepared
        self._data = prepared.df

        return prepared
    
    def load_data(self) -> pd.DataFrame:
        """
        Load and validate candle data from DuckDB.

        Delegates to engine_data_prep.load_data_impl() which handles warm-up properly.

        Returns:
            DataFrame with OHLCV data and indicators

        Raises:
            ValueError: If data is empty, has gaps, or is invalid
        """
        return load_data_impl(
            config=self.config,
            window=self.window,
            logger=self.logger,
        )
    
    def prepare_multi_tf_frames(self) -> MultiTFPreparedFrames:
        """
        Prepare multi-TF DataFrames with indicators and close_ts maps.

        Phase 3: Loads data for HTF, MTF, and LTF timeframes, applies
        indicators to each, and builds close_ts maps for data-driven
        cache detection.

        Delegates to engine_data_prep.prepare_multi_tf_frames_impl().

        Returns:
            MultiTFPreparedFrames with all TF data and metadata

        Raises:
            ValueError: If data is missing or invalid
        """
        result = prepare_multi_tf_frames_impl(
            config=self.config,
            window=self.window,
            tf_mapping=self._tf_mapping,
            multi_tf_mode=self._multi_tf_mode,
            logger=self.logger,
        )

        # Configure TimeframeCache with close_ts maps
        htf_tf = self._tf_mapping["htf"]
        htf_close_ts = result.close_ts_maps.get(htf_tf, set())
        mtf_close_ts = result.close_ts_maps.get(self._tf_mapping["mtf"], set())

        self._tf_cache.set_close_ts_maps(
            htf_close_ts=htf_close_ts,
            mtf_close_ts=mtf_close_ts,
            htf_tf=htf_tf,
            mtf_tf=self._tf_mapping["mtf"],
        )

        # Store TF DataFrames for feature lookup
        self._htf_df = result.frames.get(htf_tf)
        self._mtf_df = result.frames.get(self._tf_mapping["mtf"])
        self._ltf_df = result.ltf_frame

        self._mtf_frames = result

        # Also set _prepared_frame for backward compatibility
        ltf_frame = result.ltf_frame
        self._prepared_frame = PreparedFrame(
            df=ltf_frame,
            full_df=ltf_frame,
            warmup_bars=result.warmup_bars,
            max_indicator_lookback=result.max_indicator_lookback,
            requested_start=result.requested_start,
            requested_end=result.requested_end,
            loaded_start=ltf_frame["timestamp"].iloc[0],
            loaded_end=ltf_frame["timestamp"].iloc[-1],
            simulation_start=result.simulation_start,
            sim_start_index=result.ltf_sim_start_index,
        )
        self._data = ltf_frame

        return result
    
    def _build_feed_stores(self) -> MultiTFFeedStore:
        """
        Build FeedStores from prepared frames for array-backed hot loop.

        Must be called after prepare_multi_tf_frames() or prepare_backtest_frame().
        Creates FeedStore instances with precomputed arrays for O(1) access.

        Phase 3: Also builds 1m quote feed for px.last/px.mark.

        Delegates to engine_feed_builder.build_feed_stores_impl().

        Returns:
            MultiTFFeedStore with exec/htf/mtf feeds
        """
        result = build_feed_stores_impl(
            config=self.config,
            tf_mapping=self._tf_mapping,
            multi_tf_mode=self._multi_tf_mode,
            mtf_frames=self._mtf_frames,
            prepared_frame=self._prepared_frame,
            data=self._data,
            logger=self.logger,
        )

        self._multi_tf_feed_store, self._exec_feed, self._htf_feed, self._mtf_feed = result

        # Stage 3: Build market structures into exec feed
        self._build_structures()

        # Phase 3: Build 1m quote feed for px.last/px.mark
        self._build_quote_feed()

        return self._multi_tf_feed_store

    def _build_structures(self) -> None:
        """
        Build market structures into exec FeedStore.

        Checks if IdeaCard uses the Feature Registry with structures section.
        If so, incremental state is used (built in run()) and batch building is skipped.
        Otherwise, falls back to deprecated batch structure building with warning.

        Called from _build_feed_stores() after exec/htf/mtf feeds are built.
        """
        if self._idea_card is None:
            return

        if self._exec_feed is None:
            self.logger.warning("Cannot build structures: no exec feed")
            return

        # Check if IdeaCard uses the Feature Registry with structures
        # If so, skip batch build - incremental state is built in run()
        registry = self._feature_registry
        if registry is None and self._idea_card is not None:
            registry = self._idea_card.feature_registry

        has_incremental_structures = registry is not None and len(registry.get_structures()) > 0

        if has_incremental_structures:
            self.logger.debug("IdeaCard uses 'structures:' section - using incremental state")
            return

        # Fallback: use batch structure building (emits deprecation warning if present)
        build_structures_into_feed(
            exec_feed=self._exec_feed,
            idea_card=self._idea_card,
            logger=self.logger,
        )

    def _build_quote_feed(self) -> None:
        """
        Build 1m quote FeedStore for px.last/px.mark price proxy.

        Loads 1m data from DuckDB and builds a FeedStore for O(1) quote access.
        The quote feed provides last-trade proxy and mark price for each 1m bar.

        Phase 3: Called from _build_feed_stores() after exec/htf/mtf feeds are built.
        """
        if self._prepared_frame is None:
            self.logger.warning("Cannot build quote feed: no prepared frame")
            return

        # Compute 1m warmup: convert exec warmup to 1m bars
        # For a 15m exec TF, 1 warmup bar = 15 1m bars
        exec_tf_minutes = TF_MINUTES.get(self.config.tf.lower(), 15)
        warmup_bars_exec = self._prepared_frame.warmup_bars
        warmup_bars_1m = warmup_bars_exec * exec_tf_minutes

        try:
            # Load 1m data
            df_1m = load_1m_data_impl(
                symbol=self.config.symbol,
                window_start=self._prepared_frame.requested_start,
                window_end=self._prepared_frame.requested_end,
                warmup_bars_1m=warmup_bars_1m,
                data_env=self.config.data_build.env,
                logger=self.logger,
            )

            # Build quote FeedStore
            self._quote_feed = build_quote_feed_impl(
                df_1m=df_1m,
                symbol=self.config.symbol,
                logger=self.logger,
            )

            # Reset rollup bucket for fresh run
            self._rollup_bucket.reset()
            self._current_rollups = create_empty_rollup_dict()
            self._last_1m_idx = -1

            self.logger.info(
                f"Quote feed ready: {self._quote_feed.length} 1m bars"
            )

        except ValueError as e:
            # 1m data not available - warn but continue (preflight should have caught this)
            self.logger.warning(f"Quote feed unavailable: {e}")

    def _accumulate_1m_quotes(self, exec_ts_close: datetime) -> None:
        """
        Accumulate 1m quotes between previous exec close and current exec close.

        Scans 1m bars from last processed index to current exec close and
        accumulates their data into the rollup bucket. Called at each exec bar.

        Phase 3: Provides px.rollup.* values for zone interaction detection.

        Args:
            exec_ts_close: Current exec bar's ts_close
        """
        if self._quote_feed is None:
            return

        # Find the last 1m bar closed at or before exec_ts_close
        end_1m_idx = self._quote_feed.get_last_closed_idx_at_or_before(exec_ts_close)
        if end_1m_idx is None:
            return

        # Process all 1m bars from last_1m_idx + 1 to end_1m_idx (inclusive)
        start_1m_idx = self._last_1m_idx + 1
        if start_1m_idx > end_1m_idx:
            # No new 1m bars to process
            return

        # Accumulate each 1m bar via direct array access (O(1) per bar)
        # BUG-001 FIX: Replaced get_quote_at_exec_close() which caused duplicate
        # accumulation due to binary search finding "last bar at or before timestamp"
        for idx in range(start_1m_idx, end_1m_idx + 1):
            # Build QuoteState directly from 1m feed arrays (O(1))
            # Use _get_ts_close_ms_at() method which converts ts_close[idx] to epoch ms
            ts_ms = self._quote_feed._get_ts_close_ms_at(idx)
            quote = QuoteState(
                ts_ms=ts_ms,
                last=float(self._quote_feed.close[idx]),
                open_1m=float(self._quote_feed.open[idx]),
                high_1m=float(self._quote_feed.high[idx]),
                low_1m=float(self._quote_feed.low[idx]),
                mark=float(self._quote_feed.close[idx]),
                mark_source="approx_from_ohlcv_1m",
                volume_1m=float(self._quote_feed.volume[idx]),
            )
            self._rollup_bucket.accumulate(quote)

        # Update last processed index
        self._last_1m_idx = end_1m_idx

    def _freeze_rollups(self) -> dict[str, float]:
        """
        Freeze rollup bucket at exec close and reset for next interval.

        Returns the rollup values accumulated since last exec close,
        then resets the bucket for the next exec interval.

        Phase 3: Called at each exec bar close before snapshot creation.

        Returns:
            Dict with px.rollup.* keys and their values
        """
        rollups = self._rollup_bucket.freeze()
        self._current_rollups = rollups
        self._rollup_bucket.reset()
        return rollups

    def _get_tf_features_at_close(
        self,
        tf: str,
        ts_close: datetime,
        bar: CanonicalBar,
    ) -> FeatureSnapshot:
        """
        Get FeatureSnapshot for a TF at a specific close timestamp.

        Looks up the bar in the TF DataFrame that closed at ts_close
        and extracts its indicator features.

        Delegates to engine_data_prep.get_tf_features_at_close_impl().

        Args:
            tf: Timeframe string
            ts_close: Close timestamp to look up
            bar: Current bar (for fallback if not found)

        Returns:
            FeatureSnapshot with indicator values
        """
        return get_tf_features_at_close_impl(
            tf=tf,
            ts_close=ts_close,
            bar=bar,
            mtf_frames=self._mtf_frames,
            tf_mapping=self._tf_mapping,
            config=self.config,
        )
    
    def run(
        self,
        strategy: Callable[[RuntimeSnapshot, dict[str, Any]], Signal | None],
    ) -> BacktestResult:
        """
        Run the backtest.
        
        Args:
            strategy: Strategy function that takes (snapshot, params) and returns Signal or None
            
        Returns:
            BacktestResult with structured metrics, trades, and equity curve
            
        Phase 3: Multi-TF mode with data-driven caching.
        - Uses TimeframeCache.refresh_step() at each bar
        - Readiness gate blocks trading until HTF/MTF caches are ready
        - Cache updates are deterministic: HTF first, then MTF
        
        Lookahead Prevention (Phase 3):
        - Strategy is invoked ONLY at bar.ts_close (never mid-bar)
        - Indicators are precomputed OUTSIDE the hot loop (vectorized)
        - Snapshot.ts_close must equal bar.ts_close (asserted at runtime)
        - HTF/MTF features are forward-filled from last closed bar (no partial candles)
        """
        self._started_at = datetime.now()
        
        # Phase 3: Use multi-TF preparation if in multi-TF mode
        if self._multi_tf_mode and self._mtf_frames is None:
            self.prepare_multi_tf_frames()
        elif self._prepared_frame is None:
            self.prepare_backtest_frame()
        
        prepared = self._prepared_frame
        df = prepared.df
        sim_start_idx = prepared.sim_start_index
        
        # Array-backed hot loop: Build FeedStores for O(1) access
        self._build_feed_stores()
        exec_feed = self._exec_feed
        num_bars = exec_feed.length
        tf_delta = tf_duration(self.config.tf)

        # Phase 6: Build incremental state for structure detection
        self._incremental_state = self._build_incremental_state()
        
        # Get resolved risk profile values
        risk_profile = self.config.risk_profile
        initial_equity = risk_profile.initial_equity
        
        # Initialize exchange with initial equity and risk profile (Bybit-aligned)
        self._exchange = SimulatedExchange(
            symbol=self.config.symbol,
            initial_capital=initial_equity,
            execution_config=self.execution_config,
            risk_profile=risk_profile,
        )
        
        # Reset risk manager
        self.risk_manager.reset()
        
        self.logger.info(
            f"Running backtest: {len(df)} bars, sim_start_idx={sim_start_idx}, "
            f"warmup_bars={prepared.warmup_bars}, equity=${initial_equity:,.0f}, "
                f"leverage={risk_profile.max_leverage:.1f}x, "
                f"mark_price_source={risk_profile.mark_price_source}"
        )
        
        # Bar-by-bar simulation
        self._equity_curve = []
        self._account_curve: list[AccountCurvePoint] = []
        prev_bar: CanonicalBar | None = None

        # Early-stop tracking (proof-grade)
        stop_classification: StopReason | None = None
        stop_reason_detail: str | None = None
        stop_reason: str | None = None  # Legacy compat
        stop_ts: datetime | None = None
        stop_bar_index: int | None = None
        stop_details: dict[str, Any] | None = None
        
        for i in range(num_bars):
            # Array-backed hot loop: O(1) access to bar data
            # Get timestamps from FeedStore (no pandas)
            ts_open = exec_feed.get_ts_open_datetime(i)
            ts_close = exec_feed.get_ts_close_datetime(i)
            
            # Create canonical Bar with O(1) array access
            bar = CanonicalBar(
                symbol=self.config.symbol,
                tf=self.config.tf,
                ts_open=ts_open,
                ts_close=ts_close,
                open=float(exec_feed.open[i]),
                high=float(exec_feed.high[i]),
                low=float(exec_feed.low[i]),
                close=float(exec_feed.close[i]),
                volume=float(exec_feed.volume[i]),
            )

            # Phase 6: Update incremental state with current bar
            # This must happen BEFORE snapshot creation so structures are current
            if self._incremental_state is not None:
                # Build indicator dict for BarData (O(1) dict build from arrays)
                indicator_values: dict[str, float] = {}
                for key in exec_feed.indicators.keys():
                    val = exec_feed.indicators[key][i]
                    if not np.isnan(val):
                        indicator_values[key] = float(val)

                # Create BarData for incremental update
                bar_data = BarData(
                    idx=i,
                    open=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                    volume=bar.volume,
                    indicators=indicator_values,
                )

                # Update exec state every bar
                self._incremental_state.update_exec(bar_data)

            # Stage 7: State tracking - bar start (record-only)
            if self._state_tracker:
                self._state_tracker.on_bar_start(i)
                # Record warmup/history gate state
                warmup_ok = i >= sim_start_idx
                self._state_tracker.on_warmup_check(warmup_ok, sim_start_idx)
                self._state_tracker.on_history_check(
                    self._is_history_ready(),
                    len(self._history_manager.bars_exec),
                )

            # Phase 4: Set bar context for artifact tracking
            # Note: snapshot_ready starts as True, will be updated after snapshot build
            self._exchange.set_bar_context(i, snapshot_ready=True)
            
            # Process bar (fills pending orders, checks TP/SL)
            # Note: process_bar receives canonical Bar, uses ts_open for fills
            # Phase 4: process_bar returns StepResult with unified mark_price
            # 1m eval: Pass quote_feed and 1m range for granular TP/SL checking
            exec_1m_range = None
            if self._quote_feed is not None and self._quote_feed.length > 0:
                exec_tf_minutes = TF_MINUTES.get(self.config.tf.lower(), 15)
                start_1m, end_1m = self._quote_feed.get_1m_indices_for_exec(i, exec_tf_minutes)
                end_1m = min(end_1m, self._quote_feed.length - 1)
                exec_1m_range = (start_1m, end_1m)
            step_result = self._exchange.process_bar(
                bar, prev_bar,
                quote_feed=self._quote_feed,
                exec_1m_range=exec_1m_range,
            )
            # NOTE: Closed trades are in self._exchange.trades (cumulative list)
            # Fills are in step_result.fills (per-step list) - BUG-004 fix

            # Stage 7: Record fills/rejections from step_result (record-only)
            if self._state_tracker and step_result:
                for _fill in step_result.fills:
                    self._state_tracker.on_order_filled()
                for _rejection in step_result.rejections:
                    self._state_tracker.on_order_rejected(_rejection.reason)

            # Sync risk manager equity with exchange
            self.risk_manager.sync_equity(self._exchange.equity)
            
            # Skip bars before simulation start (warm-up period)
            if i < sim_start_idx:
                # Phase 3: Update HTF/MTF indices during warmup (for forward-fill)
                htf_updated_warmup = False
                mtf_updated_warmup = False
                if self._multi_tf_mode:
                    htf_updated_warmup, mtf_updated_warmup = self._update_htf_mtf_indices(bar.ts_close)
                
                # Array-backed: Extract features from FeedStore (O(1) access)
                warmup_features = {}
                for key in exec_feed.indicators.keys():
                    val = exec_feed.indicators[key][i]
                    if not np.isnan(val):
                        warmup_features[key] = float(val)
                
                warmup_features_exec = FeatureSnapshot(
                    tf=self.config.tf,
                    ts_close=bar.ts_close,
                    bar=bar,
                    features=warmup_features,
                    ready=True,
                )
                
                self._update_history(
                    bar=bar,
                    features_exec=warmup_features_exec,
                    htf_updated=htf_updated_warmup,
                    mtf_updated=mtf_updated_warmup,
                    features_htf=self._tf_cache.get_htf() if self._multi_tf_mode else None,
                    features_mtf=self._tf_cache.get_mtf() if self._multi_tf_mode else None,
                )
                
                prev_bar = bar
                continue
            
            # Phase 3: Update HTF/MTF indices at current bar close (O(1) lookup)
            htf_updated = False
            mtf_updated = False
            if self._multi_tf_mode:
                htf_updated, mtf_updated = self._update_htf_mtf_indices(bar.ts_close)

            # Phase 6: Update HTF incremental state on HTF close
            if self._incremental_state is not None and htf_updated:
                # Get the HTF timeframe from tf_mapping
                htf_tf = self._tf_mapping.get("htf")
                if htf_tf and htf_tf in self._incremental_state.htf:
                    # Build HTF BarData from HTF feed at current HTF index
                    htf_feed = self._htf_feed
                    if htf_feed is not None:
                        htf_idx = self._current_htf_idx
                        htf_indicator_values: dict[str, float] = {}
                        for key in htf_feed.indicators.keys():
                            val = htf_feed.indicators[key][htf_idx]
                            if not np.isnan(val):
                                htf_indicator_values[key] = float(val)

                        htf_bar_data = BarData(
                            idx=htf_idx,
                            open=float(htf_feed.open[htf_idx]),
                            high=float(htf_feed.high[htf_idx]),
                            low=float(htf_feed.low[htf_idx]),
                            close=float(htf_feed.close[htf_idx]),
                            volume=float(htf_feed.volume[htf_idx]),
                            indicators=htf_indicator_values,
                        )
                        self._incremental_state.update_htf(htf_tf, htf_bar_data)

            # Array-backed: Extract features from FeedStore (O(1) access)
            features_for_history = {}
            for key in exec_feed.indicators.keys():
                val = exec_feed.indicators[key][i]
                if not np.isnan(val):
                    features_for_history[key] = float(val)
            
            current_features_exec = FeatureSnapshot(
                tf=self.config.tf,
                ts_close=bar.ts_close,
                bar=bar,
                features=features_for_history,
                ready=True,
            )
            
            # NOTE: _update_history is called AFTER strategy evaluation (at end of loop)
            # to ensure crossover detection can access PREVIOUS bar's features correctly.
            # See: history_features_exec[-1] should be bar N-1 when evaluating bar N.

            # ========== STOP CHECKS (delegated to engine_stops module) ==========
            # Phase 1: only close-as-mark supported (explicit/configurable)
            if risk_profile.mark_price_source != "close":
                raise ValueError(
                    f"Unsupported mark_price_source='{risk_profile.mark_price_source}'. "
                    "Phase 1 supports 'close' only."
                )

            stop_result = check_all_stop_conditions(
                exchange=self._exchange,
                risk_profile=risk_profile,
                bar_ts_close=bar.ts_close,
                bar_index=i,
                logger=self.logger,
            )

            if stop_result.terminal_stop:
                # Capture stop metadata before handling
                stop_classification = stop_result.classification
                stop_reason_detail = stop_result.reason_detail
                stop_reason = stop_result.reason

                # Handle terminal stop (cancel orders, close position)
                handle_terminal_stop(
                    exchange=self._exchange,
                    bar_close_price=bar.close,
                    bar_ts_close=bar.ts_close,
                    stop_reason=stop_reason,
                )

                # Capture stop metadata (full exchange snapshot)
                stop_ts = bar.ts_close
                stop_bar_index = i
                stop_details = self._exchange.get_state()

                # Record final equity and account curve points at ts_close
                self._equity_curve.append(EquityPoint(
                    timestamp=bar.ts_close,
                    equity=self._exchange.equity,
                ))
                self._account_curve.append(AccountCurvePoint(
                    timestamp=bar.ts_close,
                    equity_usdt=self._exchange.equity_usdt,
                    used_margin_usdt=self._exchange.used_margin_usdt,
                    free_margin_usdt=self._exchange.free_margin_usdt,
                    available_balance_usdt=self._exchange.available_balance_usdt,
                    maintenance_margin_usdt=self._exchange.maintenance_margin,
                    has_position=self._exchange.position is not None,
                    entries_disabled=self._exchange.entries_disabled,
                ))

                self.logger.warning(
                    f"Terminal stop: {stop_classification.value} at bar {i}, "
                    f"equity=${self._exchange.equity_usdt:.2f}, "
                    f"detail: {stop_reason_detail}"
                )
                break
            # ========== END STOP CHECKS ==========

            # Phase 3: Accumulate 1m quotes and freeze rollups at exec close
            # This must happen BEFORE snapshot creation so rollups are available
            self._accumulate_1m_quotes(bar.ts_close)
            rollups = self._freeze_rollups()

            # Array-backed hot loop: Build RuntimeSnapshotView (O(1) creation)
            # No DataFrame access, no materialized feature dicts
            snapshot = self._build_snapshot_view(i, step_result, rollups=rollups)
            
            # Phase 4: Invoke snapshot callback if present (audit-only, no side effects)
            # Callback is invoked AFTER snapshot built, BEFORE strategy called
            if self._on_snapshot is not None:
                self._on_snapshot(snapshot, i, self._current_htf_idx, self._current_mtf_idx)
            
            # Phase 4: Update exchange with snapshot readiness for artifact tracking
            self._exchange.set_bar_context(i, snapshot_ready=snapshot.ready)
            
            # Phase 3: Readiness gate - skip trading until all TF caches are ready
            if self._multi_tf_mode and not snapshot.ready:
                # Caches not ready yet - record equity but skip strategy
                self._equity_curve.append(EquityPoint(
                    timestamp=bar.ts_close,
                    equity=self._exchange.equity,
                ))
                self._account_curve.append(AccountCurvePoint(
                    timestamp=bar.ts_close,
                    equity_usdt=self._exchange.equity_usdt,
                    used_margin_usdt=self._exchange.used_margin_usdt,
                    free_margin_usdt=self._exchange.free_margin_usdt,
                    available_balance_usdt=self._exchange.available_balance_usdt,
                    maintenance_margin_usdt=self._exchange.maintenance_margin,
                    has_position=self._exchange.position is not None,
                    entries_disabled=self._exchange.entries_disabled,
                ))
                prev_bar = bar
                continue
            
            # Mark warmup as complete on first ready snapshot
            if self._multi_tf_mode and not self._warmup_complete:
                self._warmup_complete = True
                self._first_ready_bar_index = i
                self.logger.info(
                    f"Multi-TF caches ready at bar {i} ({bar.ts_close})"
                )
            
            # ========== LOOKAHEAD GUARD (Phase 3) ==========
            # Assert strategy is invoked only at bar close with closed-candle data.
            # This guard prevents future regressions that could introduce lookahead bias.
            assert snapshot.ts_close == bar.ts_close, (
                f"Lookahead violation: snapshot.ts_close ({snapshot.ts_close}) != "
                f"bar.ts_close ({bar.ts_close})"
            )
            # RuntimeSnapshotView has exec_ctx with ts_close property
            exec_ts_close = snapshot.exec_ctx.ts_close if hasattr(snapshot, 'exec_ctx') else snapshot.features_exec.ts_close
            assert exec_ts_close == bar.ts_close, (
                f"Lookahead violation: exec ts_close ({exec_ts_close}) != "
                f"bar.ts_close ({bar.ts_close})"
            )
            # ========== END LOOKAHEAD GUARD ==========

            # ========== 1m EVALUATION SUB-LOOP ==========
            # Evaluate strategy at each 1m bar within the exec bar
            # Returns on first signal (max one entry per exec bar)
            signal, snapshot, signal_ts = self._evaluate_with_1m_subloop(
                exec_idx=i,
                strategy=strategy,
                step_result=step_result,
                rollups=rollups,
            )
            # ========== END 1m EVALUATION SUB-LOOP ==========

            # Stage 7: State tracking - record signal (record-only)
            if self._state_tracker:
                signal_direction = 0
                if signal is not None:
                    if signal.direction == "LONG":
                        signal_direction = 1
                    elif signal.direction == "SHORT":
                        signal_direction = -1
                self._state_tracker.on_signal_evaluated(signal_direction)
                # Record position state for gate context
                position_count = 1 if self._exchange.position is not None else 0
                self._state_tracker.on_position_check(position_count)

            # Process signal (use signal_ts from 1m sub-loop if available)
            if signal is not None:
                self._process_signal(signal, bar, snapshot, signal_ts=signal_ts)
            
            # Record equity point and account curve point at ts_close (step time)
            self._equity_curve.append(EquityPoint(
                timestamp=bar.ts_close,
                equity=self._exchange.equity,
            ))
            self._account_curve.append(AccountCurvePoint(
                timestamp=bar.ts_close,
                equity_usdt=self._exchange.equity_usdt,
                used_margin_usdt=self._exchange.used_margin_usdt,
                free_margin_usdt=self._exchange.free_margin_usdt,
                available_balance_usdt=self._exchange.available_balance_usdt,
                maintenance_margin_usdt=self._exchange.maintenance_margin,
                has_position=self._exchange.position is not None,
                entries_disabled=self._exchange.entries_disabled,
            ))
            
            # Update history AFTER strategy evaluation
            # This ensures crossover detection sees previous bar's features in history[-1]
            self._update_history(
                bar=bar,
                features_exec=current_features_exec,
                htf_updated=htf_updated,
                mtf_updated=mtf_updated,
                features_htf=self._tf_cache.get_htf() if self._multi_tf_mode else None,
                features_mtf=self._tf_cache.get_mtf() if self._multi_tf_mode else None,
            )

            # Stage 7: State tracking - bar end (record-only)
            if self._state_tracker:
                self._state_tracker.on_bar_end()

            prev_bar = bar
        
        # Close any remaining position at end (if not already stopped early)
        if stop_classification is None and self._exchange.position is not None:
            # Array-backed: use exec_feed for O(1) access
            last_idx = exec_feed.length - 1
            self._exchange.force_close_position(
                float(exec_feed.close[last_idx]),
                exec_feed.get_ts_open_datetime(last_idx),  # Use ts_open for fill time
            )
        
        # Capture end-of-data snapshot if not already captured from terminal stop
        if stop_details is None:
            stop_details = self._exchange.get_state()
        
        # Calculate drawdowns in equity curve
        self._calculate_drawdowns()
        
        # Count bars in position for time-in-market metric
        bars_in_position = sum(1 for a in self._account_curve if a.has_position)

        # Compute margin stress metrics from account curve
        min_margin_ratio = 1.0
        margin_calls = 0
        closest_liquidation_pct = 100.0

        for a in self._account_curve:
            # Margin ratio: equity / used_margin (lower = more stressed)
            if a.used_margin_usdt > 0:
                ratio = a.equity_usdt / a.used_margin_usdt
                if ratio < min_margin_ratio:
                    min_margin_ratio = ratio

            # Margin call: free_margin < 0
            if a.free_margin_usdt < 0:
                margin_calls += 1

            # Liquidation proximity: (equity - MM) / equity * 100
            if a.equity_usdt > 0 and a.maintenance_margin_usdt > 0:
                buffer_pct = (a.equity_usdt - a.maintenance_margin_usdt) / a.equity_usdt * 100
                if buffer_pct < closest_liquidation_pct:
                    closest_liquidation_pct = buffer_pct

        # Compute leverage/exposure metrics from account curve
        # Leverage = position_value / equity = (used_margin / IMR) / equity
        imr = risk_profile.initial_margin_rate
        leverage_values = []
        max_gross_exposure_pct = 0.0

        for a in self._account_curve:
            if a.has_position and a.used_margin_usdt > 0 and a.equity_usdt > 0 and imr > 0:
                # position_value = used_margin / IMR
                position_value = a.used_margin_usdt / imr
                leverage = position_value / a.equity_usdt
                leverage_values.append(leverage)
                exposure_pct = (position_value / a.equity_usdt) * 100
                if exposure_pct > max_gross_exposure_pct:
                    max_gross_exposure_pct = exposure_pct

        avg_leverage_used = sum(leverage_values) / len(leverage_values) if leverage_values else 0.0

        # Compute average MAE/MFE from trades
        trades = self._exchange.trades
        if trades:
            mae_avg_pct = sum(t.mae_pct for t in trades) / len(trades)
            mfe_avg_pct = sum(t.mfe_pct for t in trades) / len(trades)
        else:
            mae_avg_pct = 0.0
            mfe_avg_pct = 0.0

        # Capture first/last price for benchmark comparison
        exec_feed = self._exec_feed
        sim_start_idx = self._prepared_frame.sim_start_index
        first_price = float(exec_feed.close[sim_start_idx])
        last_price = float(exec_feed.close[exec_feed.length - 1])

        # Compute backtest metrics
        metrics = compute_backtest_metrics(
            equity_curve=self._equity_curve,
            trades=self._exchange.trades,
            tf=self.config.tf,
            initial_equity=initial_equity,
            bars_in_position=bars_in_position,
            # Entry friction from exchange
            entry_attempts=self._exchange.entry_attempts_count,
            entry_rejections=self._exchange.entry_rejections_count,
            # Margin stress from account curve
            min_margin_ratio=min_margin_ratio,
            margin_calls=margin_calls,
            # Liquidation proximity from account curve
            closest_liquidation_pct=closest_liquidation_pct,
            # Benchmark comparison
            first_price=first_price,
            last_price=last_price,
            # Leverage/exposure metrics
            avg_leverage_used=avg_leverage_used,
            max_gross_exposure_pct=max_gross_exposure_pct,
            # Trade quality (MAE/MFE from trade-level tracking)
            mae_avg_pct=mae_avg_pct,
            mfe_avg_pct=mfe_avg_pct,
        )
        
        finished_at = datetime.now()
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        
        # Build strategies summary from config
        strategies_summary = [
            StrategyInstanceSummary(
                strategy_instance_id=s.strategy_instance_id,
                strategy_id=s.strategy_id,
                strategy_version=s.strategy_version,
                role=s.role,
            )
            for s in self.config.strategies
        ]
        
        # Build run config echo for reproducibility
        run_config_echo = BacktestRunConfigEcho(
            initial_margin_rate=risk_profile.initial_margin_rate,
            maintenance_margin_rate=risk_profile.maintenance_margin_rate,
            taker_fee_rate=risk_profile.taker_fee_rate,
            slippage_bps=self.execution_config.slippage_bps,
            mark_price_source=risk_profile.mark_price_source,
            include_est_close_fee_in_entry_gate=risk_profile.include_est_close_fee_in_entry_gate,
            min_trade_usdt=risk_profile.min_trade_usdt,
            stop_equity_usdt=risk_profile.stop_equity_usdt,
            max_leverage=risk_profile.max_leverage,
            fee_mode=risk_profile.fee_mode,
        )
        
        # Determine if stopped early (terminal stops only)
        stopped_early = stop_classification is not None and stop_classification.is_terminal()
        
        # Build structured result with warm-up metadata
        result = BacktestResult(
            run_id=run_id,
            system_id=self.config.system_id,
            system_uid=self.config.system_uid,
            primary_strategy_instance_id=self.config.primary_strategy_instance_id,
            strategy_id=self.config.strategy_id,
            strategy_version=self.config.strategy_version,
            strategies=strategies_summary,
            symbol=self.config.symbol,
            tf=self.config.tf,
            window_name=self.window_name,
            start_ts=self.window.start,
            end_ts=self.window.end,
            started_at=self._started_at,
            finished_at=finished_at,
            risk_mode=self.config.risk_mode,
            data_env=self.config.data_build.env,
            metrics=metrics,
            risk_initial_equity_used=risk_profile.initial_equity,
            risk_per_trade_pct_used=risk_profile.risk_per_trade_pct,
            risk_max_leverage_used=risk_profile.max_leverage,
            # Warm-up and window metadata
            warmup_bars=prepared.warmup_bars,
            max_indicator_lookback=prepared.max_indicator_lookback,
            data_window_requested_start=prepared.requested_start.isoformat(),
            data_window_requested_end=prepared.requested_end.isoformat(),
            data_window_loaded_start=prepared.loaded_start.isoformat() if isinstance(prepared.loaded_start, datetime) else str(prepared.loaded_start),
            data_window_loaded_end=prepared.loaded_end.isoformat() if isinstance(prepared.loaded_end, datetime) else str(prepared.loaded_end),
            simulation_start_ts=prepared.simulation_start,
            # Trades and equity
            trades=self._exchange.trades,
            equity_curve=self._equity_curve,
            artifact_dir=str(self.run_dir) if self.run_dir else None,
            # Account curve (proof-grade)
            account_curve=self._account_curve,
            # Run config echo
            run_config_echo=run_config_echo,
            # Stop classification (proof-grade)
            stop_classification=stop_classification,
            stop_reason_detail=stop_reason_detail,
            # Early-stop fields (legacy compat)
            stopped_early=stopped_early,
            stop_reason=stop_reason,
            stop_ts=stop_ts,
            stop_bar_index=stop_bar_index,
            stop_details=stop_details,
            # Starvation tracking
            entries_disabled=self._exchange.entries_disabled,
            first_starved_ts=self._exchange.first_starved_ts,
            first_starved_bar_index=self._exchange.first_starved_bar_index,
            entry_attempts_count=self._exchange.entry_attempts_count,
            entry_rejections_count=self._exchange.entry_rejections_count,
        )
        
        # Write artifacts if run_dir is set
        if self.run_dir:
            self._write_artifacts(result)
        
        if stopped_early:
            self.logger.info(
                f"Backtest stopped early ({stop_classification.value}): {metrics.total_trades} trades, "
                f"PnL=${metrics.net_profit:,.2f}, "
                f"Win rate={metrics.win_rate:.1f}%"
            )
        else:
            starved_msg = " (entries disabled)" if self._exchange.entries_disabled else ""
            self.logger.info(
                f"Backtest complete{starved_msg}: {metrics.total_trades} trades, "
                f"PnL=${metrics.net_profit:,.2f}, "
                f"Win rate={metrics.win_rate:.1f}%"
            )
        
        return result
    
    def _refresh_tf_caches(self, ts_close: datetime, bar: CanonicalBar) -> tuple:
        """
        Refresh HTF/MTF caches at current bar close.

        Phase 3: Uses TimeframeCache.refresh_step() with factory functions
        that build FeatureSnapshots from the precomputed TF DataFrames.

        Updates are deterministic: HTF first, then MTF.

        Delegates to engine_snapshot.refresh_tf_caches_impl().

        Args:
            ts_close: Current LTF close timestamp
            bar: Current LTF bar (for fallback)

        Returns:
            Tuple of (htf_updated, mtf_updated) booleans
        """
        def get_tf_features(tf: str, ts: datetime) -> FeatureSnapshot:
            return self._get_tf_features_at_close(tf, ts, bar)

        return refresh_tf_caches_impl(
            ts_close=ts_close,
            tf_mapping=self._tf_mapping,
            tf_cache=self._tf_cache,
            get_tf_features_func=get_tf_features,
        )
    
    def _update_htf_mtf_indices(self, exec_ts_close: datetime) -> tuple:
        """
        Update HTF/MTF forward-fill indices for RuntimeSnapshotView.

        Forward-fill principle: Any TF slower than exec keeps its index constant
        until its bar closes. This ensures no-lookahead (values reflect last
        CLOSED bar only, never partial/forming bars).

        Example (exec=15m, HTF=1h):
            exec bars:      |  1  |  2  |  3  |  4  |  5  |  ...
            htf_ctx.idx:    [  0     0     0     0  ] [  1  ...
            htf_updated:       F     F     F     T      F  ...

        Uses O(1) ts_close_ms_to_idx mapping from FeedStore.
        Called at each exec bar close. Index only changes when TF bar closes.

        Args:
            exec_ts_close: Current exec bar's ts_close

        Returns:
            Tuple of (htf_updated, mtf_updated) booleans indicating if index changed
        """
        htf_updated, mtf_updated, new_htf_idx, new_mtf_idx = update_htf_mtf_indices_impl(
            exec_ts_close=exec_ts_close,
            htf_feed=self._htf_feed,
            mtf_feed=self._mtf_feed,
            exec_feed=self._exec_feed,
            current_htf_idx=self._current_htf_idx,
            current_mtf_idx=self._current_mtf_idx,
        )

        self._current_htf_idx = new_htf_idx
        self._current_mtf_idx = new_mtf_idx

        return htf_updated, mtf_updated
    
    def _build_snapshot_view(
        self,
        exec_idx: int,
        step_result: "StepResult | None" = None,
        rollups: dict[str, float] | None = None,
        mark_price_override: float | None = None,
    ) -> RuntimeSnapshotView:
        """
        Build RuntimeSnapshotView for array-backed hot loop.

        O(1) snapshot creation - just sets indices, no data copying.

        Delegates to engine_snapshot.build_snapshot_view_impl().

        Args:
            exec_idx: Current exec bar index
            step_result: Optional StepResult from exchange (for mark_price)
            rollups: Optional px.rollup.* values from 1m accumulation
            mark_price_override: Optional override for mark_price (1m evaluation)

        Returns:
            RuntimeSnapshotView ready for strategy evaluation
        """
        return build_snapshot_view_impl(
            exec_idx=exec_idx,
            multi_tf_feed_store=self._multi_tf_feed_store,
            exec_feed=self._exec_feed,
            htf_feed=self._htf_feed,
            mtf_feed=self._mtf_feed,
            exchange=self._exchange,
            multi_tf_mode=self._multi_tf_mode,
            current_htf_idx=self._current_htf_idx,
            current_mtf_idx=self._current_mtf_idx,
            history_config=self._history_config,
            is_history_ready=self._is_history_ready(),
            risk_profile=self.config.risk_profile,
            step_result=step_result,
            rollups=rollups,
            mark_price_override=mark_price_override,
            incremental_state=self._incremental_state,
            feature_registry=self._feature_registry,
        )

    def _evaluate_with_1m_subloop(
        self,
        exec_idx: int,
        strategy: "StrategyFn",
        step_result: "StepResult | None",
        rollups: dict[str, float] | None,
    ) -> tuple["Signal | None", "RuntimeSnapshotView", datetime | None]:
        """
        Evaluate strategy at 1m granularity within an exec bar.

        Iterates through 1m bars within the current exec bar and evaluates
        the strategy at each 1m close. Returns on first signal (max one
        entry per exec bar).

        Args:
            exec_idx: Current exec bar index
            strategy: Strategy function to evaluate
            step_result: StepResult from exchange
            rollups: px.rollup.* values from 1m accumulation

        Returns:
            Tuple of (signal, snapshot, signal_ts):
            - signal: Signal if triggered, None otherwise
            - snapshot: The snapshot used for evaluation (last evaluated)
            - signal_ts: Timestamp of signal (1m close) if triggered, None otherwise
        """
        # Get exec TF minutes for 1m mapping
        exec_tf_minutes = TF_MINUTES.get(self.config.tf.lower(), 15)

        # Check if 1m quote feed is available
        if self._quote_feed is None or self._quote_feed.length == 0:
            # Fallback: evaluate at exec close only (no 1m sub-loop)
            snapshot = self._build_snapshot_view(exec_idx, step_result, rollups)
            signal = None
            if not self._exchange.entries_disabled or self._exchange.position is not None:
                signal = strategy(snapshot, self.config.params)
            return signal, snapshot, None

        # Get 1m bar range for this exec bar
        start_1m, end_1m = self._quote_feed.get_1m_indices_for_exec(exec_idx, exec_tf_minutes)

        # Clamp to available 1m data
        end_1m = min(end_1m, self._quote_feed.length - 1)

        # Track last snapshot for return
        last_snapshot = None

        # Iterate through 1m bars
        for sub_idx in range(start_1m, end_1m + 1):
            # Get 1m close as mark_price
            mark_price_1m = float(self._quote_feed.close[sub_idx])

            # Build snapshot with 1m mark_price override
            snapshot = self._build_snapshot_view(
                exec_idx=exec_idx,
                step_result=step_result,
                rollups=rollups,
                mark_price_override=mark_price_1m,
            )
            last_snapshot = snapshot

            # Skip if entries disabled and no position
            if self._exchange.entries_disabled and self._exchange.position is None:
                continue

            # Evaluate strategy
            signal = strategy(snapshot, self.config.params)

            if signal is not None:
                # Get 1m close timestamp for order submission
                signal_ts = self._quote_feed.get_ts_close_datetime(sub_idx)
                return signal, snapshot, signal_ts

        # No signal triggered - return last snapshot for consistency
        if last_snapshot is None:
            last_snapshot = self._build_snapshot_view(exec_idx, step_result, rollups)

        return None, last_snapshot, None

    def _process_signal(
        self,
        signal: Signal,
        bar: CanonicalBar,
        snapshot: "RuntimeSnapshotView",
        signal_ts: datetime | None = None,
    ) -> None:
        """Process a strategy signal through risk sizing and submit order.

        REQUIRES RuntimeSnapshotView — legacy RuntimeSnapshot is not supported.

        Args:
            signal: Strategy signal to process
            bar: Current exec bar (for fallback timestamp)
            snapshot: RuntimeSnapshotView for sizing
            signal_ts: Optional override timestamp (from 1m evaluation)
        """
        exchange = self._exchange
        
        # Handle FLAT signal (close position)
        if signal.direction == "FLAT":
            if exchange.position is not None:
                exchange.submit_close(reason="signal")
            return
        
        # Skip if we already have a position
        if exchange.position is not None:
            return
        
        # Skip if we already have a pending order
        if exchange.pending_order is not None:
            return
        
        # Determine side
        side = "long" if signal.direction == "LONG" else "short"
        
        # Apply risk policy for filtering (if risk_mode=rules)
        # P1-004 FIX: Pass unrealized_pnl and position_count for accurate risk checks
        decision = self.risk_policy.check(
            signal=signal,
            equity=exchange.equity,
            available_balance=exchange.available_balance,
            total_exposure=exchange.position.size_usdt if exchange.position else 0,
            unrealized_pnl=exchange.unrealized_pnl_usdt,
            position_count=1 if exchange.position else 0,
        )
        
        if not decision.allowed:
            self.logger.debug(f"Signal blocked by risk policy: {decision.reason}")
            return
        
        # Use SimulatedRiskManager for sizing
        sizing_result = self.risk_manager.size_order(snapshot, signal)
        size_usdt = sizing_result.size_usdt

        # Stage 7: Record sizing (record-only)
        if self._state_tracker:
            self._state_tracker.on_sizing_computed(size_usdt)

        # Minimum size check (use configured min_trade_usdt)
        min_trade = self.config.risk_profile.min_trade_usdt
        if size_usdt < min_trade:
            self.logger.debug(f"Size too small ({size_usdt:.2f} < {min_trade}), skipping signal")
            return
        
        # Calculate TP/SL from signal metadata if present
        stop_loss = signal.metadata.get("stop_loss") if signal.metadata else None
        take_profit = signal.metadata.get("take_profit") if signal.metadata else None
        
        # Submit order (use signal_ts if provided, else bar.ts_close)
        order_timestamp = signal_ts if signal_ts is not None else bar.ts_close
        exchange.submit_order(
            side=side,
            size_usdt=size_usdt,
            stop_loss=stop_loss,
            take_profit=take_profit,
            timestamp=order_timestamp,
        )

        # Stage 7: Record order submission (record-only)
        if self._state_tracker:
            self._state_tracker.on_order_submitted()
    
    def _calculate_drawdowns(self) -> None:
        """Calculate drawdown values for equity curve.

        Delegates to engine_artifacts.calculate_drawdowns_impl().
        """
        calculate_drawdowns_impl(self._equity_curve)

    def _write_artifacts(self, result: BacktestResult) -> None:
        """Write run artifacts to run_dir.

        Delegates to engine_artifacts.write_artifacts_impl().
        """
        if self.run_dir:
            write_artifacts_impl(result, self.run_dir, self.logger)

    def get_state_tracker(self) -> StateTracker | None:
        """
        Get the state tracker if state tracking is enabled.

        Stage 7: Returns the StateTracker instance if record_state_tracking=True
        was passed to __init__. Returns None otherwise.

        Returns:
            StateTracker or None
        """
        return self._state_tracker

    def get_state_tracking_stats(self) -> dict[str, Any]:
        """
        Get state tracking summary statistics.

        Stage 7: Returns aggregated stats from block history.
        Returns empty dict if state tracking is disabled.

        Returns:
            Dict with signal/action/gate statistics
        """
        if self._state_tracker is None:
            return {}
        return self._state_tracker.summary_stats()


# NOTE: Factory functions (run_backtest, create_engine_from_idea_card, run_engine_with_idea_card)
# are now in engine_factory.py and imported at the top of this module for backward compatibility.
