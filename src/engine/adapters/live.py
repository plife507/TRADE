"""
Live adapters for PlayEngine.

These adapters connect to real exchange infrastructure:
- LiveDataProvider: WebSocket data + indicator cache
- LiveExchange: OrderExecutor + PositionManager

Integrates with existing RealtimeState/RealtimeBootstrap infrastructure.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import numpy as np

from src.backtest.runtime.timeframe import tf_minutes

from ..interfaces import (
    Candle,
    DataProvider,
    ExchangeAdapter,
    Order,
    OrderResult,
    Position,
)
from ..play_engine import PlayEngineConfig

from ...utils.logger import get_logger

if TYPE_CHECKING:
    from ...backtest.play import Play
    from ...data.realtime_state import RealtimeState
    from ...data.realtime_bootstrap import RealtimeBootstrap
    from src.structures import TFIncrementalState


logger = get_logger()


class LiveIndicatorCache:
    """
    Incremental indicator cache for live trading.

    Maintains rolling arrays of indicator values. Uses O(1) incremental
    computation for supported indicators (EMA, SMA, RSI, ATR, MACD, BBands)
    and falls back to vectorized computation for others.
    """

    def __init__(self, play: "Play", buffer_size: int = 500):
        """
        Initialize indicator cache.

        Args:
            play: Play instance with feature specs
            buffer_size: Maximum bars to keep in buffer
        """
        self._play = play
        self._buffer_size = buffer_size

        # G6.2.1: Thread safety for WebSocket callbacks
        self._lock = threading.Lock()

        # Indicator arrays (name -> numpy array)
        self._indicators: dict[str, np.ndarray] = {}

        # Incremental indicator instances (name -> IncrementalIndicator)
        self._incremental: dict[str, Any] = {}

        # Specs that don't support incremental computation
        self._vectorized_specs: list[dict] = []

        # OHLCV arrays for vectorized computation fallback
        self._open: np.ndarray = np.array([], dtype=np.float64)
        self._high: np.ndarray = np.array([], dtype=np.float64)
        self._low: np.ndarray = np.array([], dtype=np.float64)
        self._close: np.ndarray = np.array([], dtype=np.float64)
        self._volume: np.ndarray = np.array([], dtype=np.float64)

        # Track bar count
        self._bar_count: int = 0

    def initialize_from_history(
        self,
        candles: list,
        indicator_specs: list[dict],
    ) -> None:
        """
        Initialize cache from historical candles.

        Args:
            candles: List of historical candles (BarRecord or Candle)
            indicator_specs: Feature specs from Play
        """
        from ...indicators import FeatureSpec, create_incremental_indicator, supports_incremental
        from ...backtest.indicator_registry import get_registry

        if not candles:
            return

        # Convert candles to arrays
        n = len(candles)
        self._open = np.zeros(n, dtype=np.float64)
        self._high = np.zeros(n, dtype=np.float64)
        self._low = np.zeros(n, dtype=np.float64)
        self._close = np.zeros(n, dtype=np.float64)
        self._volume = np.zeros(n, dtype=np.float64)

        for i, candle in enumerate(candles):
            self._open[i] = float(candle.open)
            self._high[i] = float(candle.high)
            self._low[i] = float(candle.low)
            self._close[i] = float(candle.close)
            self._volume[i] = float(candle.volume)

        self._bar_count = n

        # Get registry for input requirements
        registry = get_registry()

        # Classify indicators: incremental vs vectorized
        self._vectorized_specs = []
        self._incremental = {}

        for spec in indicator_specs:
            try:
                feature = FeatureSpec.from_dict(spec)
                ind_type = feature.indicator_type.lower()

                if supports_incremental(ind_type):
                    # Create incremental indicator
                    inc_ind = create_incremental_indicator(ind_type, feature.params)
                    if inc_ind is not None:
                        self._incremental[feature.indicator_id] = (inc_ind, feature)

                        # Use registry to determine input requirements and outputs
                        info = registry.get_indicator_info(ind_type)
                        needs_hlc = info.requires_hlc

                        # Initialize arrays for all outputs
                        if info.is_multi_output:
                            for suffix in info.output_keys:
                                key = f"{feature.indicator_id}_{suffix}"
                                self._indicators[key] = np.full(n, np.nan)
                        else:
                            self._indicators[feature.indicator_id] = np.full(n, np.nan)

                        # Warmup with historical data
                        for i in range(n):
                            if needs_hlc:
                                inc_ind.update(
                                    high=self._high[i],
                                    low=self._low[i],
                                    close=self._close[i],
                                )
                            else:
                                inc_ind.update(close=self._close[i])

                            # Store all outputs for multi-output indicators
                            if info.is_multi_output:
                                for suffix in info.output_keys:
                                    key = f"{feature.indicator_id}_{suffix}"
                                    value = self._get_incremental_output(inc_ind, suffix)
                                    self._indicators[key][i] = value
                            else:
                                self._indicators[feature.indicator_id][i] = inc_ind.value
                    else:
                        self._vectorized_specs.append(spec)
                else:
                    self._vectorized_specs.append(spec)
            except Exception as e:
                logger.warning(f"Failed to initialize indicator {spec}: {e}")

        # Compute vectorized indicators
        self._compute_vectorized()

    def update(self, candle: Candle) -> None:
        """
        Add new closed candle and update indicators.

        Uses O(1) incremental computation for supported indicators.
        Thread-safe: protected by lock for WebSocket callbacks.
        """
        # G6.2.1: Thread safety - lock all mutations
        with self._lock:
            # Append to arrays
            self._open = np.append(self._open, candle.open)
            self._high = np.append(self._high, candle.high)
            self._low = np.append(self._low, candle.low)
            self._close = np.append(self._close, candle.close)
            self._volume = np.append(self._volume, candle.volume)

            # Trim if needed
            if len(self._close) > self._buffer_size:
                trim_count = len(self._close) - self._buffer_size
                self._open = self._open[trim_count:]
                self._high = self._high[trim_count:]
                self._low = self._low[trim_count:]
                self._close = self._close[trim_count:]
                self._volume = self._volume[trim_count:]

                # Trim indicator arrays too
                for name in self._indicators:
                    self._indicators[name] = self._indicators[name][trim_count:]

            self._bar_count = len(self._close)

            # Update incremental indicators (O(1) per indicator)
            from ...backtest.indicator_registry import get_registry
            registry = get_registry()

            for name, (inc_ind, feature) in self._incremental.items():
                ind_type = feature.indicator_type.lower()

                # Use registry to determine input requirements
                info = registry.get_indicator_info(ind_type)
                if info.requires_hlc:
                    inc_ind.update(
                        high=float(candle.high),
                        low=float(candle.low),
                        close=float(candle.close),
                    )
                else:
                    inc_ind.update(close=float(candle.close))

                # Append new values for all outputs
                if info.is_multi_output:
                    for suffix in info.output_keys:
                        key = f"{name}_{suffix}"
                        value = self._get_incremental_output(inc_ind, suffix)
                        self._indicators[key] = np.append(self._indicators[key], value)
                else:
                    self._indicators[name] = np.append(self._indicators[name], inc_ind.value)

            # Recompute vectorized indicators (still O(n) but only for non-incremental)
            if self._vectorized_specs:
                self._compute_vectorized()

    def _get_incremental_output(self, inc_ind: Any, suffix: str) -> float:
        """
        Get output value from incremental indicator by suffix.

        Multi-output incremental indicators have properties like:
        - k_value, d_value (Stochastic)
        - adx_value, dmp_value, dmn_value (ADX)
        - trend_value, direction_value, long_value, short_value (SuperTrend)
        - macd (via .value), signal_value, histogram_value (MACD)
        - lower, middle, upper (BBands - direct properties)

        Args:
            inc_ind: Incremental indicator instance
            suffix: Output suffix from registry (e.g., "k", "d", "adx")

        Returns:
            Output value (may be NaN)
        """
        # Try {suffix}_value property first (most common pattern)
        prop_name = f"{suffix}_value"
        if hasattr(inc_ind, prop_name):
            return float(getattr(inc_ind, prop_name))

        # Try direct property (BBands: lower, middle, upper)
        if hasattr(inc_ind, suffix):
            return float(getattr(inc_ind, suffix))

        # Fallback to primary value
        return float(inc_ind.value)

    def _compute_vectorized(self) -> None:
        """Compute vectorized indicators (fallback for non-incremental)."""
        from ...indicators import FeatureSpec

        for spec in self._vectorized_specs:
            try:
                feature = FeatureSpec.from_dict(spec)
                values = feature.compute(
                    open=self._open,
                    high=self._high,
                    low=self._low,
                    close=self._close,
                    volume=self._volume,
                )
                self._indicators[feature.indicator_id] = values
            except Exception as e:
                logger.warning(f"Failed to compute indicator {spec}: {e}")

    def get(self, name: str, index: int) -> float:
        """Get indicator value at index. Thread-safe."""
        with self._lock:
            if name not in self._indicators:
                raise KeyError(f"Indicator '{name}' not found")

            arr = self._indicators[name]
            if index < 0:
                index = len(arr) + index

            if index < 0 or index >= len(arr):
                raise IndexError(f"Index {index} out of bounds")

            return float(arr[index])

    def has_indicator(self, name: str) -> bool:
        """Check if indicator exists. Thread-safe."""
        with self._lock:
            return name in self._indicators

    @property
    def length(self) -> int:
        """Number of bars in cache. Thread-safe."""
        with self._lock:
            return self._bar_count


class LiveDataProvider:
    """
    DataProvider that uses WebSocket streams and indicator cache.

    Provides real-time access to:
    - Live candles from WebSocket via RealtimeState
    - Incrementally computed indicators via LiveIndicatorCache
    - Structure state (swing, trend, zones) via TFIncrementalState

    Supports 3-feed + exec role system for multi-timeframe strategies:
    - low_tf: Fast timeframe (execution, entries)
    - med_tf: Medium timeframe (structure, bias)
    - high_tf: Slow timeframe (trend, context)
    - exec: Pointer to which TF to step on

    Integrates with existing RealtimeBootstrap/RealtimeState infrastructure.
    """

    def __init__(self, play: "Play", demo: bool = True):
        """
        Initialize live data provider.

        Args:
            play: Play instance with feature specs
            demo: If True, use demo WebSocket endpoint
        """
        self._play = play
        self._demo = demo
        self._symbol = play.symbol_universe[0]

        # 3-Feed + Exec Role System
        # Extract TF mapping from Play timeframes
        tf_config = play.timeframes if hasattr(play, 'timeframes') and play.timeframes else {}
        self._tf_mapping = {
            "low_tf": tf_config.get("low_tf", play.execution_tf),
            "med_tf": tf_config.get("med_tf", play.execution_tf),
            "high_tf": tf_config.get("high_tf", play.execution_tf),
            "exec": tf_config.get("exec", "low_tf"),  # Pointer to which feed
        }
        self._exec_role = self._tf_mapping["exec"]

        # Resolved exec TF (the actual timeframe string)
        self._timeframe = self._tf_mapping[self._exec_role]

        # RealtimeState integration (set during connect)
        self._realtime_state: "RealtimeState | None" = None
        self._bootstrap: "RealtimeBootstrap | None" = None

        # G6.2.2: Thread safety for buffer access from WebSocket callbacks
        self._buffer_lock = threading.Lock()

        # 3-Feed Candle Buffers
        self._low_tf_buffer: list[Candle] = []
        self._med_tf_buffer: list[Candle] = []
        self._high_tf_buffer: list[Candle] = []
        self._buffer_size = 500

        # 3-Feed Indicator Caches
        self._low_tf_indicators = LiveIndicatorCache(play, buffer_size=self._buffer_size)
        self._med_tf_indicators: LiveIndicatorCache | None = None
        self._high_tf_indicators: LiveIndicatorCache | None = None

        # Initialize med_tf/high_tf caches only if different from low_tf
        if self._tf_mapping["med_tf"] != self._tf_mapping["low_tf"]:
            self._med_tf_indicators = LiveIndicatorCache(play, buffer_size=self._buffer_size)
        if self._tf_mapping["high_tf"] != self._tf_mapping["med_tf"]:
            self._high_tf_indicators = LiveIndicatorCache(play, buffer_size=self._buffer_size)

        # 3-Feed Structure States (incremental detection)
        self._low_tf_structure: "TFIncrementalState | None" = None
        self._med_tf_structure: "TFIncrementalState | None" = None
        self._high_tf_structure: "TFIncrementalState | None" = None

        # Legacy single-buffer aliases (for compatibility)
        self._candle_buffer = self._low_tf_buffer
        self._indicator_cache = self._low_tf_indicators
        self._structure_state: "TFIncrementalState | None" = None

        # Tracking
        self._ready = False
        # Minimum bars before provider is ready for trading
        # 100 bars ensures most indicators (EMA, RSI, etc.) have sufficient history
        self._warmup_bars = 100
        self._current_bar_index: int = -1

        # Environment for multi-TF buffer lookup
        self._env = "demo" if demo else "live"

        # Multi-TF mode flag
        self._multi_tf_mode = (
            self._tf_mapping["high_tf"] != self._tf_mapping["low_tf"] or
            self._tf_mapping["med_tf"] != self._tf_mapping["low_tf"]
        )

        logger.info(
            f"LiveDataProvider initialized: {self._symbol} exec={self._timeframe} "
            f"env={self._env} multi_tf={self._multi_tf_mode}"
        )
        if self._multi_tf_mode:
            logger.info(
                f"  TF mapping: low_tf={self._tf_mapping['low_tf']} "
                f"med_tf={self._tf_mapping['med_tf']} high_tf={self._tf_mapping['high_tf']} "
                f"exec={self._exec_role}"
            )

    @property
    def num_bars(self) -> int:
        """Number of bars in exec buffer. Thread-safe."""
        with self._buffer_lock:
            return len(self._exec_buffer)

    @property
    def _exec_buffer(self) -> list[Candle]:
        """Resolved exec buffer based on exec role pointer."""
        if self._exec_role == "high_tf":
            return self._high_tf_buffer
        elif self._exec_role == "med_tf":
            return self._med_tf_buffer
        return self._low_tf_buffer

    @property
    def _exec_indicators(self) -> LiveIndicatorCache:
        """Resolved exec indicator cache based on exec role pointer."""
        if self._exec_role == "high_tf" and self._high_tf_indicators:
            return self._high_tf_indicators
        elif self._exec_role == "med_tf" and self._med_tf_indicators:
            return self._med_tf_indicators
        return self._low_tf_indicators

    @property
    def symbol(self) -> str:
        return self._symbol

    @property
    def timeframe(self) -> str:
        return self._timeframe

    @property
    def tf_mapping(self) -> dict[str, str]:
        """TF mapping for PlayEngine compatibility."""
        return self._tf_mapping

    @property
    def multi_tf_mode(self) -> bool:
        """Whether multi-TF mode is active."""
        return self._multi_tf_mode

    @property
    def current_bar_index(self) -> int:
        """Current bar index for structure access."""
        return self._current_bar_index

    @current_bar_index.setter
    def current_bar_index(self, value: int) -> None:
        """Set current bar index (called by runner each bar)."""
        self._current_bar_index = value

    @property
    def low_tf_buffer(self) -> list[Candle]:
        """Low timeframe candle buffer."""
        return self._low_tf_buffer

    @property
    def med_tf_buffer(self) -> list[Candle]:
        """Medium timeframe candle buffer."""
        return self._med_tf_buffer

    @property
    def high_tf_buffer(self) -> list[Candle]:
        """High timeframe candle buffer."""
        return self._high_tf_buffer

    async def connect(self) -> None:
        """
        Connect to WebSocket and start receiving data.

        Uses the global RealtimeBootstrap if available.
        """
        from ...data.realtime_state import get_realtime_state
        from ...data.realtime_bootstrap import get_realtime_bootstrap

        try:
            # Get global realtime state
            self._realtime_state = get_realtime_state()
            self._bootstrap = get_realtime_bootstrap()

            # Ensure symbol is subscribed
            if not self._bootstrap.is_running:
                self._bootstrap.start(
                    symbols=[self._symbol],
                    include_private=False,  # Data provider doesn't need private streams
                )

            # Ensure our symbol is tracked
            self._bootstrap.ensure_symbol_subscribed(self._symbol)

            # Load historical bars from bar buffer
            await self._load_initial_bars()

            logger.info(f"LiveDataProvider connected: {self._symbol}")

        except Exception as e:
            logger.error(f"Failed to connect LiveDataProvider: {e}")
            raise

    async def disconnect(self) -> None:
        """Disconnect from WebSocket."""
        # We don't stop the bootstrap as other components may be using it
        self._ready = False
        logger.info(f"LiveDataProvider disconnected: {self._symbol}")

    async def _load_initial_bars(self) -> None:
        """Load initial bars from bar buffer, DuckDB, or REST API for all TFs."""
        if self._realtime_state is None:
            return

        # Load bars for each unique timeframe
        unique_tfs = {
            "low_tf": self._tf_mapping["low_tf"],
            "med_tf": self._tf_mapping["med_tf"],
            "high_tf": self._tf_mapping["high_tf"],
        }

        # Load low_tf (always required)
        await self._load_tf_bars("low_tf", unique_tfs["low_tf"])

        # Load med_tf if different from low_tf
        if unique_tfs["med_tf"] != unique_tfs["low_tf"]:
            await self._load_tf_bars("med_tf", unique_tfs["med_tf"])

        # Load high_tf if different from med_tf
        if unique_tfs["high_tf"] != unique_tfs["med_tf"]:
            await self._load_tf_bars("high_tf", unique_tfs["high_tf"])

        # Initialize structure states for each TF if Play has structures
        if self._play.structures:
            self._init_structure_states()

        # Check warmup (exec buffer must have enough bars)
        if len(self._exec_buffer) >= self._warmup_bars:
            self._ready = True
            logger.info("LiveDataProvider ready (warmup complete)")

    async def _load_tf_bars(self, tf_role: str, tf_str: str) -> None:
        """Load bars for a specific timeframe role."""
        if self._realtime_state is None:
            return

        # Get the right buffer and indicator cache for this TF
        if tf_role == "low_tf":
            buffer = self._low_tf_buffer
            indicator_cache = self._low_tf_indicators
        elif tf_role == "med_tf":
            buffer = self._med_tf_buffer
            indicator_cache = self._med_tf_indicators
        elif tf_role == "high_tf":
            buffer = self._high_tf_buffer
            indicator_cache = self._high_tf_indicators
        else:
            return

        # Try to get from bar buffer first (hot in-memory cache)
        bars = self._realtime_state.get_bar_buffer(
            env=self._env,
            symbol=self._symbol,
            timeframe=tf_str,
            limit=self._buffer_size,
        )

        # Fall back to DuckDB if bar buffer is empty
        if not bars:
            bars = await self._load_bars_from_db_for_tf(tf_str)

        if bars:
            # Convert BarRecords to interface Candles
            for bar_record in bars:
                candle = Candle(
                    ts_open=bar_record.timestamp,
                    ts_close=bar_record.timestamp,  # Approximate
                    open=bar_record.open,
                    high=bar_record.high,
                    low=bar_record.low,
                    close=bar_record.close,
                    volume=bar_record.volume,
                )
                buffer.append(candle)

            # Initialize indicators from historical data
            if indicator_cache is not None:
                # Get indicator specs for this TF from Play
                tf_specs = self._get_indicator_specs_for_tf(tf_role)
                indicator_cache.initialize_from_history(bars, tf_specs)

            logger.info(f"Loaded {len(bars)} bars for {tf_role} ({tf_str}) warm-up")

    def _get_indicator_specs_for_tf(self, tf_role: str) -> list[dict]:
        """Get indicator specs for a specific TF role from Play."""
        if not self._play.features:
            return []

        tf_str = self._tf_mapping[tf_role]
        specs = []
        for feature in self._play.features:
            # Check if this feature's TF matches
            feature_tf = feature.get("timeframe", self._timeframe)
            if feature_tf == tf_str:
                specs.append(feature)
        return specs

    async def _load_bars_from_db(self) -> list:
        """Load bars from DuckDB for warm-up (exec TF)."""
        return await self._load_bars_from_db_for_tf(self._timeframe)

    async def _load_bars_from_db_for_tf(self, tf_str: str) -> list:
        """
        Load bars from DuckDB for warm-up for a specific timeframe.

        Fallback when in-memory buffer is empty (e.g., bot restart).
        """
        from ...data.historical_data_store import get_historical_store
        from ...data.realtime_state import BarRecord
        from datetime import datetime, timedelta

        try:
            store = get_historical_store(env=self._env)

            # Calculate time range (last N bars based on timeframe)
            # G6.5.1: Use non-deprecated timezone-aware datetime
            end = datetime.now(timezone.utc)
            tf_mins = tf_minutes(tf_str)
            start = end - timedelta(minutes=tf_mins * self._buffer_size)

            # Query DuckDB
            df = store.query_ohlcv(
                symbol=self._symbol,
                timeframe=tf_str,
                start=start,
                end=end,
            )

            if df is None or df.empty:
                logger.info(f"No bars in DuckDB for {self._symbol} {tf_str}")
                return []

            # Convert DataFrame rows to BarRecord objects
            bars = []
            for _, row in df.iterrows():
                bar = BarRecord(
                    timestamp=row['timestamp'],
                    open=float(row['open']),
                    high=float(row['high']),
                    low=float(row['low']),
                    close=float(row['close']),
                    volume=float(row['volume']),
                )
                bars.append(bar)

            logger.info(f"Loaded {len(bars)} bars from DuckDB ({self._env}) for {tf_str}")
            return bars

        except Exception as e:
            logger.warning(f"Failed to load bars from DuckDB for {tf_str}: {e}")
            return []

    def _init_structure_state(self) -> None:
        """Initialize incremental structure state from Play specs (legacy single-TF)."""
        self._init_structure_states()

    def _init_structure_states(self) -> None:
        """Initialize incremental structure states for all TFs from Play specs."""
        from src.structures import TFIncrementalState

        if not self._play.structures:
            return

        # Get structure specs for each TF role
        # Play.structures is a dict keyed by TF role: {"exec": [...], "high_tf": [...], etc.}

        # low_tf / exec structures
        exec_specs = self._play.structures.get("exec", [])
        low_tf_specs = self._play.structures.get("low_tf", [])
        combined_low_tf = exec_specs + low_tf_specs
        if combined_low_tf:
            try:
                self._low_tf_structure = TFIncrementalState(
                    self._tf_mapping["low_tf"],
                    combined_low_tf,
                )
                # Set legacy alias
                self._structure_state = self._low_tf_structure
                logger.info(f"Initialized low_tf structure state with {len(combined_low_tf)} specs")
            except Exception as e:
                logger.warning(f"Failed to initialize low_tf structure state: {e}")

        # med_tf structures (only if different from low_tf)
        if self._tf_mapping["med_tf"] != self._tf_mapping["low_tf"]:
            med_tf_specs = self._play.structures.get("med_tf", [])
            if med_tf_specs:
                try:
                    self._med_tf_structure = TFIncrementalState(
                        self._tf_mapping["med_tf"],
                        med_tf_specs,
                    )
                    logger.info(f"Initialized med_tf structure state with {len(med_tf_specs)} specs")
                except Exception as e:
                    logger.warning(f"Failed to initialize med_tf structure state: {e}")

        # high_tf structures (only if different from med_tf)
        if self._tf_mapping["high_tf"] != self._tf_mapping["med_tf"]:
            high_tf_specs = self._play.structures.get("high_tf", [])
            if high_tf_specs:
                try:
                    self._high_tf_structure = TFIncrementalState(
                        self._tf_mapping["high_tf"],
                        high_tf_specs,
                    )
                    logger.info(f"Initialized high_tf structure state with {len(high_tf_specs)} specs")
                except Exception as e:
                    logger.warning(f"Failed to initialize high_tf structure state: {e}")

    def get_candle(self, index: int, tf_role: str | None = None) -> Candle:
        """
        Get candle at index from specified TF buffer.

        Args:
            index: Negative index for live (-1 = latest, -2 = previous, etc.)
            tf_role: TF role (low_tf, med_tf, high_tf). If None, uses exec buffer.

        Returns:
            Candle data
        """
        # Get the appropriate buffer
        if tf_role == "low_tf":
            buffer = self._low_tf_buffer
        elif tf_role == "med_tf":
            buffer = self._med_tf_buffer
        elif tf_role == "high_tf":
            buffer = self._high_tf_buffer
        else:
            buffer = self._exec_buffer

        if not buffer:
            raise RuntimeError(f"No candles in {tf_role or 'exec'} buffer. Is WebSocket connected?")

        # Support both positive (backtest-style) and negative (live-style) indexing
        if index < 0:
            # Live-style: -1 = latest
            actual_idx = index
        else:
            # Backtest-style: positive index
            actual_idx = index

        if abs(actual_idx) > len(buffer) if actual_idx < 0 else actual_idx >= len(buffer):
            raise IndexError(f"Index {index} out of buffer bounds (buffer size: {len(buffer)})")

        return buffer[actual_idx]

    def get_indicator(self, name: str, index: int, tf_role: str | None = None) -> float:
        """
        Get indicator value at index from specified TF.

        Args:
            name: Indicator name
            index: Bar index
            tf_role: TF role (low_tf, med_tf, high_tf). If None, uses exec cache.

        Returns:
            Indicator value
        """
        cache = self._get_indicator_cache_for_role(tf_role)
        return cache.get(name, index)

    def _get_indicator_cache_for_role(self, tf_role: str | None) -> LiveIndicatorCache:
        """Get the indicator cache for a TF role."""
        if tf_role == "low_tf":
            return self._low_tf_indicators
        elif tf_role == "med_tf" and self._med_tf_indicators:
            return self._med_tf_indicators
        elif tf_role == "high_tf" and self._high_tf_indicators:
            return self._high_tf_indicators
        return self._exec_indicators

    def get_structure(self, key: str, field: str, tf_role: str | None = None) -> float:
        """
        Get current structure field value.

        Args:
            key: Structure key
            field: Field name
            tf_role: TF role (low_tf, med_tf, high_tf). If None, uses exec structure.

        Returns:
            Structure field value
        """
        structure = self._get_structure_for_role(tf_role)
        if structure is None:
            raise RuntimeError(f"Structure state not initialized for {tf_role or 'exec'}")

        return structure.get_value(key, field)

    def _get_structure_for_role(self, tf_role: str | None) -> "TFIncrementalState | None":
        """Get the structure state for a TF role."""
        if tf_role == "low_tf":
            return self._low_tf_structure
        elif tf_role == "med_tf":
            return self._med_tf_structure
        elif tf_role == "high_tf":
            return self._high_tf_structure
        # Default: use exec role
        if self._exec_role == "high_tf":
            return self._high_tf_structure
        elif self._exec_role == "med_tf":
            return self._med_tf_structure
        return self._low_tf_structure

    def get_structure_at(self, key: str, field: str, index: int, tf_role: str | None = None) -> float:
        """
        Get structure field at specific index.

        Args:
            key: Structure key
            field: Field name
            index: Bar index
            tf_role: TF role (low_tf, med_tf, high_tf). If None, uses exec structure.

        Returns:
            Structure field value
        """
        structure = self._get_structure_for_role(tf_role)
        if structure is None:
            raise RuntimeError(f"Structure state not initialized for {tf_role or 'exec'}")

        # For now, just return current value (full history not tracked in live)
        # P3: Track structure history for lookback (ring buffer per structure field)
        return structure.get_value(key, field)

    def has_indicator(self, name: str, tf_role: str | None = None) -> bool:
        """Check if indicator exists in specified TF cache."""
        cache = self._get_indicator_cache_for_role(tf_role)
        return cache.has_indicator(name)

    def is_ready(self) -> bool:
        """Check if data provider is ready. Thread-safe."""
        with self._buffer_lock:
            return self._ready

    def on_candle_close(self, candle: Candle, timeframe: str | None = None) -> None:
        """
        Called when a new candle closes.

        Updates buffer, computes indicators, updates structures.

        Args:
            candle: The closed candle
            timeframe: The timeframe this candle belongs to. If None, assumes exec TF.
        """
        # Determine which TF role this candle belongs to
        if timeframe is None:
            timeframe = self._timeframe

        tf_role = self._get_tf_role_for_timeframe(timeframe)

        # Route to correct buffer and indicator cache
        if tf_role == "low_tf":
            self._update_tf_buffer(
                candle, self._low_tf_buffer, self._low_tf_indicators, self._low_tf_structure
            )
        elif tf_role == "med_tf":
            self._update_tf_buffer(
                candle, self._med_tf_buffer, self._med_tf_indicators, self._med_tf_structure
            )
        elif tf_role == "high_tf":
            self._update_tf_buffer(
                candle, self._high_tf_buffer, self._high_tf_indicators, self._high_tf_structure
            )

        # Check warmup (exec buffer must have enough bars)
        with self._buffer_lock:
            if not self._ready and len(self._exec_buffer) >= self._warmup_bars:
                self._ready = True
                logger.info("LiveDataProvider ready (warmup complete)")

    def _get_tf_role_for_timeframe(self, timeframe: str) -> str:
        """Map a timeframe string to its TF role (low_tf, med_tf, high_tf)."""
        if timeframe == self._tf_mapping["low_tf"]:
            return "low_tf"
        elif timeframe == self._tf_mapping["med_tf"]:
            return "med_tf"
        elif timeframe == self._tf_mapping["high_tf"]:
            return "high_tf"
        # Default to low_tf if unknown
        return "low_tf"

    def _update_tf_buffer(
        self,
        candle: Candle,
        buffer: list[Candle],
        indicator_cache: LiveIndicatorCache | None,
        structure_state: "TFIncrementalState | None",
    ) -> None:
        """Update a specific TF's buffer, indicators, and structures. Thread-safe."""
        # G6.2.2: Thread safety - lock buffer access
        with self._buffer_lock:
            # Add to buffer
            buffer.append(candle)

            # Trim buffer if needed
            if len(buffer) > self._buffer_size:
                del buffer[:-self._buffer_size]

            buffer_len = len(buffer)

        # Update indicators (has its own lock)
        if indicator_cache is not None:
            indicator_cache.update(candle)

        # Update structure state
        if structure_state is not None:
            self._update_structure_state_for_tf(structure_state, buffer_len - 1, candle)

    def _update_structure_state(self, bar_idx: int) -> None:
        """Update structure state with latest candle (legacy single-TF method)."""
        if self._structure_state is None:
            return

        candle = self._exec_buffer[-1] if self._exec_buffer else None
        if candle is None:
            return

        self._update_structure_state_for_tf(self._structure_state, bar_idx, candle)

    def _update_structure_state_for_tf(
        self,
        structure_state: "TFIncrementalState",
        bar_idx: int,
        candle: Candle,
    ) -> None:
        """Update structure state for a specific TF with the given candle."""
        from src.structures import BarData

        # Get indicator values for structure computation
        # Use the appropriate indicator cache based on which structure state this is
        indicator_cache = self._low_tf_indicators
        if structure_state is self._med_tf_structure and self._med_tf_indicators:
            indicator_cache = self._med_tf_indicators
        elif structure_state is self._high_tf_structure and self._high_tf_indicators:
            indicator_cache = self._high_tf_indicators

        indicator_values: dict[str, float] = {}
        for name in indicator_cache._indicators.keys():
            try:
                val = indicator_cache.get(name, -1)
                if not np.isnan(val):
                    indicator_values[name] = val
            except (IndexError, KeyError):
                pass

        bar_data = BarData(
            idx=bar_idx,
            open=candle.open,
            high=candle.high,
            low=candle.low,
            close=candle.close,
            volume=candle.volume,
            indicators=indicator_values,
        )

        try:
            structure_state.update(bar_data)
        except Exception as e:
            logger.warning(f"Failed to update structure state: {e}")


