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
    load_funding_data_impl,
    load_open_interest_data_impl,
    timeframe_to_timedelta,
    get_tf_features_at_close_impl,
)

# Import from engine_feed_builder module
from .engine_feed_builder import (
    build_feed_stores_impl,
    build_quote_feed_impl,
    get_quote_at_exec_close,
    build_structures_into_feed,
    build_market_data_arrays_impl,
)

# Import funding scheduler for hot loop
from .runtime.funding_scheduler import get_funding_events_in_window

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

# Import BarProcessor for decomposed run loop
from .bar_processor import BarProcessor, BarProcessingResult

# Import factory functions from engine_factory module
# These are re-exported for backward compatibility
from .engine_factory import (
    run_backtest,
    create_engine_from_play,
    run_engine_with_play,
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
from .rationalization import StateRationalizer, RationalizedState

from ..core.risk_manager import Signal
from ..data.historical_data_store import get_historical_store, TF_MINUTES
from ..utils.logger import get_logger
from ..utils.debug import (
    debug_log,
    debug_milestone,
    debug_signal,
    debug_trade,
    debug_run_complete,
    is_debug_enabled,
)

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .feature_registry import FeatureRegistry
    from .play import Play


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
            feature_registry: Optional FeatureRegistry from Play.
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

        # Debug tracing: play_hash for log correlation
        self._play_hash: str | None = None
        
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

        # Phase 12: Funding rate and open interest data
        self._funding_df: pd.DataFrame | None = None
        self._oi_df: pd.DataFrame | None = None

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

        # Play reference (set by factory, None if created directly)
        # Must be initialized here to avoid AttributeError in _build_structures_into_exec_feed()
        self._play: "Play | None" = None

        # Phase 6: Incremental state for structure detection (swing, trend, zone, etc.)
        # Built from Play structure specs after engine creation
        self._incremental_state: MultiTFIncrementalState | None = None

        # W2: StateRationalizer for Layer 2 transition detection and derived state
        # Created alongside incremental_state, called after structure updates
        self._rationalizer: StateRationalizer | None = None
        self._rationalized_state: RationalizedState | None = None

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
        if registry is None and self._play is not None:
            registry = self._play.feature_registry

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

    def set_play_hash(self, play_hash: str) -> None:
        """Set play hash for debug log correlation."""
        self._play_hash = play_hash

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

        # Phase 12: Build market data arrays (funding rates, open interest)
        self._build_market_data()

        return self._multi_tf_feed_store

    def _build_structures(self) -> None:
        """
        Build market structures into exec FeedStore.

        Checks if Play uses the Feature Registry with structures section.
        If so, incremental state is used (built in run()) and batch building is skipped.
        Otherwise, falls back to deprecated batch structure building with warning.

        Called from _build_feed_stores() after exec/htf/mtf feeds are built.
        """
        if self._play is None:
            return

        if self._exec_feed is None:
            self.logger.warning("Cannot build structures: no exec feed")
            return

        # Check if Play uses the Feature Registry with structures
        # If so, skip batch build - incremental state is built in run()
        registry = self._feature_registry
        if registry is None and self._play is not None:
            registry = self._play.feature_registry

        has_incremental_structures = registry is not None and len(registry.get_structures()) > 0

        if has_incremental_structures:
            self.logger.debug("Play uses 'structures:' section - using incremental state")
            return

        # Fallback: use batch structure building (emits deprecation warning if present)
        build_structures_into_feed(
            exec_feed=self._exec_feed,
            play=self._play,
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

    def _build_market_data(self) -> None:
        """
        Build market data arrays (funding rates, open interest) into exec FeedStore.

        Loads funding and OI data from DuckDB and builds arrays aligned to exec bar
        timestamps. These arrays enable:
        - funding_rate feature access in strategies
        - open_interest feature access in strategies
        - Funding settlement detection in hot loop

        Phase 12: Called from _build_feed_stores() after quote feed is built.
        """
        if self._prepared_frame is None:
            self.logger.debug("Cannot build market data: no prepared frame")
            return

        if self._exec_feed is None:
            self.logger.warning("Cannot build market data: no exec feed")
            return

        # Load funding rate data
        try:
            self._funding_df = load_funding_data_impl(
                symbol=self.config.symbol,
                window_start=self._prepared_frame.requested_start,
                window_end=self._prepared_frame.requested_end,
                data_env=self.config.data_build.env,
                logger=self.logger,
            )
        except Exception as e:
            self.logger.warning(f"Failed to load funding data: {e}")
            self._funding_df = None

        # Load open interest data
        try:
            self._oi_df = load_open_interest_data_impl(
                symbol=self.config.symbol,
                window_start=self._prepared_frame.requested_start,
                window_end=self._prepared_frame.requested_end,
                data_env=self.config.data_build.env,
                logger=self.logger,
            )
        except Exception as e:
            self.logger.warning(f"Failed to load open interest data: {e}")
            self._oi_df = None

        # Build aligned arrays
        funding_array, oi_array, settlement_times = build_market_data_arrays_impl(
            funding_df=self._funding_df,
            oi_df=self._oi_df,
            exec_feed=self._exec_feed,
            logger=self.logger,
        )

        # Wire into exec feed
        self._exec_feed.funding_rate = funding_array
        self._exec_feed.open_interest = oi_array
        self._exec_feed.funding_settlement_times = settlement_times

        # Log summary
        funding_info = f"{len(settlement_times)} settlements" if funding_array is not None else "unavailable"
        oi_info = "available" if oi_array is not None else "unavailable"
        self.logger.info(f"Market data ready: funding={funding_info}, OI={oi_info}")

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

        Uses BarProcessor for per-bar processing with clear separation:
        - Warmup bars: State updates only, no trading
        - Trading bars: Full evaluation with stops, signals, equity

        Lookahead Prevention:
        - Strategy is invoked ONLY at bar.ts_close (never mid-bar)
        - Indicators are precomputed OUTSIDE the hot loop (vectorized)
        - Snapshot.ts_close must equal bar.ts_close (asserted at runtime)
        - HTF/MTF features are forward-filled from last closed bar
        """
        self._started_at = datetime.now()

        # Prepare data frames
        if self._multi_tf_mode and self._mtf_frames is None:
            self.prepare_multi_tf_frames()
        elif self._prepared_frame is None:
            self.prepare_backtest_frame()

        prepared = self._prepared_frame
        sim_start_idx = prepared.sim_start_index

        # Build FeedStores for O(1) access
        self._build_feed_stores()
        exec_feed = self._exec_feed
        num_bars = exec_feed.length

        # Build incremental state for structure detection
        self._incremental_state = self._build_incremental_state()

        # Build StateRationalizer for Layer 2
        if self._incremental_state is not None:
            self._rationalizer = StateRationalizer(history_depth=1000)
        else:
            self._rationalizer = None

        # Get risk profile and initialize exchange
        risk_profile = self.config.risk_profile
        initial_equity = risk_profile.initial_equity

        self._exchange = SimulatedExchange(
            symbol=self.config.symbol,
            initial_capital=initial_equity,
            execution_config=self.execution_config,
            risk_profile=risk_profile,
        )
        self.risk_manager.reset()

        self.logger.info(
            f"Running backtest: {len(prepared.df)} bars, sim_start_idx={sim_start_idx}, "
            f"warmup_bars={prepared.warmup_bars}, equity=${initial_equity:,.0f}, "
            f"leverage={risk_profile.max_leverage:.1f}x, "
            f"mark_price_source={risk_profile.mark_price_source}"
        )

        debug_log(
            self._play_hash,
            "Engine init",
            symbol=self.config.symbol,
            tf=self.config.tf,
            bars=num_bars,
            warmup=prepared.warmup_bars,
            equity=initial_equity,
        )

        # Initialize processing state
        self._equity_curve = []
        self._account_curve: list[AccountCurvePoint] = []
        prev_bar: CanonicalBar | None = None
        run_start_time = datetime.now()

        # Stop tracking
        stop_classification: StopReason | None = None
        stop_reason_detail: str | None = None
        stop_reason: str | None = None
        stop_ts: datetime | None = None
        stop_bar_index: int | None = None
        stop_details: dict[str, Any] | None = None

        # Create bar processor
        processor = BarProcessor(self, strategy, run_start_time)

        # ========== MAIN BAR LOOP ==========
        for i in range(num_bars):
            bar = processor.build_bar(i)

            if i < sim_start_idx:
                # Warmup period: update state, no trading
                processor.process_warmup_bar(i, bar, prev_bar, sim_start_idx)
            else:
                # Trading period: full evaluation
                result = processor.process_trading_bar(
                    i, bar, prev_bar, sim_start_idx,
                    self._equity_curve, self._account_curve,
                )

                if result.terminal_stop:
                    stop_classification = result.stop_classification
                    stop_reason_detail = result.stop_reason_detail
                    stop_reason = result.stop_reason
                    stop_ts = result.stop_ts
                    stop_bar_index = result.stop_bar_index
                    stop_details = result.stop_details
                    break

            prev_bar = bar
        # ========== END MAIN BAR LOOP ==========

        # Post-loop: close remaining position if not stopped early
        if stop_classification is None and self._exchange.position is not None:
            last_idx = exec_feed.length - 1
            self._exchange.force_close_position(
                float(exec_feed.close[last_idx]),
                exec_feed.get_ts_open_datetime(last_idx),
            )

        if stop_details is None:
            stop_details = self._exchange.get_state()

        # Build result using helper
        return self._build_result(
            prepared=prepared,
            risk_profile=risk_profile,
            initial_equity=initial_equity,
            stop_classification=stop_classification,
            stop_reason_detail=stop_reason_detail,
            stop_reason=stop_reason,
            stop_ts=stop_ts,
            stop_bar_index=stop_bar_index,
            stop_details=stop_details,
        )

    def _build_result(
        self,
        prepared: PreparedFrame,
        risk_profile: RiskProfileConfig,
        initial_equity: float,
        stop_classification: StopReason | None,
        stop_reason_detail: str | None,
        stop_reason: str | None,
        stop_ts: datetime | None,
        stop_bar_index: int | None,
        stop_details: dict[str, Any] | None,
    ) -> BacktestResult:
        """Build BacktestResult from run data."""
        # Calculate drawdowns
        self._calculate_drawdowns()

        # Compute metrics from account curve
        bars_in_position = sum(1 for a in self._account_curve if a.has_position)
        min_margin_ratio = 1.0
        margin_calls = 0
        closest_liquidation_pct = 100.0

        for a in self._account_curve:
            if a.used_margin_usdt > 0:
                ratio = a.equity_usdt / a.used_margin_usdt
                if ratio < min_margin_ratio:
                    min_margin_ratio = ratio
            if a.free_margin_usdt < 0:
                margin_calls += 1
            if a.equity_usdt > 0 and a.maintenance_margin_usdt > 0:
                buffer_pct = (a.equity_usdt - a.maintenance_margin_usdt) / a.equity_usdt * 100
                if buffer_pct < closest_liquidation_pct:
                    closest_liquidation_pct = buffer_pct

        # Leverage metrics
        imr = risk_profile.initial_margin_rate
        leverage_values = []
        max_gross_exposure_pct = 0.0

        for a in self._account_curve:
            if a.has_position and a.used_margin_usdt > 0 and a.equity_usdt > 0 and imr > 0:
                position_value = a.used_margin_usdt / imr
                leverage = position_value / a.equity_usdt
                leverage_values.append(leverage)
                exposure_pct = (position_value / a.equity_usdt) * 100
                if exposure_pct > max_gross_exposure_pct:
                    max_gross_exposure_pct = exposure_pct

        avg_leverage_used = sum(leverage_values) / len(leverage_values) if leverage_values else 0.0

        # Trade quality metrics
        trades = self._exchange.trades
        mae_avg_pct = sum(t.mae_pct for t in trades) / len(trades) if trades else 0.0
        mfe_avg_pct = sum(t.mfe_pct for t in trades) / len(trades) if trades else 0.0

        # Benchmark prices
        exec_feed = self._exec_feed
        sim_start_idx = prepared.sim_start_index
        first_price = float(exec_feed.close[sim_start_idx])
        last_price = float(exec_feed.close[exec_feed.length - 1])

        # Funding totals
        total_funding_paid_usdt = sum(
            max(0.0, -t.funding_pnl) for t in trades if t.is_closed
        )
        total_funding_received_usdt = sum(
            max(0.0, t.funding_pnl) for t in trades if t.is_closed
        )

        # Compute metrics
        metrics = compute_backtest_metrics(
            equity_curve=self._equity_curve,
            trades=trades,
            tf=self.config.tf,
            initial_equity=initial_equity,
            bars_in_position=bars_in_position,
            total_funding_paid_usdt=total_funding_paid_usdt,
            total_funding_received_usdt=total_funding_received_usdt,
            entry_attempts=self._exchange.entry_attempts_count,
            entry_rejections=self._exchange.entry_rejections_count,
            min_margin_ratio=min_margin_ratio,
            margin_calls=margin_calls,
            closest_liquidation_pct=closest_liquidation_pct,
            first_price=first_price,
            last_price=last_price,
            avg_leverage_used=avg_leverage_used,
            max_gross_exposure_pct=max_gross_exposure_pct,
            mae_avg_pct=mae_avg_pct,
            mfe_avg_pct=mfe_avg_pct,
        )

        finished_at = datetime.now()
        run_id = f"run-{uuid.uuid4().hex[:12]}"

        strategies_summary = [
            StrategyInstanceSummary(
                strategy_instance_id=s.strategy_instance_id,
                strategy_id=s.strategy_id,
                strategy_version=s.strategy_version,
                role=s.role,
            )
            for s in self.config.strategies
        ]

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

        stopped_early = stop_classification is not None and stop_classification.is_terminal()

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
            description=self.config.description,
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
            warmup_bars=prepared.warmup_bars,
            max_indicator_lookback=prepared.max_indicator_lookback,
            data_window_requested_start=prepared.requested_start.isoformat(),
            data_window_requested_end=prepared.requested_end.isoformat(),
            data_window_loaded_start=prepared.loaded_start.isoformat() if isinstance(prepared.loaded_start, datetime) else str(prepared.loaded_start),
            data_window_loaded_end=prepared.loaded_end.isoformat() if isinstance(prepared.loaded_end, datetime) else str(prepared.loaded_end),
            simulation_start_ts=prepared.simulation_start,
            trades=trades,
            equity_curve=self._equity_curve,
            artifact_dir=str(self.run_dir) if self.run_dir else None,
            account_curve=self._account_curve,
            run_config_echo=run_config_echo,
            stop_classification=stop_classification,
            stop_reason_detail=stop_reason_detail,
            stopped_early=stopped_early,
            stop_reason=stop_reason,
            stop_ts=stop_ts,
            stop_bar_index=stop_bar_index,
            stop_details=stop_details,
            entries_disabled=self._exchange.entries_disabled,
            first_starved_ts=self._exchange.first_starved_ts,
            first_starved_bar_index=self._exchange.first_starved_bar_index,
            entry_attempts_count=self._exchange.entry_attempts_count,
            entry_rejections_count=self._exchange.entry_rejections_count,
        )

        if self.run_dir:
            self._write_artifacts(result)

        if stopped_early:
            self.logger.info(
                f"Backtest stopped early ({stop_classification.value}): {metrics.total_trades} trades, "
                f"PnL=${metrics.net_profit:,.2f}, Win rate={metrics.win_rate:.1f}%"
            )
        else:
            starved_msg = " (entries disabled)" if self._exchange.entries_disabled else ""
            self.logger.info(
                f"Backtest complete{starved_msg}: {metrics.total_trades} trades, "
                f"PnL=${metrics.net_profit:,.2f}, Win rate={metrics.win_rate:.1f}%"
            )

        elapsed = (finished_at - self._started_at).total_seconds() if self._started_at else 0
        debug_run_complete(
            self._play_hash,
            run_hash=run_id,
            trades_count=metrics.total_trades,
            elapsed_seconds=elapsed,
            artifact_path=str(self.run_dir) if self.run_dir else None,
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
        last_price: float | None = None,
        prev_last_price: float | None = None,
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
            last_price: 1m action price (ticker close) for DSL access
            prev_last_price: Previous 1m action price (for crossover operators)

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
            last_price=last_price,
            prev_last_price=prev_last_price,
            incremental_state=self._incremental_state,
            feature_registry=self._feature_registry,
            rationalized_state=self._rationalized_state,
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
            # Note: This path runs when 1m data is unavailable. For full 1m
            # action semantics, ensure 1m data is synced for your symbol.
            exec_close = float(self._exec_feed.close[exec_idx])
            snapshot = self._build_snapshot_view(
                exec_idx, step_result, rollups, last_price=exec_close
            )
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
        # Track previous 1m price for crossover operators
        prev_price_1m: float | None = None

        # Iterate through 1m bars (mandatory 1m action loop)
        for sub_idx in range(start_1m, end_1m + 1):
            # Get 1m close as both mark_price and last_price
            price_1m = float(self._quote_feed.close[sub_idx])

            # Build snapshot with 1m prices
            snapshot = self._build_snapshot_view(
                exec_idx=exec_idx,
                step_result=step_result,
                rollups=rollups,
                mark_price_override=price_1m,
                last_price=price_1m,
                prev_last_price=prev_price_1m,
            )
            last_snapshot = snapshot
            # Update previous price for next iteration
            prev_price_1m = price_1m

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
            exec_close = float(self._exec_feed.close[exec_idx])
            last_snapshot = self._build_snapshot_view(
                exec_idx, step_result, rollups, last_price=exec_close
            )

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
                # Check for partial exit percentage in metadata
                exit_percent = 100.0
                if signal.metadata and "exit_percent" in signal.metadata:
                    exit_percent = signal.metadata["exit_percent"]
                exchange.submit_close(reason="signal", percent=exit_percent)
            return
        
        # Skip if we already have a position
        if exchange.position is not None:
            return

        # Skip if we already have pending orders
        if exchange.get_open_orders():
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

        # Debug: log signal before order submission
        # Get bar_idx from snapshot if available
        bar_idx = getattr(snapshot, "_exec_idx", None)
        debug_signal(
            self._play_hash,
            bar_idx=bar_idx or 0,
            action=f"ENTRY_{side.upper()}",
            feature_values={"size_usdt": size_usdt, "sl": stop_loss, "tp": take_profit},
        )

        # Submit order (use signal_ts if provided, else bar.ts_close)
        order_timestamp = signal_ts if signal_ts is not None else bar.ts_close
        exchange.submit_order(
            side=side,
            size_usdt=size_usdt,
            stop_loss=stop_loss,
            take_profit=take_profit,
            timestamp=order_timestamp,
        )

        # Debug: log trade opened
        trade_count = len(exchange.trades) + 1  # Next trade number
        debug_trade(
            self._play_hash,
            bar_idx=bar_idx or 0,
            event="opened",
            trade_num=trade_count,
            entry=bar.close,
            sl=stop_loss,
            tp=take_profit,
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


# NOTE: Factory functions (run_backtest, create_engine_from_play, run_engine_with_play)
# are now in engine_factory.py and imported at the top of this module for backward compatibility.
