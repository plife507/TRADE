"""
Backtest engine.

Main orchestrator for deterministic backtesting:
1. Load candles from DuckDB (multi-TF support)
2. Compute indicators per TF DataFrame
3. Run bar-by-bar simulation with risk-based sizing
4. Generate structured BacktestResult with metrics
5. Write artifacts (trades.csv, equity.csv, result.json)

Usage:
    from src.backtest import BacktestEngine, load_system_config
    
    config = load_system_config("SOLUSDT_5m_ema_rsi_atr_pure", "hygiene")
    engine = BacktestEngine(config, "hygiene")
    result = engine.run(strategy)
    
Phase 1: Uses canonical Bar (ts_open/ts_close) for proper timing semantics.
- ts_open: when bar starts, fills occur
- ts_close: when bar ends, strategy evaluates, MTM updates

Phase 3: Multi-TF support with data-driven close detection.
- HTF/MTF/LTF feature caching
- Data-driven close detection via close_ts maps
- Readiness gate blocks trading until all TF caches are ready

Phase 4: Unified mark price handling.
- Exchange computes mark_price exactly once per step via PriceModel
- StepResult includes ts_close, mark_price, mark_price_source
- SnapshotBuilder gets mark_price from exchange (no PriceModel calls)
- All MTM/liquidation uses the same mark_price
"""

import json
import pandas as pd
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Callable, List, Dict, Any, Set
import uuid

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
from .runtime.timeframe import tf_duration, tf_minutes, validate_tf_mapping
from .runtime.snapshot_builder import SnapshotBuilder, build_exchange_state_from_exchange
from .runtime.cache import TimeframeCache, build_close_ts_map_from_df
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
from .proof_metrics import compute_proof_metrics

from ..core.risk_manager import Signal
from ..data.historical_data_store import get_historical_store, TF_MINUTES
from ..utils.logger import get_logger


# Dataclass to hold prepared frame metadata
@dataclass
class PreparedFrame:
    """Result of prepare_backtest_frame with metadata."""
    df: pd.DataFrame  # DataFrame ready for simulation (trimmed to sim_start)
    full_df: pd.DataFrame  # Full DataFrame with indicators (includes warm-up data)
    warmup_bars: int
    warmup_multiplier: int
    max_indicator_lookback: int
    requested_start: datetime
    requested_end: datetime
    loaded_start: datetime
    loaded_end: datetime
    simulation_start: datetime
    sim_start_index: int  # Index in full_df where simulation starts