class LiveExchange:
    """
    ExchangeAdapter that wraps OrderExecutor and PositionManager.

    Provides real order execution via Bybit API:
    - Market and limit orders
    - Position tracking
    - TP/SL as conditional orders

    Integrates with existing OrderExecutor and PositionManager.
    """

    def __init__(self, play: "Play", config: PlayEngineConfig, demo: bool = True):
        """
        Initialize live exchange adapter.

        Args:
            play: Play instance
            config: Engine configuration
            demo: If True, use demo API
        """
        self._play = play
        self._config = config
        self._demo = demo
        self._symbol = play.symbol_universe[0]

        # These will be initialized during connect
        self._order_executor = None
        self._position_manager = None
        self._exchange_manager = None
        self._risk_manager = None

        # RealtimeState for account data
        self._realtime_state = None

        # Tracking
        self._connected = False

        logger.info(
            f"LiveExchange initialized: {self._symbol} demo={demo}"
        )

    async def connect(self) -> None:
        """
        Connect to exchange and initialize components.

        Uses existing infrastructure: ExchangeManager, RiskManager,
        OrderExecutor, and PositionManager.
        """
        from ...core.exchange_manager import ExchangeManager
        from ...core.risk_manager import RiskManager, RiskConfig
        from ...core.order_executor import OrderExecutor
        from ...core.position_manager import PositionManager
        from ...data.realtime_state import get_realtime_state

        try:
            # Get realtime state for account data
            self._realtime_state = get_realtime_state()

            # Initialize exchange manager
            self._exchange_manager = ExchangeManager()

            # Initialize position manager
            self._position_manager = PositionManager(self._exchange_manager)

            # Initialize risk manager with config from Play
            # G0.2: Remove invalid position_manager param, G0.3: pass exchange_manager
            risk_config = self._build_risk_config()
            self._risk_manager = RiskManager(
                config=risk_config,
                enable_global_risk=True,
                exchange_manager=self._exchange_manager,
            )

            # Initialize order executor
            self._order_executor = OrderExecutor(
                exchange_manager=self._exchange_manager,
                risk_manager=self._risk_manager,
                position_manager=self._position_manager,
                use_ws_feedback=True,  # Use WebSocket for fast feedback
            )

            self._connected = True
            logger.info(f"LiveExchange connected: {self._symbol}")

        except Exception as e:
            logger.error(f"Failed to connect LiveExchange: {e}")
            raise

    def _build_risk_config(self):
        """Build RiskConfig from Play settings."""
        from ...core.risk_manager import RiskConfig

        # Start with defaults
        config = RiskConfig()

        # Apply Play-specific settings
        account = self._play.account
        risk_model = self._play.risk_model

        # G6.0.1: Use SizingConfig max_position_equity_pct (default 95%)
        # The PlayEngineConfig doesn't have max_position_pct - use default
        max_position_pct = 95.0  # SizingConfig default
        config.max_position_value = account.starting_equity_usdt * (
            max_position_pct / 100.0
        )

        if risk_model:
            # Apply risk limits from Play
            if hasattr(risk_model, 'max_daily_trades'):
                config.max_daily_trades = risk_model.max_daily_trades

        return config

    async def disconnect(self) -> None:
        """Disconnect from exchange."""
        self._connected = False
        logger.info(f"LiveExchange disconnected: {self._symbol}")

    def submit_order(self, order: Order) -> OrderResult:
        """Submit order for execution."""
        if self._order_executor is None:
            return OrderResult(
                success=False,
                error="Exchange not connected. Call connect() first.",
            )

        from ...core.risk_manager import Signal

        try:
            # Convert unified Order to Signal format
            signal = Signal(
                symbol=order.symbol,
                direction=self._order_side_to_direction(order.side),
                size_usdt=order.size_usdt,
                stop_loss=order.stop_loss,
                take_profit=order.take_profit,
                order_type=order.order_type.lower(),
                limit_price=order.limit_price,
            )

            # Execute through OrderExecutor
            exec_result = self._order_executor.execute(signal)

            # Convert to unified OrderResult
            return OrderResult(
                success=exec_result.success,
                order_id=exec_result.order_result.order_id if exec_result.order_result else None,
                exchange_order_id=exec_result.order_result.order_id if exec_result.order_result else None,
                fill_price=exec_result.order_result.avg_price if exec_result.order_result else None,
                fill_usdt=exec_result.executed_size,
                error=exec_result.error,
                metadata={
                    "risk_check": exec_result.risk_check.to_dict() if exec_result.risk_check else None,
                    "source": exec_result.source,
                },
            )

        except Exception as e:
            logger.error(f"Order submission failed: {e}")
            return OrderResult(
                success=False,
                error=str(e),
            )

    def _order_side_to_direction(self, side: str) -> str:
        """Convert order side to direction string."""
        side_upper = side.upper()
        if side_upper in ("LONG", "BUY"):
            return "long"
        elif side_upper in ("SHORT", "SELL"):
            return "short"
        elif side_upper == "FLAT":
            return "close"
        return side.lower()

    def cancel_order(self, order_id: str) -> bool:
        """Cancel pending order."""
        if self._exchange_manager is None:
            return False

        try:
            result = self._exchange_manager.cancel_order(
                symbol=self._symbol,
                order_id=order_id,
            )
            return result.success if result else False
        except Exception as e:
            logger.error(f"Cancel order failed: {e}")
            return False

    def get_position(self, symbol: str) -> Position | None:
        """Get current position."""
        # Try RealtimeState first (WebSocket-fed)
        if self._realtime_state:
            pos_data = self._realtime_state.get_position(symbol)
            if pos_data and pos_data.is_open:
                return Position(
                    symbol=pos_data.symbol,
                    side="LONG" if pos_data.side.lower() == "buy" else "SHORT",
                    size_usdt=pos_data.position_value,
                    size_qty=pos_data.size,
                    entry_price=pos_data.entry_price,
                    mark_price=pos_data.mark_price,
                    unrealized_pnl=pos_data.unrealized_pnl,
                    leverage=pos_data.leverage,
                    stop_loss=pos_data.stop_loss,
                    take_profit=pos_data.take_profit,
                    liquidation_price=pos_data.liq_price,
                )

        # Fall back to PositionManager
        if self._position_manager:
            pm_pos = self._position_manager.get_position(symbol)
            if pm_pos:
                return Position(
                    symbol=pm_pos.symbol,
                    side=pm_pos.side.upper(),
                    size_usdt=pm_pos.size_usdt,
                    size_qty=pm_pos.size_qty,
                    entry_price=pm_pos.entry_price,
                    mark_price=pm_pos.mark_price,
                    unrealized_pnl=pm_pos.unrealized_pnl,
                    leverage=pm_pos.leverage,
                )

        return None

    def get_balance(self) -> float:
        """Get available balance."""
        # Try RealtimeState first
        if self._realtime_state:
            metrics = self._realtime_state.get_account_metrics()
            if metrics:
                return metrics.total_available_balance

            wallet = self._realtime_state.get_wallet("USDT")
            if wallet:
                return wallet.available_balance

        # Fall back to REST
        if self._exchange_manager:
            try:
                balance = self._exchange_manager.get_balance()
                return balance.available if balance else self._config.initial_equity
            except Exception:
                pass

        return self._config.initial_equity

    def get_equity(self) -> float:
        """Get total equity."""
        # Try RealtimeState first
        if self._realtime_state:
            metrics = self._realtime_state.get_account_metrics()
            if metrics:
                return metrics.total_equity

            wallet = self._realtime_state.get_wallet("USDT")
            if wallet:
                return wallet.equity

        # Fall back to REST
        if self._exchange_manager:
            try:
                balance = self._exchange_manager.get_balance()
                return balance.equity if balance else self._config.initial_equity
            except Exception:
                pass

        return self._config.initial_equity

    def get_realized_pnl(self) -> float:
        """
        Get total realized PnL since start.

        P3: Track from exchange trade history or accumulate locally.
        For now returns 0.0 - requires integration with position close events.
        """
        # Future: Could accumulate from closed position history
        # or query exchange for session realized PnL
        return 0.0

    def get_pending_orders(self, symbol: str | None = None) -> list[Order]:
        """Get pending orders."""
        orders = []

        # Try RealtimeState first
        if self._realtime_state:
            open_orders = self._realtime_state.get_open_orders(symbol)
            for order_data in open_orders:
                orders.append(Order(
                    symbol=order_data.symbol,
                    side="LONG" if order_data.side.lower() == "buy" else "SHORT",
                    size_usdt=order_data.value,
                    order_type=order_data.order_type.upper(),
                    limit_price=order_data.price if order_data.order_type.lower() == "limit" else None,
                    client_order_id=order_data.order_id,
                ))
            return orders

        # Fall back to REST
        if self._exchange_manager:
            try:
                rest_orders = self._exchange_manager.get_open_orders(symbol)
                for od in rest_orders:
                    orders.append(Order(
                        symbol=od.get("symbol", self._symbol),
                        side="LONG" if od.get("side", "").lower() == "buy" else "SHORT",
                        size_usdt=float(od.get("orderValue", 0)),
                        order_type=od.get("orderType", "MARKET").upper(),
                        limit_price=float(od.get("price", 0)) if od.get("price") else None,
                        client_order_id=od.get("orderId"),
                    ))
            except Exception as e:
                logger.warning(f"Failed to get open orders: {e}")

        return orders

    def step(self, candle: Candle) -> None:
        """
        Process new candle.

        For live mode, this is a no-op since the exchange
        handles fills asynchronously via WebSocket.
        """
        pass  # Exchange handles fills via WebSocket

    def submit_close(self, reason: str = "signal", percent: float = 100.0) -> None:
        """
        Submit close order for current position.

        Args:
            reason: Reason for close (e.g., "signal", "stop_loss", "take_profit")
            percent: Percentage of position to close (1-100)

        Called by PlayEngine when exit signal triggers.
        """
        position = self.get_position(self._symbol)
        if position is None:
            logger.warning(f"submit_close called but no position for {self._symbol}")
            return

        # Calculate close size
        close_qty = position.size_qty * (percent / 100.0)

        # Determine close side (opposite of position)
        close_side = "Sell" if position.side.upper() == "LONG" else "Buy"

        logger.info(
            f"Submitting close order: {self._symbol} {close_side} "
            f"qty={close_qty:.6f} ({percent}%) reason={reason}"
        )

        if self._exchange_manager is None:
            logger.error("Exchange not connected. Cannot close position.")
            return

        try:
            # Use ExchangeManager to close position
            result = self._exchange_manager.place_order(
                symbol=self._symbol,
                side=close_side,
                order_type="Market",
                qty=close_qty,
                reduce_only=True,  # Ensures this only closes, doesn't flip
            )

            if result and result.success:
                logger.info(
                    f"Close order submitted: order_id={result.order_id} "
                    f"avg_price={result.avg_price}"
                )
            else:
                error_msg = result.error if result else "Unknown error"
                logger.error(f"Close order failed: {error_msg}")

        except Exception as e:
            logger.error(f"Failed to submit close order: {e}")

    @property
    def has_position(self) -> bool:
        """Check if there's an open position."""
        pos = self.get_position(self._symbol)
        return pos is not None

    @property
    def is_connected(self) -> bool:
        """Check if connected to exchange."""
        return self._connected
