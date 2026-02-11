"""
DataBuilder - Standalone data preparation for backtests.

Provides clean, stateless data building for PlayEngine backtests.
This is the canonical way to prepare backtest data components.

Uses 3-feed + exec role system:
- low_tf_feed, med_tf_feed, high_tf_feed: actual data feeds
- exec: role pointer to which feed we step on

Usage:
    window = config.get_window(window_name)
    builder = DataBuilder(
        config=system_config,
        window=window,
        play=play,
        tf_mapping=tf_mapping,
    )
    result = builder.build()
    # result.low_tf_feed, result.med_tf_feed, result.high_tf_feed
    # result.exec_feed  # property that resolves based on exec role
    # result.sim_exchange, result.incremental_state, result.prepared_frame
"""

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from .engine_data_prep import (
    PreparedFrame,
    MultiTFPreparedFrames,
    prepare_backtest_frame_impl,
    prepare_multi_tf_frames_impl,
    load_1m_data_impl,
    load_funding_data_impl,
    load_open_interest_data_impl,
)
from .engine_feed_builder import (
    build_feed_stores_impl,
    build_quote_feed_impl,
    build_market_data_arrays_impl,
)
from .runtime.feed_store import FeedStore, MultiTFFeedStore
from .sim.exchange import SimulatedExchange
from .system_config import SystemConfig
from src.structures.state import MultiTFIncrementalState, TFIncrementalState

if TYPE_CHECKING:
    from .play.play import Play
    from .types import WindowConfig
    from src.forge.validation.synthetic_provider import SyntheticDataProvider


@dataclass
class DataBuildResult:
    """Complete result of data preparation for backtest."""

    # 3-Feed System (O(1) array access)
    # low_tf, med_tf, high_tf are the actual feeds
    # exec is a POINTER to which feed we step on
    low_tf_feed: FeedStore
    med_tf_feed: FeedStore | None  # None if same as low_tf
    high_tf_feed: FeedStore | None  # None if same as med_tf

    # Quote feed (1m data for mark price proxy)
    quote_feed: FeedStore | None

    # Multi-TF container (holds all feeds + exec_role)
    multi_tf_feed_store: MultiTFFeedStore

    # Simulation exchange
    sim_exchange: SimulatedExchange

    # Structure detection state
    incremental_state: MultiTFIncrementalState | None

    # Metadata for runner
    prepared_frame: PreparedFrame
    multi_tf_frames: MultiTFPreparedFrames | None
    warmup_bars: int
    sim_start_idx: int
    multi_tf_mode: bool
    tf_mapping: dict[str, str]  # {low_tf, med_tf, high_tf -> TF string, exec -> role}

    @property
    def exec_feed(self) -> FeedStore:
        """Resolved exec feed based on exec role pointer."""
        return self.multi_tf_feed_store.exec_feed