@dataclass
class MultiTFPreparedFrames:
    """
    Multi-timeframe prepared frames with close_ts maps for data-driven caching.
    
    Phase 3: Supports HTF/MTF/LTF data loading and indicator precomputation.
    """
    # TF mapping (htf, mtf, ltf -> tf string)
    tf_mapping: Dict[str, str]
    
    # DataFrames with indicators per TF (key = tf string, e.g., "4h", "1h", "5m")
    frames: Dict[str, pd.DataFrame] = field(default_factory=dict)
    
    # Close timestamp sets per TF (for data-driven close detection)
    close_ts_maps: Dict[str, Set[datetime]] = field(default_factory=dict)
    
    # LTF is the primary (simulation stepping)
    ltf_frame: Optional[pd.DataFrame] = None
    ltf_sim_start_index: int = 0
    
    # Warmup metadata
    warmup_bars: int = 0
    warmup_multiplier: int = 5
    max_indicator_lookback: int = 0
    
    # Window metadata
    requested_start: Optional[datetime] = None
    requested_end: Optional[datetime] = None
    simulation_start: Optional[datetime] = None
    
    def get_htf_close_ts(self) -> Set[datetime]:
        """Get HTF close timestamps for cache detection."""
        htf_tf = self.tf_mapping.get("htf", "")
        return self.close_ts_maps.get(htf_tf, set())
    
    def get_mtf_close_ts(self) -> Set[datetime]:
        """Get MTF close timestamps for cache detection."""
        mtf_tf = self.tf_mapping.get("mtf", "")
        return self.close_ts_maps.get(mtf_tf, set())
    
    def get_ltf_close_ts(self) -> Set[datetime]:
        """Get LTF close timestamps for cache detection."""
        ltf_tf = self.tf_mapping.get("ltf", "")
        return self.close_ts_maps.get(ltf_tf, set())


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
        run_dir: Optional[Path] = None,
        tf_mapping: Optional[Dict[str, str]] = None,
    ):
        """
        Initialize backtest engine.
        
        Args:
            config: System configuration (with resolved risk profile)
            window_name: Window to use ("hygiene" or "test")
            run_dir: Optional directory for writing artifacts
            tf_mapping: Optional dict mapping htf/mtf/ltf to timeframe strings.
                        If None, single-TF mode (all roles = config.tf).
        """
        self.config = config
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
        
        # Execution config from params
        params = config.params
        self.execution_config = ExecutionConfig(
            taker_fee_bps=params.get("taker_fee_bps", 6.0),
            slippage_bps=params.get("slippage_bps", 5.0),
        )
        
        # State
        self._data: Optional[pd.DataFrame] = None
        self._prepared_frame: Optional[PreparedFrame] = None
        self._mtf_frames: Optional[MultiTFPreparedFrames] = None  # Phase 3
        self._exchange: Optional[SimulatedExchange] = None
        self._equity_curve: List[EquityPoint] = []
        self._started_at: Optional[datetime] = None
        
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
        
        # Phase 1: History management
        # Parse history config from system config (if present)
        self._history_config = self._parse_history_config(config)
        
        # Rolling history windows (mutable lists, converted to tuples for snapshot)
        self._history_bars_exec: List[CanonicalBar] = []
        self._history_features_exec: List[FeatureSnapshot] = []
        self._history_features_htf: List[FeatureSnapshot] = []
        self._history_features_mtf: List[FeatureSnapshot] = []
        
        # Phase 2/3: SnapshotBuilder for RuntimeSnapshot construction
        self._snapshot_builder = SnapshotBuilder(
            symbol=config.symbol,
            tf_mapping=self._tf_mapping,
            history_config=self._history_config,
        )
        
        # Phase 3: TimeframeCache for HTF/MTF carry-forward
        self._tf_cache = TimeframeCache()
        
        # Phase 3: Indicator DataFrames per TF (populated in prepare_multi_tf_frames)
        self._htf_df: Optional[pd.DataFrame] = None
        self._mtf_df: Optional[pd.DataFrame] = None
        self._ltf_df: Optional[pd.DataFrame] = None
        
        # Phase 3: Readiness gate tracking
        self._warmup_complete = False
        self._first_ready_bar_index: Optional[int] = None
        
        tf_mode_str = "multi-TF" if self._multi_tf_mode else "single-TF"
        self.logger.info(
            f"BacktestEngine initialized: {config.system_id} / {window_name} / "
            f"risk_mode={config.risk_mode} / initial_equity={config.risk_profile.initial_equity} / "
            f"mode={tf_mode_str} / tf_mapping={self._tf_mapping}"
        )
    
    def _parse_history_config(self, config: SystemConfig) -> HistoryConfig:
        """
        Parse HistoryConfig from system config.
        
        Looks for optional 'history' section in params or config.
        
        Args:
            config: System configuration
            
        Returns:
            HistoryConfig (default if not specified)
        """
        # Check params for history config
        params = config.params
        history_raw = params.get("history", {})
        
        if not history_raw:
            return DEFAULT_HISTORY_CONFIG
        
        return HistoryConfig(
            bars_exec_count=int(history_raw.get("bars_exec_count", 0)),
            features_exec_count=int(history_raw.get("features_exec_count", 0)),
            features_htf_count=int(history_raw.get("features_htf_count", 0)),
            features_mtf_count=int(history_raw.get("features_mtf_count", 0)),
        )
    
    def _update_history(
        self,
        bar: CanonicalBar,
        features_exec: FeatureSnapshot,
        htf_updated: bool,
        mtf_updated: bool,
        features_htf: Optional[FeatureSnapshot],
        features_mtf: Optional[FeatureSnapshot],
    ) -> None:
        """
        Update rolling history windows.
        
        Called after each bar close, before snapshot build.
        Maintains bounded windows per HistoryConfig.
        
        Args:
            bar: Current exec-TF bar
            features_exec: Current exec-TF features
            htf_updated: Whether HTF cache was updated this step
            mtf_updated: Whether MTF cache was updated this step
            features_htf: Current HTF features (if updated)
            features_mtf: Current MTF features (if updated)
        """
        config = self._history_config
        
        # Update exec bar history
        if config.bars_exec_count > 0:
            self._history_bars_exec.append(bar)
            # Trim to max size (keep most recent)
            if len(self._history_bars_exec) > config.bars_exec_count:
                self._history_bars_exec = self._history_bars_exec[-config.bars_exec_count:]
        
        # Update exec feature history
        if config.features_exec_count > 0 and features_exec.ready:
            self._history_features_exec.append(features_exec)
            if len(self._history_features_exec) > config.features_exec_count:
                self._history_features_exec = self._history_features_exec[-config.features_exec_count:]
        
        # Update HTF feature history (only on HTF close)
        if config.features_htf_count > 0 and htf_updated and features_htf and features_htf.ready:
            self._history_features_htf.append(features_htf)
            if len(self._history_features_htf) > config.features_htf_count:
                self._history_features_htf = self._history_features_htf[-config.features_htf_count:]
        
        # Update MTF feature history (only on MTF close)
        if config.features_mtf_count > 0 and mtf_updated and features_mtf and features_mtf.ready:
            self._history_features_mtf.append(features_mtf)
            if len(self._history_features_mtf) > config.features_mtf_count:
                self._history_features_mtf = self._history_features_mtf[-config.features_mtf_count:]
    
    def _is_history_ready(self) -> bool:
        """
        Check if required history windows are filled.
        
        Returns:
            True if all configured history windows are at required depth,
            or if no history is configured.
        """
        config = self._history_config
        
        if not config.requires_history:
            return True
        
        # Check each configured window
        if config.bars_exec_count > 0:
            if len(self._history_bars_exec) < config.bars_exec_count:
                return False
        
        if config.features_exec_count > 0:
            if len(self._history_features_exec) < config.features_exec_count:
                return False
        
        if config.features_htf_count > 0:
            if len(self._history_features_htf) < config.features_htf_count:
                return False
        
        if config.features_mtf_count > 0:
            if len(self._history_features_mtf) < config.features_mtf_count:
                return False
        
        return True
    
    def _get_history_tuples(self) -> tuple:
        """
        Get immutable history tuples for snapshot.
        
        Returns:
            Tuple of (bars_exec, features_exec, features_htf, features_mtf)
        """
        return (
            tuple(self._history_bars_exec),
            tuple(self._history_features_exec),
            tuple(self._history_features_htf),
            tuple(self._history_features_mtf),
        )
    
    def _timeframe_to_timedelta(self, tf: str) -> timedelta:
        """Convert timeframe string to timedelta."""
        tf_minutes = TF_MINUTES.get(tf.lower(), 60)  # Default to 1h
        return timedelta(minutes=tf_minutes)
    
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
        
        Returns:
            PreparedFrame with DataFrame and metadata
            
        Raises:
            ValueError: If not enough data for warm-up + window, or invalid config
        """
        # =====================================================================
        # Mode Lock Validations (BEFORE data fetch)
        # Fail fast without downloading data for invalid configs.
        # =====================================================================
        if self.config.symbol:
            validate_usdt_pair(self.config.symbol)
        validate_margin_mode_isolated(self.config.risk_profile.margin_mode)
        validate_quote_ccy_and_instrument_type(
            self.config.risk_profile.quote_ccy,
            self.config.risk_profile.instrument_type,
        )
        
        store = get_historical_store(env=self.config.data_build.env)
        
        # Compute warm-up parameters from FeatureSpecs (IdeaCard-driven)
        warmup_multiplier = self.config.warmup_multiplier
        exec_specs = self.config.feature_specs_by_role.get('exec', []) if hasattr(self.config, 'feature_specs_by_role') else []
        warmup_bars = get_warmup_from_specs(exec_specs, warmup_multiplier)
        
        # max_lookback is the raw max warmup from specs (without multiplier)
        max_lookback = get_warmup_from_specs(exec_specs, warmup_multiplier=1) if exec_specs else 0
        
        # Convert warmup_bars to time span
        tf_delta = self._timeframe_to_timedelta(self.config.tf)
        warmup_span = tf_delta * warmup_bars
        
        # Requested window from config
        requested_start = self.window.start
        requested_end = self.window.end
        
        # Extended query range (pull data before window for warm-up)
        extended_start = requested_start - warmup_span
        
        self.logger.info(
            f"Loading data: {self.config.symbol} {self.config.tf} "
            f"from {extended_start} to {requested_end} "
            f"(warm-up: {warmup_bars} bars = {warmup_span})"
        )
        
        # Load extended data
        df = store.get_ohlcv(
            symbol=self.config.symbol,
            tf=self.config.tf,
            start=extended_start,
            end=requested_end,
        )
        
        # Validate data exists
        if df.empty:
            raise ValueError(
                f"No data found for {self.config.symbol} {self.config.tf} "
                f"from {extended_start} to {requested_end}. "
                f"Run data sync first: sync_symbols(['{self.config.symbol}'], "
                f"period='{self.config.data_build.period}')"
            )
        
        # Ensure sorted by timestamp
        df = df.sort_values("timestamp").reset_index(drop=True)
        
        # Track actual loaded range (may be clamped to dataset boundaries)
        loaded_start = df["timestamp"].iloc[0]
        loaded_end = df["timestamp"].iloc[-1]
        
        self.logger.info(
            f"Loaded {len(df)} bars: {loaded_start} to {loaded_end}"
        )
        
        # Apply indicators from IdeaCard FeatureSpecs (ONLY supported path)
        # No legacy params-based indicators - IdeaCard is the single source of truth
        if hasattr(self.config, 'feature_specs_by_role') and self.config.feature_specs_by_role:
            exec_specs = self.config.feature_specs_by_role.get('exec', [])
            if exec_specs:
                df = apply_feature_spec_indicators(df, exec_specs)
        else:
            raise ValueError(
                "No feature_specs_by_role in config. "
                "IdeaCard with declared FeatureSpecs is required. "
                "Legacy params-based indicators are not supported."
            )
        
        # Find first bar where all required indicators are valid
        # Use IdeaCard specs to get required columns
        if hasattr(self.config, 'feature_specs_by_role') and self.config.feature_specs_by_role:
            exec_specs = self.config.feature_specs_by_role.get('exec', [])
            required_cols = get_required_indicator_columns_from_specs(exec_specs)
        else:
            required_cols = []  # Will fail validation
        
        first_valid_idx = find_first_valid_bar(df, required_cols)
        
        if first_valid_idx < 0:
            raise ValueError(
                f"No valid bars found for {self.config.symbol} {self.config.tf}. "
                f"All indicator columns have NaN values. Check data quality."
            )
        
        first_valid_ts = df.iloc[first_valid_idx]["timestamp"]
        
        # Simulation starts at max(first_valid_bar, requested_start)
        # We never start before the requested window, even if indicators are valid earlier
        if first_valid_ts >= requested_start:
            sim_start_ts = first_valid_ts
            sim_start_idx = first_valid_idx
        else:
            # Find the first bar >= requested_start
            mask = df["timestamp"] >= requested_start
            if not mask.any():
                raise ValueError(
                    f"No data found at or after requested window start {requested_start}. "
                    f"Loaded data ends at {loaded_end}."
                )
            sim_start_idx = mask.idxmax()
            sim_start_ts = df.iloc[sim_start_idx]["timestamp"]
        
        # Validate we have enough data for simulation
        if sim_start_ts > requested_end:
            raise ValueError(
                f"Not enough history for {self.config.symbol} {self.config.tf} "
                f"to satisfy warm-up + window. Simulation would start at {sim_start_ts}, "
                f"but requested window ends at {requested_end}. "
                f"Adjust warmup_multiplier (current: {warmup_multiplier}) or window dates."
            )
        
        # Check we have at least some bars for simulation
        sim_bars = len(df) - sim_start_idx
        if sim_bars < 10:
            raise ValueError(
                f"Insufficient simulation bars: got {sim_bars} bars after warm-up, "
                f"need at least 10 trading bars."
            )
        
        self.logger.info(
            f"Simulation start: {sim_start_ts} (bar {sim_start_idx}), "
            f"{sim_bars} bars available for trading"
        )
        
        # Create PreparedFrame
        prepared = PreparedFrame(
            df=df,  # Full DF with indicators, engine will handle sim_start_idx
            full_df=df,
            warmup_bars=warmup_bars,
            warmup_multiplier=warmup_multiplier,
            max_indicator_lookback=max_lookback,
            requested_start=requested_start,
            requested_end=requested_end,
            loaded_start=loaded_start,
            loaded_end=loaded_end,
            simulation_start=sim_start_ts,
            sim_start_index=sim_start_idx,
        )
        
        self._prepared_frame = prepared
        self._data = df
        
        return prepared
    
    def load_data(self) -> pd.DataFrame:
        """
        Load and validate candle data from DuckDB.
        
        Delegates to prepare_backtest_frame() which handles warm-up properly.
        
        Returns:
            DataFrame with OHLCV data and indicators
            
        Raises:
            ValueError: If data is empty, has gaps, or is invalid
        """
        prepared = self.prepare_backtest_frame()
        return prepared.df
    
    def prepare_multi_tf_frames(self) -> MultiTFPreparedFrames:
        """
        Prepare multi-TF DataFrames with indicators and close_ts maps.
        
        Phase 3: Loads data for HTF, MTF, and LTF timeframes, applies
        indicators to each, and builds close_ts maps for data-driven
        cache detection.
        
        Returns:
            MultiTFPreparedFrames with all TF data and metadata
            
        Raises:
            ValueError: If data is missing or invalid
        """
        store = get_historical_store(env=self.config.data_build.env)
        
        # Compute warm-up parameters from FeatureSpecs (IdeaCard-driven)
        ltf_tf = self._tf_mapping["ltf"]
        htf_tf = self._tf_mapping["htf"]
        warmup_multiplier = self.config.warmup_multiplier
        
        # Get warmup for each TF role
        specs_by_role = self.config.feature_specs_by_role if hasattr(self.config, 'feature_specs_by_role') else {}
        exec_specs = specs_by_role.get('exec', [])
        htf_specs = specs_by_role.get('htf', [])
        
        warmup_bars = get_warmup_from_specs(exec_specs, warmup_multiplier)
        htf_warmup_bars = get_warmup_from_specs(htf_specs, warmup_multiplier)
        
        # max_lookback is the raw max warmup from specs (without multiplier)
        max_lookback = get_warmup_from_specs(exec_specs, warmup_multiplier=1) if exec_specs else 0
        
        # Convert warmup_bars to time span (based on LTF)
        ltf_delta = tf_duration(ltf_tf)
        warmup_span = ltf_delta * warmup_bars
        
        # Requested window from config
        requested_start = self.window.start
        requested_end = self.window.end
        
        # Extended query range (pull data before window for warm-up)
        extended_start = requested_start - warmup_span
        
        # Add extra buffer for HTF warm-up (HTF needs more history)
        htf_delta = tf_duration(htf_tf)
        htf_warmup_span = htf_delta * htf_warmup_bars
        
        # Use the larger warm-up span
        data_start = min(extended_start, requested_start - htf_warmup_span)
        
        self.logger.info(
            f"Loading multi-TF data: {self.config.symbol} "
            f"HTF={htf_tf}, MTF={self._tf_mapping['mtf']}, LTF={ltf_tf} "
            f"from {data_start} to {requested_end} "
            f"(warmup: {warmup_bars} LTF bars)"
        )
        
        # Load data for each unique TF
        unique_tfs = set(self._tf_mapping.values())
        frames: Dict[str, pd.DataFrame] = {}
        close_ts_maps: Dict[str, Set[datetime]] = {}
        
        for tf in unique_tfs:
            df = store.get_ohlcv(
                symbol=self.config.symbol,
                tf=tf,
                start=data_start,
                end=requested_end,
            )
            
            if df.empty:
                raise ValueError(
                    f"No data found for {self.config.symbol} {tf} "
                    f"from {data_start} to {requested_end}. "
                    f"Run data sync first."
                )
            
            # Ensure sorted by timestamp
            df = df.sort_values("timestamp").reset_index(drop=True)
            
            # Apply indicators from IdeaCard FeatureSpecs for this TF
            # Map TF back to role (htf/mtf/exec) to get correct specs
            tf_role = None
            for role, role_tf in self._tf_mapping.items():
                if role_tf == tf:
                    tf_role = role
                    break
            
            if hasattr(self.config, 'feature_specs_by_role') and self.config.feature_specs_by_role:
                # Try role-specific specs first, fallback to exec
                specs = self.config.feature_specs_by_role.get(tf_role) or \
                        self.config.feature_specs_by_role.get('exec', [])
                if specs:
                    df = apply_feature_spec_indicators(df, specs)
            else:
                raise ValueError(
                    f"No feature_specs_by_role in config for TF {tf}. "
                    "IdeaCard with declared FeatureSpecs is required."
                )
            
            # Add ts_close column for close detection
            tf_delta = tf_duration(tf)
            df["ts_close"] = df["timestamp"] + tf_delta
            
            # Build close_ts map from this TF's data
            close_ts_maps[tf] = build_close_ts_map_from_df(df, ts_close_column="ts_close")
            
            frames[tf] = df
            
            self.logger.debug(
                f"Loaded {len(df)} bars for {tf}, "
                f"{len(close_ts_maps[tf])} close timestamps"
            )
        
        # Get the LTF frame for simulation stepping
        ltf_frame = frames[ltf_tf]
        
        # Find first valid bar in LTF where all indicators are ready
        # Use IdeaCard specs to get required columns
        if hasattr(self.config, 'feature_specs_by_role') and self.config.feature_specs_by_role:
            exec_specs = self.config.feature_specs_by_role.get('exec', [])
            required_cols = get_required_indicator_columns_from_specs(exec_specs)
        else:
            required_cols = []  # Will fail validation
        
        first_valid_idx = find_first_valid_bar(ltf_frame, required_cols)
        
        if first_valid_idx < 0:
            raise ValueError(
                f"No valid bars found for {self.config.symbol} {ltf_tf}. "
                f"All indicator columns have NaN values."
            )
        
        first_valid_ts = ltf_frame.iloc[first_valid_idx]["timestamp"]
        
        # Simulation starts at max(first_valid_bar, requested_start)
        if first_valid_ts >= requested_start:
            sim_start_ts = first_valid_ts
            sim_start_idx = first_valid_idx
        else:
            mask = ltf_frame["timestamp"] >= requested_start
            if not mask.any():
                raise ValueError(
                    f"No data found at or after requested window start {requested_start}."
                )
            sim_start_idx = mask.idxmax()
            sim_start_ts = ltf_frame.iloc[sim_start_idx]["timestamp"]
        
        # Validate enough data for simulation
        sim_bars = len(ltf_frame) - sim_start_idx
        if sim_bars < 10:
            raise ValueError(
                f"Insufficient simulation bars: got {sim_bars} bars after warm-up."
            )
        
        self.logger.info(
            f"Multi-TF simulation start: {sim_start_ts} (bar {sim_start_idx}), "
            f"{sim_bars} LTF bars available"
        )
        
        # Configure TimeframeCache with close_ts maps
        htf_close_ts = close_ts_maps.get(htf_tf, set())
        mtf_close_ts = close_ts_maps.get(self._tf_mapping["mtf"], set())
        
        self._tf_cache.set_close_ts_maps(
            htf_close_ts=htf_close_ts,
            mtf_close_ts=mtf_close_ts,
            htf_tf=htf_tf,
            mtf_tf=self._tf_mapping["mtf"],
        )
        
        # Store TF DataFrames for feature lookup
        self._htf_df = frames.get(htf_tf)
        self._mtf_df = frames.get(self._tf_mapping["mtf"])
        self._ltf_df = ltf_frame
        
        # Create and store result
        result = MultiTFPreparedFrames(
            tf_mapping=dict(self._tf_mapping),
            frames=frames,
            close_ts_maps=close_ts_maps,
            ltf_frame=ltf_frame,
            ltf_sim_start_index=sim_start_idx,
            warmup_bars=warmup_bars,
            warmup_multiplier=warmup_multiplier,
            max_indicator_lookback=max_lookback,
            requested_start=requested_start,
            requested_end=requested_end,
            simulation_start=sim_start_ts,
        )
        
        self._mtf_frames = result
        
        # Also set _prepared_frame for backward compatibility
        self._prepared_frame = PreparedFrame(
            df=ltf_frame,
            full_df=ltf_frame,
            warmup_bars=warmup_bars,
            warmup_multiplier=warmup_multiplier,
            max_indicator_lookback=max_lookback,
            requested_start=requested_start,
            requested_end=requested_end,
            loaded_start=ltf_frame["timestamp"].iloc[0],
            loaded_end=ltf_frame["timestamp"].iloc[-1],
            simulation_start=sim_start_ts,
            sim_start_index=sim_start_idx,
        )
        self._data = ltf_frame
        
        return result
    
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
        
        Args:
            tf: Timeframe string
            ts_close: Close timestamp to look up
            bar: Current bar (for fallback if not found)
            
        Returns:
            FeatureSnapshot with indicator values
        """
        # Get the DataFrame for this TF
        df = self._mtf_frames.frames.get(tf) if self._mtf_frames else None
        
        if df is None or "ts_close" not in df.columns:
            return create_not_ready_feature_snapshot(
                tf=tf,
                ts_close=ts_close,
                bar=bar,
                reason=f"No data for {tf}",
            )
        
        # Find the row with this ts_close
        mask = df["ts_close"] == ts_close
        if not mask.any():
            return create_not_ready_feature_snapshot(
                tf=tf,
                ts_close=ts_close,
                bar=bar,
                reason=f"No bar at {ts_close} for {tf}",
            )
        
        row = df[mask].iloc[-1]  # Take last matching row
        
        # Extract ALL numeric features (not hardcoded list)
        features = {}
        ohlcv_cols = {"timestamp", "open", "high", "low", "close", "volume", "ts_close"}
        for col in row.index:
            if col not in ohlcv_cols and pd.notna(row[col]):
                try:
                    features[col] = float(row[col])
                except (ValueError, TypeError):
                    pass
        
        # Check if required indicators are valid (not NaN)
        if hasattr(self.config, 'feature_specs_by_role') and self.config.feature_specs_by_role:
            # Get specs for this TF's role
            tf_role = None
            for role, role_tf in self._tf_mapping.items():
                if role_tf == tf:
                    tf_role = role
                    break
            specs = self.config.feature_specs_by_role.get(tf_role) or \
                    self.config.feature_specs_by_role.get('exec', [])
            required_cols = get_required_indicator_columns_from_specs(specs)
        else:
            required_cols = []
        
        all_valid = all(col in features for col in required_cols)
        
        # Create the Bar for this TF
        tf_delta = tf_duration(tf)
        ts_open = row["timestamp"]
        if hasattr(ts_open, "to_pydatetime"):
            ts_open = ts_open.to_pydatetime()
        tf_ts_close = row["ts_close"]
        if hasattr(tf_ts_close, "to_pydatetime"):
            tf_ts_close = tf_ts_close.to_pydatetime()
        
        tf_bar = CanonicalBar(
            symbol=self.config.symbol,
            tf=tf,
            ts_open=ts_open,
            ts_close=tf_ts_close,
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            volume=row["volume"],
        )
        
        if not all_valid:
            return create_not_ready_feature_snapshot(
                tf=tf,
                ts_close=tf_ts_close,
                bar=tf_bar,
                reason=f"Indicators warming up for {tf}",
            )
        
        return FeatureSnapshot(
            tf=tf,
            ts_close=tf_ts_close,
            bar=tf_bar,
            features=features,
            ready=True,
        )
    
    def run(
        self,
        strategy: Callable[[RuntimeSnapshot, Dict[str, Any]], Optional[Signal]],
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
        self._account_curve: List[AccountCurvePoint] = []
        prev_bar: Optional[CanonicalBar] = None
        
        # Early-stop tracking (proof-grade)
        stop_classification: Optional[StopReason] = None
        stop_reason_detail: Optional[str] = None
        stop_reason: Optional[str] = None  # Legacy compat
        stop_ts: Optional[datetime] = None
        stop_bar_index: Optional[int] = None
        stop_details: Optional[Dict[str, Any]] = None
        
        for i in range(len(df)):
            row = df.iloc[i]
            
            # Compute ts_open and ts_close for canonical Bar
            ts_open = row["timestamp"]  # DB stores ts_open
            tf_delta = tf_duration(self.config.tf)
            ts_close = ts_open + tf_delta
            
            # Create canonical Bar with explicit ts_open/ts_close
            bar = CanonicalBar(
                symbol=self.config.symbol,
                tf=self.config.tf,
                ts_open=ts_open,
                ts_close=ts_close,
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
            )
            
            # Phase 4: Set bar context for artifact tracking
            # Note: snapshot_ready starts as True, will be updated after snapshot build
            self._exchange.set_bar_context(i, snapshot_ready=True)
            
            # Process bar (fills pending orders, checks TP/SL)
            # Note: process_bar receives canonical Bar, uses ts_open for fills
            # Phase 4: process_bar returns StepResult with unified mark_price
            step_result = self._exchange.process_bar(bar, prev_bar)
            closed_trades = self._exchange.last_closed_trades  # Phase 4 backward compat
            
            # Sync risk manager equity with exchange
            self.risk_manager.sync_equity(self._exchange.equity)
            
            # Skip bars before simulation start (warm-up period)
            if i < sim_start_idx:
                # Phase 3: Update caches during warmup (to populate HTF/MTF)
                htf_updated_warmup = False
                mtf_updated_warmup = False
                if self._multi_tf_mode:
                    htf_updated_warmup, mtf_updated_warmup = self._refresh_tf_caches(bar.ts_close, bar)
                
                # Phase 5: Also update history during warmup (for crossover detection)
                # Extract features from row for history
                warmup_features = {}
                ohlcv_cols = {"timestamp", "open", "high", "low", "close", "volume"}
                for col in row.index:
                    if col not in ohlcv_cols and pd.notna(row[col]):
                        try:
                            warmup_features[col] = float(row[col])
                        except (ValueError, TypeError):
                            pass
                
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
            
            # Phase 3: Refresh TF caches at current bar close
            htf_updated = False
            mtf_updated = False
            if self._multi_tf_mode:
                htf_updated, mtf_updated = self._refresh_tf_caches(bar.ts_close, bar)
            
            # Phase 1: Update history windows (before snapshot build)
            # Extract ALL numeric features from row (not hardcoded columns)
            # This supports both legacy (ema_fast, etc.) and IdeaCard (ema_20, atr_14, etc.)
            features_for_history = {}
            ohlcv_cols = {"timestamp", "open", "high", "low", "close", "volume"}
            for col in row.index:
                if col not in ohlcv_cols and pd.notna(row[col]):
                    try:
                        features_for_history[col] = float(row[col])
                    except (ValueError, TypeError):
                        pass  # Skip non-numeric columns
            
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
            
            # ========== STOP CHECKS WITH PRECEDENCE (after warmup only) ==========
            # Stop precedence (highest to lowest priority):
            # 1. LIQUIDATED - equity <= maintenance margin (terminal)
            # 2. EQUITY_FLOOR_HIT - equity <= stop_equity_usdt (terminal)
            # 3. STRATEGY_STARVED - can't meet entry gate (non-terminal, continues)
            
            # Phase 1: only close-as-mark supported (explicit/configurable)
            if risk_profile.mark_price_source != "close":
                raise ValueError(
                    f"Unsupported mark_price_source='{risk_profile.mark_price_source}'. "
                    "Phase 1 supports 'close' only."
                )
            
            terminal_stop = False
            
            # 1. LIQUIDATED - equity <= maintenance margin (with position)
            if self._exchange.is_liquidatable:
                stop_classification = StopReason.LIQUIDATED
                stop_reason_detail = (
                    f"Liquidation: equity ${self._exchange.equity_usdt:.2f} "
                    f"<= maintenance margin ${self._exchange.maintenance_margin:.2f}"
                )
                stop_reason = "liquidated"  # Legacy
                terminal_stop = True
            
            # 2. EQUITY_FLOOR_HIT - equity <= stop_equity_usdt (configurable threshold)
            elif self._exchange.equity_usdt <= risk_profile.stop_equity_usdt:
                stop_classification = StopReason.EQUITY_FLOOR_HIT
                stop_reason_detail = (
                    f"Equity floor hit: equity ${self._exchange.equity_usdt:.2f} "
                    f"<= threshold ${risk_profile.stop_equity_usdt:.2f}"
                )
                stop_reason = "account_blown"  # Legacy compat
                terminal_stop = True
            
            # 3. STRATEGY_STARVED - can't meet entry gate for min_trade_usdt (non-terminal)
            elif not self._exchange.entries_disabled:
                # Check preemptive starvation: can we open a min_trade_usdt position?
                required_for_min = self._exchange.compute_required_for_entry(risk_profile.min_trade_usdt)
                if self._exchange.available_balance_usdt < required_for_min:
                    # Set starvation on exchange (use ts_close as evaluation time)
                    self._exchange.set_starvation(bar.ts_close, i, "INSUFFICIENT_ENTRY_GATE")
                    # Cancel any pending entry order
                    self._exchange.cancel_pending_order()
                    self.logger.info(
                        f"Strategy starved at bar {i}: available=${self._exchange.available_balance_usdt:.2f} "
                        f"< required=${required_for_min:.2f} for min_trade_usdt=${risk_profile.min_trade_usdt}"
                    )
            
            # Handle terminal stops (halt immediately)
            if terminal_stop:
                # Cancel any pending entry order
                self._exchange.cancel_pending_order()
                
                # Force close any open position at current bar close
                # Use ts_close as stop time (bar close)
                if self._exchange.position is not None:
                    self._exchange.force_close_position(
                        bar.close,
                        bar.ts_close,  # Use ts_close for exit time
                        reason=stop_reason,
                    )
                
                # Capture stop metadata (full exchange snapshot)
                # Use ts_close as stop timestamp (strategy evaluation time)
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
            
            # Build RuntimeSnapshot for strategy (Phase 2/3/4)
            # Phase 4: Use mark_price from StepResult (computed once by exchange)
            snapshot = self._build_snapshot(row, bar, i, step_result)
            
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
            assert snapshot.features_exec.ts_close == bar.ts_close, (
                f"Lookahead violation: features_exec.ts_close ({snapshot.features_exec.ts_close}) != "
                f"bar.ts_close ({bar.ts_close})"
            )
            # ========== END LOOKAHEAD GUARD ==========
            
            # Get strategy signal (skip if entries disabled and no position)
            signal = None
            if not self._exchange.entries_disabled or self._exchange.position is not None:
                signal = strategy(snapshot, self.config.params)
            
            # Process signal (use bar for order submission)
            if signal is not None:
                self._process_signal(signal, bar, snapshot)
            
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
            
            prev_bar = bar
        
        # Close any remaining position at end (if not already stopped early)
        if stop_classification is None and self._exchange.position is not None:
            last_row = df.iloc[-1]
            self._exchange.force_close_position(
                last_row["close"],
                last_row["timestamp"],
            )
        
        # Capture end-of-data snapshot if not already captured from terminal stop
        if stop_details is None:
            stop_details = self._exchange.get_state()
        
        # Calculate drawdowns in equity curve
        self._calculate_drawdowns()
        
        # Count bars in position for time-in-market metric
        bars_in_position = sum(1 for a in self._account_curve if a.has_position)
        
        # Compute structured metrics (legacy)
        metrics = compute_backtest_metrics(
            equity_curve=self._equity_curve,
            trades=self._exchange.trades,
            tf=self.config.tf,
            initial_equity=initial_equity,
            bars_in_position=bars_in_position,
        )
        
        # Compute proof-grade metrics (v2)
        metrics_v2 = compute_proof_metrics(
            account_curve=self._account_curve,
            equity_curve=self._equity_curve,
            trades=self._exchange.trades,
            tf=self.config.tf,
            initial_equity=initial_equity,
            entry_attempts=self._exchange.entry_attempts_count,
            entry_rejections=self._exchange.entry_rejections_count,
            first_starved_ts=self._exchange.first_starved_ts,
            first_starved_bar_index=self._exchange.first_starved_bar_index,
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
            metrics_v2=metrics_v2,
            risk_initial_equity_used=risk_profile.initial_equity,
            risk_per_trade_pct_used=risk_profile.risk_per_trade_pct,
            risk_max_leverage_used=risk_profile.max_leverage,
            # Warm-up and window metadata
            warmup_bars=prepared.warmup_bars,
            warmup_multiplier=prepared.warmup_multiplier,
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
        
        Args:
            ts_close: Current LTF close timestamp
            bar: Current LTF bar (for fallback)
            
        Returns:
            Tuple of (htf_updated, mtf_updated) booleans
        """
        htf_tf = self._tf_mapping["htf"]
        mtf_tf = self._tf_mapping["mtf"]
        
        # Factory function for HTF snapshot
        def htf_factory() -> FeatureSnapshot:
            return self._get_tf_features_at_close(htf_tf, ts_close, bar)
        
        # Factory function for MTF snapshot
        def mtf_factory() -> FeatureSnapshot:
            return self._get_tf_features_at_close(mtf_tf, ts_close, bar)
        
        return self._tf_cache.refresh_step(ts_close, htf_factory, mtf_factory)
    
    def _build_snapshot(
        self,
        row: pd.Series,
        bar: CanonicalBar,
        bar_index: int,
        step_result: Optional["StepResult"] = None,
    ) -> RuntimeSnapshot:
        """
        Build a RuntimeSnapshot from current bar data.
        
        Phase 1: Includes history for crossover detection and structure SL.
        Phase 2: Uses SnapshotBuilder with single-TF mode (all TFs = LTF).
        Phase 3: Uses TimeframeCache for HTF/MTF carry-forward in multi-TF mode.
        Phase 4: Uses mark_price from StepResult (computed once by exchange).
        
        Args:
            row: DataFrame row with indicator values
            bar: Current canonical bar
            bar_index: Index of current bar
            step_result: Optional StepResult from exchange (Phase 4)
        """
        exchange = self._exchange
        
        # Extract ALL numeric features (not hardcoded list)
        features = {}
        ohlcv_cols = {"timestamp", "open", "high", "low", "close", "volume", "ts_close"}
        for col in row.index:
            if col not in ohlcv_cols and pd.notna(row[col]):
                try:
                    features[col] = float(row[col])
                except (ValueError, TypeError):
                    pass
        
        # Build ExchangeState from exchange
        exchange_state = build_exchange_state_from_exchange(exchange)
        
        # Build exec-TF FeatureSnapshot
        features_exec = FeatureSnapshot(
            tf=self.config.tf,
            ts_close=bar.ts_close,
            bar=bar,
            features=features,
            ready=True,
        )
        
        # Phase 4: Use mark_price from StepResult (computed once by exchange)
        # This ensures SnapshotBuilder never calls PriceModel
        if step_result is not None and step_result.mark_price is not None:
            mark_price = step_result.mark_price
            mark_price_source = step_result.mark_price_source
        else:
            # Fallback for backward compatibility (shouldn't happen in normal flow)
            mark_price = bar.close
            mark_price_source = self.config.risk_profile.mark_price_source
        
        # Phase 1: Get history tuples (immutable)
        history_bars_exec, history_features_exec, history_features_htf, history_features_mtf = self._get_history_tuples()
        history_ready = self._is_history_ready()
        
        # Phase 3: Multi-TF mode - use cached HTF/MTF features
        if self._multi_tf_mode:
            features_htf = self._tf_cache.get_htf()
            features_mtf = self._tf_cache.get_mtf()
            
            # Use SnapshotBuilder with cached features (may be None if not yet ready)
            return self._snapshot_builder.build_with_defaults(
                ts_close=bar.ts_close,
                bar_ltf=bar,
                mark_price=mark_price,
                mark_price_source=mark_price_source,
                exchange_state=exchange_state,
                features_ltf=features_exec,
                features_htf=features_htf,
                features_mtf=features_mtf,
                history_bars_exec=history_bars_exec,
                history_features_exec=history_features_exec,
                history_features_htf=history_features_htf,
                history_features_mtf=history_features_mtf,
                history_ready=history_ready,
            )
        
        # Single-TF mode: use exec features for all TFs
        return self._snapshot_builder.build_with_defaults(
            ts_close=bar.ts_close,
            bar_ltf=bar,
            mark_price=mark_price,
            mark_price_source=mark_price_source,
            exchange_state=exchange_state,
            features_ltf=features_exec,
            features_htf=features_exec,
            features_mtf=features_exec,
            history_bars_exec=history_bars_exec,
            history_features_exec=history_features_exec,
            history_features_htf=history_features_htf,
            history_features_mtf=history_features_mtf,
            history_ready=history_ready,
        )
    
    
    def _process_signal(
        self,
        signal: Signal,
        bar: CanonicalBar,
        snapshot: RuntimeSnapshot,
    ) -> None:
        """Process a strategy signal through risk sizing and submit order."""
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
        decision = self.risk_policy.check(
            signal=signal,
            equity=exchange.equity,
            available_balance=exchange.available_balance,
            total_exposure=exchange.position.size_usdt if exchange.position else 0,
        )
        
        if not decision.allowed:
            self.logger.debug(f"Signal blocked by risk policy: {decision.reason}")
            return
        
        # Use SimulatedRiskManager for sizing
        sizing_result = self.risk_manager.size_order(snapshot, signal)
        size_usdt = sizing_result.size_usdt
        
        # Minimum size check (use configured min_trade_usdt)
        min_trade = self.config.risk_profile.min_trade_usdt
        if size_usdt < min_trade:
            self.logger.debug(f"Size too small ({size_usdt:.2f} < {min_trade}), skipping signal")
            return
        
        # Calculate TP/SL from signal metadata if present
        stop_loss = signal.metadata.get("stop_loss") if signal.metadata else None
        take_profit = signal.metadata.get("take_profit") if signal.metadata else None
        
        # Submit order (use ts_close as signal timestamp - decision made at bar close)
        exchange.submit_order(
            side=side,
            size_usdt=size_usdt,
            stop_loss=stop_loss,
            take_profit=take_profit,
            timestamp=bar.ts_close,
        )
    
    def _calculate_drawdowns(self) -> None:
        """Calculate drawdown values for equity curve."""
        if not self._equity_curve:
            return
        
        peak = self._equity_curve[0].equity
        
        for point in self._equity_curve:
            if point.equity > peak:
                peak = point.equity
            
            point.drawdown = peak - point.equity
            point.drawdown_pct = (point.drawdown / peak * 100) if peak > 0 else 0.0
    
    def _write_artifacts(self, result: BacktestResult) -> None:
        """Write run artifacts to run_dir."""
        if not self.run_dir:
            return
        
        self.run_dir.mkdir(parents=True, exist_ok=True)
        
        # Write trades.csv (Phase 4: includes bar indices, exit trigger, readiness)
        trades_path = self.run_dir / "trades.csv"
        if result.trades:
            trades_df = pd.DataFrame([
                {
                    "trade_id": t.trade_id,
                    "symbol": t.symbol,
                    "side": t.side.upper(),
                    "entry_time": t.entry_time.isoformat(),
                    "exit_time": t.exit_time.isoformat() if t.exit_time else "",
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price or 0,
                    "qty": t.entry_size,
                    "pnl": t.net_pnl,
                    "pnl_pct": t.pnl_pct,
                    # Phase 4: Bar indices
                    "entry_bar_index": t.entry_bar_index,
                    "exit_bar_index": t.exit_bar_index,
                    "duration_bars": t.duration_bars,
                    # Phase 4: Exit trigger classification
                    "exit_reason": t.exit_reason or "",
                    "exit_price_source": t.exit_price_source or "",
                    # Phase 4: Snapshot readiness at entry/exit
                    "entry_ready": t.entry_ready,
                    "exit_ready": t.exit_ready if t.exit_ready is not None else "",
                    # Risk levels
                    "stop_loss": t.stop_loss or "",
                    "take_profit": t.take_profit or "",
                }
                for t in result.trades
            ])
            trades_df.to_csv(trades_path, index=False)
        else:
            # Write empty file with headers
            pd.DataFrame(columns=[
                "trade_id", "symbol", "side", "entry_time", "exit_time",
                "entry_price", "exit_price", "qty", "pnl", "pnl_pct",
                # Phase 4 fields
                "entry_bar_index", "exit_bar_index", "duration_bars",
                "exit_reason", "exit_price_source",
                "entry_ready", "exit_ready",
                "stop_loss", "take_profit"
            ]).to_csv(trades_path, index=False)
        
        # Write equity.csv
        equity_path = self.run_dir / "equity.csv"
        equity_df = pd.DataFrame([
            {
                "ts": e.timestamp.isoformat(),
                "equity": e.equity,
                "drawdown_abs": e.drawdown,
                "drawdown_pct": e.drawdown_pct,
            }
            for e in result.equity_curve
        ])
        equity_df.to_csv(equity_path, index=False)
        
        # Write account_curve.csv (proof-grade margin state per bar)
        account_curve_path = self.run_dir / "account_curve.csv"
        if result.account_curve:
            account_df = pd.DataFrame([
                {
                    "ts": a.timestamp.isoformat(),
                    "equity_usdt": a.equity_usdt,
                    "used_margin_usdt": a.used_margin_usdt,
                    "free_margin_usdt": a.free_margin_usdt,
                    "available_balance_usdt": a.available_balance_usdt,
                    "maintenance_margin_usdt": a.maintenance_margin_usdt,
                    "has_position": a.has_position,
                    "entries_disabled": a.entries_disabled,
                }
                for a in result.account_curve
            ])
            account_df.to_csv(account_curve_path, index=False)
        else:
            pd.DataFrame(columns=[
                "ts", "equity_usdt", "used_margin_usdt", "free_margin_usdt",
                "available_balance_usdt", "maintenance_margin_usdt",
                "has_position", "entries_disabled"
            ]).to_csv(account_curve_path, index=False)
        
        # Compute artifact hashes for reproducibility
        import hashlib
        artifact_hashes = {}
        for path_name, path in [
            ("trades.csv", trades_path),
            ("equity.csv", equity_path),
            ("account_curve.csv", account_curve_path),
        ]:
            if path.exists():
                with open(path, "rb") as f:
                    artifact_hashes[path_name] = hashlib.sha256(f.read()).hexdigest()
        
        # Build result dict with artifact hashes
        result_dict = result.to_dict()
        result_dict["artifact_hashes"] = artifact_hashes
        result_dict["account_curve_path"] = "account_curve.csv"
        
        # Write result.json
        result_path = self.run_dir / "result.json"
        with open(result_path, "w") as f:
            json.dump(result_dict, f, indent=2)
        
        self.logger.info(f"Artifacts written to {self.run_dir}")


def run_backtest(
    system_id: str,
    window_name: str,
    strategy: Callable[[RuntimeSnapshot, Dict[str, Any]], Optional[Signal]],
    run_dir: Optional[Path] = None,
) -> BacktestResult:
    """
    Convenience function to run a backtest.
    
    Args:
        system_id: System configuration ID
        window_name: Window to use ("hygiene" or "test")
        strategy: Strategy function
        run_dir: Optional directory for artifacts
        
    Returns:
        BacktestResult
    """
    config = load_system_config(system_id, window_name)
    engine = BacktestEngine(config, window_name, run_dir)
    return engine.run(strategy)