class DataBuilder:
    """
    Standalone data preparation builder.

    Handles all data loading and preparation for backtests.
    All data prep logic delegates to existing *_impl() functions.

    Usage:
        # SystemConfig is built in engine_factory.py with all Play parsing
        window = config.get_window(window_name)
        builder = DataBuilder(
            config=system_config,
            window=window,
            play=play,
            tf_mapping=tf_mapping,
            synthetic_provider=synthetic_provider,
        )
        result = builder.build()
    """

    def __init__(
        self,
        config: SystemConfig,
        window: "WindowConfig",
        play: "Play",
        tf_mapping: dict[str, str],
        synthetic_provider: "SyntheticDataProvider | None" = None,
    ):
        self.config = config
        self.window = window
        self.play = play
        self.tf_mapping = tf_mapping
        self.synthetic_provider = synthetic_provider
        self._logger = None

    def build(self) -> DataBuildResult:
        """
        Build all data components for backtest.

        Returns:
            DataBuildResult with all pre-built components ready for PlayEngine.
        """
        from ..utils.logger import get_logger

        self._logger = get_logger(__name__)

        config = self.config
        tf_mapping = self.tf_mapping

        # Determine multi-TF mode
        low_tf_str = tf_mapping["low_tf"]
        multi_tf_mode = (
            tf_mapping["high_tf"] != low_tf_str or
            tf_mapping["med_tf"] != low_tf_str
        )

        # Step 1: Prepare data frames (load data, compute indicators)
        prepared_frame: PreparedFrame
        multi_tf_frames: MultiTFPreparedFrames | None = None

        if multi_tf_mode:
            multi_tf_frames = prepare_multi_tf_frames_impl(
                config=config,
                window=self.window,
                tf_mapping=tf_mapping,
                multi_tf_mode=multi_tf_mode,
                logger=self._logger,
                synthetic_provider=self.synthetic_provider,
            )
            # Create PreparedFrame wrapper for API consistency
            exec_role = tf_mapping["exec"]
            exec_tf = tf_mapping[exec_role]
            assert multi_tf_frames.exec_frame is not None, "exec_frame must be set after multi-TF preparation"
            assert multi_tf_frames.requested_start is not None, "requested_start must be set"
            assert multi_tf_frames.requested_end is not None, "requested_end must be set"
            assert multi_tf_frames.simulation_start is not None, "simulation_start must be set"
            prepared_frame = PreparedFrame(
                df=multi_tf_frames.exec_frame,
                full_df=multi_tf_frames.exec_frame,
                warmup_bars=multi_tf_frames.warmup_bars,
                max_indicator_lookback=multi_tf_frames.max_indicator_lookback,
                requested_start=multi_tf_frames.requested_start,
                requested_end=multi_tf_frames.requested_end,
                loaded_start=multi_tf_frames.requested_start,
                loaded_end=multi_tf_frames.requested_end,
                simulation_start=multi_tf_frames.simulation_start,
                sim_start_index=multi_tf_frames.exec_sim_start_index,
            )
        else:
            prepared_frame = prepare_backtest_frame_impl(
                config=config,
                window=self.window,
                logger=self._logger,
                synthetic_provider=self.synthetic_provider,
            )

        # Step 2: Build FeedStores (3-feed + exec role system)
        multi_tf_feed_store, resolved_exec_feed, high_tf_feed, med_tf_feed = build_feed_stores_impl(
            config=config,
            tf_mapping=tf_mapping,
            multi_tf_mode=multi_tf_mode,
            multi_tf_frames=multi_tf_frames,
            prepared_frame=prepared_frame,
            data=prepared_frame.df,
            logger=self._logger,
        )

        # Extract low_tf_feed from multi_tf_feed_store
        low_tf_feed = multi_tf_feed_store.low_tf_feed

        # Step 3: Build quote feed (1m data)
        quote_feed = self._build_quote_feed(config, prepared_frame)

        # Step 4: Build market data (funding, OI) into exec feed
        self._build_market_data(config, prepared_frame, resolved_exec_feed)

        # Step 5: Build SimulatedExchange
        sim_exchange = self._build_sim_exchange(config)

        # Step 6: Build incremental state for structures
        incremental_state = self._build_incremental_state(config, tf_mapping)

        return DataBuildResult(
            low_tf_feed=low_tf_feed,
            med_tf_feed=med_tf_feed,
            high_tf_feed=high_tf_feed,
            quote_feed=quote_feed,
            multi_tf_feed_store=multi_tf_feed_store,
            sim_exchange=sim_exchange,
            incremental_state=incremental_state,
            prepared_frame=prepared_frame,
            multi_tf_frames=multi_tf_frames,
            warmup_bars=prepared_frame.warmup_bars,
            sim_start_idx=prepared_frame.sim_start_index,
            multi_tf_mode=multi_tf_mode,
            tf_mapping=tf_mapping,
        )

    def _build_quote_feed(
        self,
        config: SystemConfig,
        prepared_frame: PreparedFrame,
    ) -> FeedStore | None:
        """Build 1m quote feed for mark price proxy."""
        from .runtime.timeframe import tf_duration

        # Compute 1m warmup (match exec TF warmup in 1m bars)
        exec_tf = config.resolved_exec_tf
        tf_minutes = tf_duration(exec_tf).total_seconds() / 60
        warmup_bars_1m = int(prepared_frame.warmup_bars * tf_minutes)

        # Load 1m data
        df_1m = load_1m_data_impl(
            symbol=config.symbol,
            window_start=prepared_frame.requested_start,
            window_end=prepared_frame.requested_end,
            warmup_bars_1m=warmup_bars_1m,
            data_env=config.data_build.env,
            logger=self._logger,
            synthetic_provider=self.synthetic_provider,
        )

        if df_1m is None or df_1m.empty:
            return None

        return build_quote_feed_impl(df_1m, config.symbol, self._logger)

    def _build_market_data(
        self,
        config: SystemConfig,
        prepared_frame: PreparedFrame,
        exec_feed: FeedStore,
    ) -> None:
        """Load and attach funding rate and OI data to exec feed."""
        # Load funding data
        funding_df = load_funding_data_impl(
            symbol=config.symbol,
            window_start=prepared_frame.simulation_start,
            window_end=prepared_frame.requested_end,
            data_env=config.data_build.env,
            logger=self._logger,
        )

        # Load open interest data
        oi_df = load_open_interest_data_impl(
            symbol=config.symbol,
            window_start=prepared_frame.simulation_start,
            window_end=prepared_frame.requested_end,
            data_env=config.data_build.env,
            logger=self._logger,
        )

        # Build arrays aligned to exec feed
        funding_arr, oi_arr, settlement_times = build_market_data_arrays_impl(
            funding_df=funding_df,
            oi_df=oi_df,
            exec_feed=exec_feed,
            logger=self._logger,
        )

        exec_feed.funding_rate = funding_arr
        exec_feed.open_interest = oi_arr
        exec_feed.funding_settlement_times = settlement_times

    def _build_sim_exchange(self, config: SystemConfig) -> SimulatedExchange:
        """Create SimulatedExchange with config."""
        from .sim.exchange import SimulatedExchange
        from .sim.types import ExecutionConfig

        # Get slippage from Play (with default)
        slippage_bps = 5.0  # Default
        if self.play.account and self.play.account.slippage_bps is not None:
            slippage_bps = self.play.account.slippage_bps

        # Build execution config - only slippage, fees come from risk_profile
        exec_config = ExecutionConfig(
            slippage_bps=slippage_bps,
        )

        return SimulatedExchange(
            symbol=config.symbol,
            initial_capital=config.risk_profile.initial_equity,
            execution_config=exec_config,
            risk_profile=config.risk_profile,
        )

    def _build_incremental_state(
        self,
        config: SystemConfig,
        tf_mapping: dict[str, str],
    ) -> MultiTFIncrementalState | None:
        """Build incremental state for structure detection."""
        registry = self.play.feature_registry
        if registry is None:
            return None

        structures = registry.get_structures()
        if not structures:
            return None

        exec_tf = registry.execution_tf

        # Resolve med_tf and high_tf strings from tf_mapping
        med_tf_str = tf_mapping.get("med_tf", exec_tf)
        high_tf_str = tf_mapping.get("high_tf", exec_tf)

        # Group structures by TF role, converting Feature to spec dict
        exec_specs: list[dict] = []
        med_tf_configs: dict[str, list[dict]] = {}
        high_tf_configs: dict[str, list[dict]] = {}

        for feature in structures:
            # Convert Feature object to spec dict
            spec_dict = {
                "type": feature.structure_type,
                "key": feature.id,
                "params": dict(feature.params) if feature.params else {},
            }
            if feature.uses:
                spec_dict["uses"] = list(feature.uses)

            if feature.tf == exec_tf:
                exec_specs.append(spec_dict)
            elif feature.tf == med_tf_str and med_tf_str != exec_tf:
                # Medium timeframe structure
                if feature.tf not in med_tf_configs:
                    med_tf_configs[feature.tf] = []
                med_tf_configs[feature.tf].append(spec_dict)
            else:
                # Higher timeframe structure (high_tf or any other non-exec/non-med TF)
                if feature.tf not in high_tf_configs:
                    high_tf_configs[feature.tf] = []
                high_tf_configs[feature.tf].append(spec_dict)

        # Create incremental state
        state = MultiTFIncrementalState(
            exec_tf=exec_tf,
            exec_specs=exec_specs,
            med_tf_configs=med_tf_configs if med_tf_configs else None,
            high_tf_configs=high_tf_configs if high_tf_configs else None,
        )

        return state
