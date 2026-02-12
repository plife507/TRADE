"""
Live adapters for PlayEngine.

These adapters connect to real exchange infrastructure:
- LiveDataProvider: WebSocket data + indicator cache
- LiveExchange: OrderExecutor + PositionManager

Integrates with existing RealtimeState/RealtimeBootstrap infrastructure.
"""


import threading
from collections import deque
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Literal

import numpy as np
import pandas as pd

from src.backtest.runtime.timeframe import tf_minutes
from src.config.constants import DataEnv, validate_data_env
from src.utils.time_range import TimeRange

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
                        self._incremental[feature.output_key] = (inc_ind, feature)

                        # Use registry to determine input requirements and outputs
                        info = registry.get_indicator_info(ind_type)
                        needs_hlc = info.requires_hlc

                        # Initialize arrays for all outputs
                        if info.is_multi_output:
                            for suffix in info.output_keys:
                                key = f"{feature.output_key}_{suffix}"
                                self._indicators[key] = np.full(n, np.nan)
                        else:
                            self._indicators[feature.output_key] = np.full(n, np.nan)

                        # Warmup with historical data
                        needs_volume = info.requires_volume
                        for i in range(n):
                            if needs_hlc:
                                kwargs: dict = dict(
                                    high=self._high[i],
                                    low=self._low[i],
                                    close=self._close[i],
                                )
                                if needs_volume:
                                    kwargs["volume"] = self._volume[i]
                                inc_ind.update(**kwargs)
                            else:
                                # Route primary input by feature's input_source
                                input_val = self._resolve_input_from_arrays(feature, i)
                                kwargs = dict(close=input_val)
                                if needs_volume:
                                    kwargs["volume"] = self._volume[i]
                                inc_ind.update(**kwargs)

                            # Store all outputs for multi-output indicators
                            if info.is_multi_output:
                                for suffix in info.output_keys:
                                    key = f"{feature.output_key}_{suffix}"
                                    value = self._get_incremental_output(inc_ind, suffix)
                                    self._indicators[key][i] = value
                            else:
                                self._indicators[feature.output_key][i] = inc_ind.value
                    else:
                        self._vectorized_specs.append(spec)
                else:
                    self._vectorized_specs.append(spec)
            except Exception as e:
                logger.warning(f"Failed to initialize indicator {spec}: {e}")

        # Compute vectorized indicators
        self._compute_vectorized()

    def _resolve_input_from_candle(self, feature, candle: Candle) -> float:
        """Resolve primary input value from candle based on feature's input_source."""
        source = feature.input_source
        source_str = source.value if hasattr(source, 'value') else str(source).lower()
        if source_str == "volume":
            return float(candle.volume)
        elif source_str == "open":
            return float(candle.open)
        elif source_str == "high":
            return float(candle.high)
        elif source_str == "low":
            return float(candle.low)
        elif source_str == "hlc3":
            return float(candle.hlc3)
        elif source_str == "ohlc4":
            return float(candle.ohlc4)
        return float(candle.close)

    def _resolve_input_from_arrays(self, feature, idx: int) -> float:
        """Resolve primary input value from OHLCV arrays based on feature's input_source."""
        source = feature.input_source
        source_str = source.value if hasattr(source, 'value') else str(source).lower()
        if source_str == "volume":
            return float(self._volume[idx])
        elif source_str == "open":
            return float(self._open[idx])
        elif source_str == "high":
            return float(self._high[idx])
        elif source_str == "low":
            return float(self._low[idx])
        elif source_str == "hlc3":
            return (float(self._high[idx]) + float(self._low[idx]) + float(self._close[idx])) / 3.0
        elif source_str == "ohlc4":
            return (float(self._open[idx]) + float(self._high[idx]) + float(self._low[idx]) + float(self._close[idx])) / 4.0
        return float(self._close[idx])

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
                    kwargs: dict = dict(
                        high=float(candle.high),
                        low=float(candle.low),
                        close=float(candle.close),
                    )
                    if info.requires_volume:
                        kwargs["volume"] = float(candle.volume)
                    inc_ind.update(**kwargs)
                else:
                    # Route primary input by feature's input_source
                    input_val = self._resolve_input_from_candle(feature, candle)
                    kwargs = dict(close=input_val)
                    if info.requires_volume:
                        kwargs["volume"] = float(candle.volume)
                    inc_ind.update(**kwargs)

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
        from ...backtest.indicator_vendor import compute_indicator

        for spec in self._vectorized_specs:
            try:
                feature = FeatureSpec.from_dict(spec)
                result = compute_indicator(
                    feature.indicator_type,
                    close=pd.Series(self._close),
                    high=pd.Series(self._high),
                    low=pd.Series(self._low),
                    open_=pd.Series(self._open),
                    volume=pd.Series(self._volume),
                    **feature.params,
                )
                if isinstance(result, dict):
                    # Multi-output: store each output separately
                    for suffix, series in result.items():
                        key = f"{feature.output_key}_{suffix}"
                        self._indicators[key] = series.to_numpy() if hasattr(series, 'to_numpy') else np.asarray(series)
                else:
                    self._indicators[feature.output_key] = result.to_numpy() if hasattr(result, 'to_numpy') else np.asarray(result)
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

    def audit_incremental_parity(self, tolerance: float = 1e-8) -> dict[str, dict]:
        """
        WU-03: Audit incremental vs vectorized indicator computation parity.

        Recomputes all indicators using vectorized computation and compares
        with incrementally computed values. Returns any discrepancies.

        Args:
            tolerance: Maximum allowed difference (default 1e-8)

        Returns:
            Dict with audit results per indicator:
            {
                "indicator_name": {
                    "max_diff": 0.0,
                    "num_mismatches": 0,
                    "mismatch_indices": [],
                    "pass": True,
                }
            }
        """
        import pandas as pd
        from ...backtest.indicator_vendor import compute_indicator

        results = {}

        with self._lock:
            if self._bar_count == 0:
                return results

            # Build pandas Series from arrays for vectorized computation
            close_s = pd.Series(self._close)
            high_s = pd.Series(self._high)
            low_s = pd.Series(self._low)
            open_s = pd.Series(self._open)
            volume_s = pd.Series(self._volume)

            # For each incrementally computed indicator, recompute vectorized
            for name, (inc_ind, feature) in self._incremental.items():
                try:
                    # Determine primary input based on feature's input_source
                    source_str = (
                        feature.input_source.value
                        if hasattr(feature.input_source, 'value')
                        else str(feature.input_source).lower()
                    )
                    if source_str == "volume":
                        primary_input = volume_s
                    elif source_str == "open":
                        primary_input = open_s
                    elif source_str == "high":
                        primary_input = high_s
                    elif source_str == "low":
                        primary_input = low_s
                    elif source_str == "hlc3":
                        primary_input = (high_s + low_s + close_s) / 3.0
                    elif source_str == "ohlc4":
                        primary_input = (open_s + high_s + low_s + close_s) / 4.0
                    else:
                        primary_input = close_s

                    # Recompute using vectorized method
                    vec_result = compute_indicator(
                        feature.indicator_type,
                        close=primary_input,
                        high=high_s,
                        low=low_s,
                        open_=open_s,
                        volume=volume_s,
                        **feature.params,
                    )

                    # Handle single vs multi-output
                    if isinstance(vec_result, dict):
                        # Multi-output: take first output
                        vectorized = next(iter(vec_result.values())).to_numpy()
                    else:
                        vectorized = vec_result.to_numpy()

                    # Get incremental values
                    incremental = self._indicators.get(name, np.array([]))

                    if len(vectorized) == 0 or len(incremental) == 0:
                        results[name] = {
                            "max_diff": 0.0,
                            "num_mismatches": 0,
                            "mismatch_indices": [],
                            "pass": True,
                            "note": "No values to compare",
                        }
                        continue

                    # Compare values (skip NaN positions)
                    min_len = min(len(vectorized), len(incremental))
                    diffs = []
                    mismatch_indices = []

                    for i in range(min_len):
                        v_val = vectorized[i]
                        i_val = incremental[i]

                        # Skip if either is NaN
                        if np.isnan(v_val) or np.isnan(i_val):
                            continue

                        diff = abs(v_val - i_val)
                        diffs.append(diff)
                        if diff > tolerance:
                            mismatch_indices.append(i)

                    max_diff = max(diffs) if diffs else 0.0
                    results[name] = {
                        "max_diff": max_diff,
                        "num_mismatches": len(mismatch_indices),
                        "mismatch_indices": mismatch_indices[:10],  # First 10
                        "pass": len(mismatch_indices) == 0,
                    }

                except Exception as e:
                    results[name] = {
                        "max_diff": -1.0,
                        "num_mismatches": -1,
                        "mismatch_indices": [],
                        "pass": False,
                        "error": str(e),
                    }

        return results


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
        tf_config = play.tf_mapping if play.tf_mapping else {}
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

        # G16.3: Structure history ring buffer for lookback
        # Key: (tf_role, struct_key, field) -> deque of (bar_idx, value)
        self._structure_history: dict[tuple[str, str, str], deque] = {}

        # Tracking
        self._ready = False
        # WU-01, WU-06: Configurable warmup bars (default 100)
        # Reads from Play.warmup_bars if present, otherwise defaults to 100
        # 100 bars ensures most indicators (EMA, RSI, etc.) have sufficient history
        self._warmup_bars = getattr(play, 'warmup_bars', 100)
        self._current_bar_index: int = -1

        # WU-02: Track warmup state per TF for multi-TF sync
        self._low_tf_ready: bool = False
        self._med_tf_ready: bool = False
        self._high_tf_ready: bool = False

        # Environment for multi-TF buffer lookup
        self._env: DataEnv = "demo" if demo else "live"

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

        # WU-05: Initialize structure states for each TF if Play has structures
        # Track structure warmup readiness alongside indicator warmup
        if self._play.has_structures:
            self._init_structure_states()

        # WU-02, WU-04: Check warmup for all TFs (not just exec)
        # All active TFs must have sufficient bars with valid (non-NaN) indicators
        self._check_all_tf_warmup()

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
        """Get indicator specs for a specific TF role from Play.

        Converts Feature objects into dicts compatible with
        ``FeatureSpec.from_dict()`` (maps ``Feature.id`` → ``output_key``).
        """
        if not self._play.features:
            return []

        tf_str = self._tf_mapping[tf_role]
        specs = []
        for feature in self._play.features:
            # Feature is a dataclass -- read .tf directly
            if getattr(feature, "tf", None) != tf_str:
                continue
            # Only include indicators (not structures)
            if getattr(feature, "type", None) is not None:
                from ...backtest.feature_registry import FeatureType
                if feature.type != FeatureType.INDICATOR:
                    continue
            # Build FeatureSpec-compatible dict
            input_source = getattr(feature, "input_source", None)
            if input_source is not None and hasattr(input_source, "value"):
                input_source = input_source.value
            else:
                input_source = str(input_source) if input_source else "close"
            specs.append({
                "indicator_type": feature.indicator_type,
                "output_key": feature.id,
                "params": dict(feature.params) if feature.params else {},
                "input_source": input_source,
            })
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

            # Query DuckDB (G14.1: use get_ohlcv, not query_ohlcv)
            df = store.get_ohlcv(
                symbol=self._symbol,
                tf=tf_str,
                start=start,
                end=end,
            )

            if df is None or df.empty:
                logger.info(f"No bars in DuckDB for {self._symbol} {tf_str}")
                return []

            # Convert DataFrame rows to BarRecord objects
            bars = []
            for _, row in df.iterrows():
                ts = row['timestamp']
                if not isinstance(ts, datetime):
                    ts = datetime.fromisoformat(str(ts))
                bar = BarRecord(
                    timestamp=ts,
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

    def _get_structure_specs_by_tf_role(self) -> dict[str, list[dict]]:
        """Derive structure specs grouped by TF role from play.features.

        Each structure Feature already carries its concrete TF string.
        We reverse-map concrete TFs back to roles using ``_tf_mapping``
        so the live adapter knows which ``TFIncrementalState`` to feed.

        Returns:
            Dict keyed by TF role ("low_tf", "med_tf", "high_tf") with
            lists of spec dicts suitable for ``TFIncrementalState``.
        """
        from ...backtest.feature_registry import FeatureType

        # Build reverse map: concrete TF → set of roles
        tf_to_roles: dict[str, list[str]] = {}
        for role in ("low_tf", "med_tf", "high_tf"):
            tf_str = self._tf_mapping[role]
            tf_to_roles.setdefault(tf_str, []).append(role)

        # Also map the exec role's concrete TF to low_tf (exec → low_tf by convention)
        exec_role = self._tf_mapping.get("exec", "low_tf")
        exec_tf = self._tf_mapping.get(exec_role, self._tf_mapping.get("low_tf", ""))
        tf_to_roles.setdefault(exec_tf, [])

        result: dict[str, list[dict]] = {"low_tf": [], "med_tf": [], "high_tf": []}

        for feature in self._play.features:
            if getattr(feature, "type", None) != FeatureType.STRUCTURE:
                continue
            spec = {
                "type": feature.structure_type,
                "key": feature.id,
                "params": dict(feature.params) if feature.params else {},
            }
            if feature.uses:
                spec["uses"] = list(feature.uses)

            # Map concrete TF to the highest-priority role
            roles = tf_to_roles.get(feature.tf, [])
            if roles:
                # Prefer lowest role: low_tf > med_tf > high_tf
                target = roles[0]
            else:
                # Unknown TF — default to low_tf
                target = "low_tf"
            result[target].append(spec)

        return result

    def _init_structure_states(self) -> None:
        """Initialize incremental structure states for all TFs from Play features."""
        from src.structures import TFIncrementalState

        if not self._play.has_structures:
            return

        specs_by_role = self._get_structure_specs_by_tf_role()

        # low_tf / exec structures
        low_tf_specs = specs_by_role["low_tf"]
        if low_tf_specs:
            try:
                self._low_tf_structure = TFIncrementalState(
                    self._tf_mapping["low_tf"],
                    low_tf_specs,
                )
                logger.info(f"Initialized low_tf structure state with {len(low_tf_specs)} specs")
            except Exception as e:
                logger.warning(f"Failed to initialize low_tf structure state: {e}")

        # med_tf structures (only if different from low_tf)
        if self._tf_mapping["med_tf"] != self._tf_mapping["low_tf"]:
            med_tf_specs = specs_by_role["med_tf"]
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
            high_tf_specs = specs_by_role["high_tf"]
            if high_tf_specs:
                try:
                    self._high_tf_structure = TFIncrementalState(
                        self._tf_mapping["high_tf"],
                        high_tf_specs,
                    )
                    logger.info(f"Initialized high_tf structure state with {len(high_tf_specs)} specs")
                except Exception as e:
                    logger.warning(f"Failed to initialize high_tf structure state: {e}")

    def get_candle(self, index: int) -> Candle:
        """
        Get candle at index from exec buffer (DataProvider protocol).

        Args:
            index: Negative index for live (-1 = latest, -2 = previous, etc.)

        Returns:
            Candle data
        """
        return self.get_candle_for_tf(index, tf_role=None)

    def get_candle_for_tf(self, index: int, tf_role: str | None = None) -> Candle:
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

    def get_indicator(self, name: str, index: int) -> float:
        """
        Get indicator value at index from exec cache (DataProvider protocol).

        Args:
            name: Indicator name
            index: Bar index

        Returns:
            Indicator value
        """
        return self.get_indicator_for_tf(name, index, tf_role=None)

    def get_indicator_for_tf(self, name: str, index: int, tf_role: str | None = None) -> float:
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

    def get_structure(self, key: str, field: str) -> float:
        """
        Get current structure field value (DataProvider protocol).

        Args:
            key: Structure key
            field: Field name

        Returns:
            Structure field value
        """
        return self.get_structure_for_tf(key, field, tf_role=None)

    def get_structure_for_tf(self, key: str, field: str, tf_role: str | None = None) -> float:
        """
        Get current structure field value for a specific TF.

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

        return float(structure.get_value(key, field))

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

    def get_structure_at(self, key: str, field: str, index: int) -> float:
        """
        Get structure field at specific index (DataProvider protocol).

        Args:
            key: Structure key
            field: Field name
            index: Bar index

        Returns:
            Structure field value
        """
        return self.get_structure_at_for_tf(key, field, index, tf_role=None)

    def get_structure_at_for_tf(
        self, key: str, field: str, index: int, tf_role: str | None = None
    ) -> float:
        """
        Get structure field at specific index for a specific TF.

        Supports negative indexing for lookback (-1 = latest, -2 = previous, etc.).

        Args:
            key: Structure key
            field: Field name
            index: Bar index (negative for lookback)
            tf_role: TF role (low_tf, med_tf, high_tf). If None, uses exec structure.

        Returns:
            Structure field value
        """
        structure = self._get_structure_for_role(tf_role)
        if structure is None:
            raise RuntimeError(f"Structure state not initialized for {tf_role or 'exec'}")

        # G16.3: Use ring buffer for lookback (negative index)
        resolved_role = tf_role
        if resolved_role is None:
            # Resolve exec pointer to actual role
            resolved_role = self._exec_role
        buf_key = (resolved_role, key, field)
        buf = self._structure_history.get(buf_key)
        if buf and index < 0:
            abs_idx = len(buf) + index
            if 0 <= abs_idx < len(buf):
                return buf[abs_idx][1]

        # Fall through to current value for non-negative index or empty buffer
        return float(structure.get_value(key, field))

    def has_indicator(self, name: str, tf_role: str | None = None) -> bool:
        """Check if indicator exists in specified TF cache."""
        cache = self._get_indicator_cache_for_role(tf_role)
        return cache.has_indicator(name)

    def is_ready(self) -> bool:
        """Check if data provider is ready. Thread-safe."""
        with self._buffer_lock:
            return self._ready

    def _check_all_tf_warmup(self) -> None:
        """
        WU-02, WU-04: Check warmup status for all active TFs.

        Provider is only ready when ALL active TFs have:
        1. Sufficient bars (>= warmup_bars)
        2. Valid (non-NaN) indicator values for the latest bar

        This ensures multi-TF strategies don't start with incomplete data.
        """
        # Check low_tf (always required)
        self._low_tf_ready = self._check_tf_warmup(
            self._low_tf_buffer, self._low_tf_indicators
        )

        # Check med_tf only if different from low_tf
        if self._tf_mapping["med_tf"] != self._tf_mapping["low_tf"]:
            self._med_tf_ready = self._check_tf_warmup(
                self._med_tf_buffer, self._med_tf_indicators
            )
        else:
            self._med_tf_ready = True  # Same as low_tf, already checked

        # Check high_tf only if different from med_tf
        if self._tf_mapping["high_tf"] != self._tf_mapping["med_tf"]:
            self._high_tf_ready = self._check_tf_warmup(
                self._high_tf_buffer, self._high_tf_indicators
            )
        else:
            self._high_tf_ready = True  # Same as med_tf, already checked

        # All active TFs must be ready
        all_ready = self._low_tf_ready and self._med_tf_ready and self._high_tf_ready

        with self._buffer_lock:
            if not self._ready and all_ready:
                self._ready = True
                logger.info(
                    f"LiveDataProvider ready (warmup complete): "
                    f"low_tf={len(self._low_tf_buffer)}, "
                    f"med_tf={len(self._med_tf_buffer)}, "
                    f"high_tf={len(self._high_tf_buffer)} bars"
                )

    def _check_tf_warmup(
        self,
        buffer: list[Candle],
        indicator_cache: LiveIndicatorCache | None,
    ) -> bool:
        """
        WU-04: Check if a single TF is warmed up.

        A TF is ready when:
        1. Buffer has >= warmup_bars
        2. Indicators have valid (non-NaN) values at the latest bar

        Args:
            buffer: Candle buffer for this TF
            indicator_cache: Indicator cache for this TF (may be None)

        Returns:
            True if TF is warmed up, False otherwise
        """
        # Check bar count
        if len(buffer) < self._warmup_bars:
            return False

        # WU-04: Check for NaN in indicator values
        if indicator_cache is not None and indicator_cache.length > 0:
            # Check all indicators at the latest bar for NaN
            with indicator_cache._lock:
                for name, arr in indicator_cache._indicators.items():
                    if len(arr) > 0 and np.isnan(arr[-1]):
                        # Found NaN at latest bar - warmup not complete
                        logger.debug(
                            f"Indicator {name} has NaN at latest bar, warmup incomplete"
                        )
                        return False

        return True

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
        assert isinstance(timeframe, str)

        tf_role = self._get_tf_role_for_timeframe(timeframe)

        # Route to correct buffer and indicator cache
        if tf_role == "low_tf":
            self._update_tf_buffer(
                candle, self._low_tf_buffer, self._low_tf_indicators, self._low_tf_structure, tf_role
            )
        elif tf_role == "med_tf":
            self._update_tf_buffer(
                candle, self._med_tf_buffer, self._med_tf_indicators, self._med_tf_structure, tf_role
            )
        elif tf_role == "high_tf":
            self._update_tf_buffer(
                candle, self._high_tf_buffer, self._high_tf_indicators, self._high_tf_structure, tf_role
            )

        # WU-02, WU-04: Check warmup for all TFs with NaN validation
        if not self._ready:
            self._check_all_tf_warmup()

    def _get_tf_role_for_timeframe(self, timeframe: str) -> str:
        """Map a timeframe string to its TF role (low_tf, med_tf, high_tf)."""
        if timeframe == self._tf_mapping["low_tf"]:
            return "low_tf"
        elif timeframe == self._tf_mapping["med_tf"]:
            return "med_tf"
        elif timeframe == self._tf_mapping["high_tf"]:
            return "high_tf"
        raise ValueError(f"Unknown timeframe '{timeframe}' - valid TFs: {self._tf_mapping}")

    def _update_tf_buffer(
        self,
        candle: Candle,
        buffer: list[Candle],
        indicator_cache: LiveIndicatorCache | None,
        structure_state: "TFIncrementalState | None",
        tf_role: str = "low_tf",
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
            self._update_structure_state_for_tf(structure_state, buffer_len - 1, candle, tf_role)

    def _update_structure_state_for_tf(
        self,
        structure_state: "TFIncrementalState",
        bar_idx: int,
        candle: Candle,
        tf_role: str = "low_tf",
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
            # G16.3: Record all structure output values in history ring buffer
            self._record_structure_history(structure_state, tf_role, bar_idx)
        except Exception as e:
            logger.warning(f"Failed to update structure state: {e}")


    def _record_structure_history(
        self,
        structure_state: "TFIncrementalState",
        tf_role: str,
        bar_idx: int,
    ) -> None:
        """G16.3: Record all structure output values in history ring buffer."""
        for struct_key in structure_state.list_structures():
            for field in structure_state.list_outputs(struct_key):
                try:
                    value = structure_state.get_value(struct_key, field)
                except (KeyError, RuntimeError):
                    continue
                buf_key = (tf_role, struct_key, field)
                if buf_key not in self._structure_history:
                    self._structure_history[buf_key] = deque(maxlen=500)
                self._structure_history[buf_key].append((bar_idx, value))


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
        self._start_ms: int = int(datetime.now(timezone.utc).timestamp() * 1000)

        logger.info(
            f"LiveExchange initialized: {self._symbol} demo={demo}"
        )

    def _is_ws_data_fresh(self, max_age_s: float = 60.0) -> bool:
        """Check if WebSocket data is fresh enough to trust."""
        if not self._realtime_state:
            return False
        last_update = getattr(self._realtime_state, '_last_update_ts', None)
        if last_update is None:
            return True  # No timestamp tracking, assume fresh
        age = (datetime.now(timezone.utc) - last_update).total_seconds()
        return age < max_age_s

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
        assert account is not None, "Play.account is required for live trading"

        # G6.0.1: Use SizingConfig max_position_equity_pct (default 95%)
        # The PlayEngineConfig doesn't have max_position_pct - use default
        max_position_pct = 95.0  # SizingConfig default
        config.max_position_size_usdt = account.starting_equity_usdt * (
            max_position_pct / 100.0
        )

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
            # Extract original Signal from Order metadata if available
            # (PlayEngine.execute_signal stores it as order.metadata["signal"])
            original_signal = order.metadata.get("signal") if order.metadata else None

            # Preserve strategy and confidence from original signal
            strategy = (
                original_signal.strategy
                if original_signal and hasattr(original_signal, "strategy")
                else (self._play.name or self._play.id)
            )
            confidence = (
                original_signal.confidence
                if original_signal and hasattr(original_signal, "confidence")
                else 1.0
            )

            # Build metadata preserving original signal fields
            signal_metadata = {}
            if original_signal and hasattr(original_signal, "metadata") and original_signal.metadata:
                signal_metadata.update(original_signal.metadata)
            # Ensure stop_loss/take_profit are in metadata for downstream consumers
            if order.stop_loss is not None:
                signal_metadata["stop_loss"] = order.stop_loss
            if order.take_profit is not None:
                signal_metadata["take_profit"] = order.take_profit
            if order.order_type:
                signal_metadata["order_type"] = order.order_type.lower()
            if order.limit_price is not None:
                signal_metadata["limit_price"] = order.limit_price

            # Convert unified Order to Signal format (only valid Signal fields)
            signal = Signal(
                symbol=order.symbol,
                direction=self._order_side_to_direction(order.side),
                size_usdt=order.size_usdt,
                strategy=strategy,
                confidence=confidence,
                metadata=signal_metadata,
            )

            # Execute through OrderExecutor
            exec_result = self._order_executor.execute(signal)

            # Convert to unified OrderResult
            # Build risk_check metadata (RiskCheckResult has no to_dict)
            risk_meta = None
            if exec_result.risk_check:
                rc = exec_result.risk_check
                risk_meta = {
                    "allowed": rc.allowed,
                    "reason": rc.reason,
                    "adjusted_size": rc.adjusted_size,
                }

            return OrderResult(
                success=exec_result.success,
                order_id=exec_result.order_result.order_id if exec_result.order_result else None,
                exchange_order_id=exec_result.order_result.order_id if exec_result.order_result else None,
                fill_price=exec_result.order_result.price if exec_result.order_result else None,
                fill_usdt=exec_result.executed_size,
                fee_usdt=getattr(exec_result, 'fee_usdt', None),
                error=exec_result.error,
                metadata={
                    "risk_check": risk_meta,
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
        """Convert order side to direction string.

        OrderExecutor expects uppercase: LONG, SHORT, FLAT.
        """
        side_upper = side.upper()
        if side_upper in ("LONG", "BUY"):
            return "LONG"
        elif side_upper in ("SHORT", "SELL"):
            return "SHORT"
        elif side_upper in ("FLAT", "CLOSE"):
            return "FLAT"
        return side_upper

    def cancel_order(self, order_id: str) -> bool:
        """Cancel pending order."""
        if self._exchange_manager is None:
            return False

        try:
            result = self._exchange_manager.cancel_order(
                symbol=self._symbol,
                order_id=order_id,
            )
            return bool(result)
        except Exception as e:
            logger.error(f"Cancel order failed: {e}")
            return False

    def get_position(self, symbol: str) -> Position | None:
        """Get current position."""
        # Try RealtimeState first (WebSocket-fed) if data is fresh
        if self._realtime_state and self._is_ws_data_fresh():
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
        # PM returns core Position (fields: size, current_price) not interfaces.Position (size_qty, mark_price)
        if self._position_manager:
            pm_pos = self._position_manager.get_position(symbol)
            if pm_pos:
                raw_side = pm_pos.side.upper()
                pos_side: Literal["LONG", "SHORT"] = "LONG" if raw_side == "LONG" else "SHORT"
                return Position(
                    symbol=pm_pos.symbol,
                    side=pos_side,
                    size_usdt=pm_pos.size_usdt,
                    size_qty=pm_pos.size,
                    entry_price=pm_pos.entry_price,
                    mark_price=pm_pos.current_price,
                    unrealized_pnl=pm_pos.unrealized_pnl,
                    leverage=pm_pos.leverage,
                    stop_loss=pm_pos.stop_loss,
                    take_profit=pm_pos.take_profit,
                    liquidation_price=pm_pos.liquidation_price,
                )

        return None

    def get_balance(self) -> float:
        """Get available balance."""
        # Try RealtimeState first if data is fresh
        if self._realtime_state and self._is_ws_data_fresh():
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
                return balance["available"] if balance else self._config.initial_equity
            except Exception as e:
                logger.error(f"Failed to get available balance from exchange, using initial equity: {e}")

        return self._config.initial_equity

    def get_equity(self) -> float:
        """Get total equity."""
        # Try RealtimeState first if data is fresh
        if self._realtime_state and self._is_ws_data_fresh():
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
                return balance["total"] if balance else self._config.initial_equity
            except Exception as e:
                logger.error(f"Failed to get equity from exchange, using initial equity: {e}")

        return self._config.initial_equity

    def get_realized_pnl(self) -> float:
        """Get total realized PnL from Bybit closed PnL endpoint."""
        if self._exchange_manager is None:
            return 0.0
        try:
            now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
            time_range = TimeRange(
                start_ms=self._start_ms,
                end_ms=now_ms,
                label="engine_session",
                endpoint_type="closed_pnl",
            )
            records = self._exchange_manager.get_closed_pnl(
                time_range=time_range, symbol=self._symbol,
            )
            return sum(float(r.get("closedPnl", 0)) for r in records)
        except Exception as e:
            logger.warning(f"Failed to query realized PnL from exchange: {e}")
            return 0.0

    def get_pending_orders(self, symbol: str | None = None) -> list[Order]:
        """Get pending orders."""
        orders = []

        # Try RealtimeState first
        if self._realtime_state:
            open_orders = self._realtime_state.get_open_orders(symbol)
            for order_data in open_orders:
                od_side: Literal["LONG", "SHORT"] = "LONG" if order_data.side.lower() == "buy" else "SHORT"
                raw_otype = order_data.order_type.upper()
                od_otype: Literal["MARKET", "LIMIT", "STOP_MARKET", "STOP_LIMIT"] = (
                    "LIMIT" if raw_otype == "LIMIT"
                    else "STOP_MARKET" if raw_otype == "STOP_MARKET"
                    else "STOP_LIMIT" if raw_otype == "STOP_LIMIT"
                    else "MARKET"
                )
                orders.append(Order(
                    symbol=order_data.symbol,
                    side=od_side,
                    size_usdt=order_data.price * order_data.qty,
                    order_type=od_otype,
                    limit_price=order_data.price if order_data.order_type.lower() == "limit" else None,
                    client_order_id=order_data.order_id,
                ))
            return orders

        # Fall back to REST
        if self._exchange_manager:
            try:
                rest_orders = self._exchange_manager.get_open_orders(symbol)
                for od in rest_orders:
                    rest_side: Literal["LONG", "SHORT"] = "LONG" if od.side.lower() == "buy" else "SHORT"
                    raw_rt = od.order_type.upper()
                    rest_otype: Literal["MARKET", "LIMIT", "STOP_MARKET", "STOP_LIMIT"] = (
                        "LIMIT" if raw_rt == "LIMIT"
                        else "STOP_MARKET" if raw_rt == "STOP_MARKET"
                        else "STOP_LIMIT" if raw_rt == "STOP_LIMIT"
                        else "MARKET"
                    )
                    orders.append(Order(
                        symbol=od.symbol,
                        side=rest_side,
                        size_usdt=float((od.price or 0.0) * od.qty),
                        order_type=rest_otype,
                        limit_price=od.price,
                        client_order_id=od.order_id,
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
            result = self._exchange_manager.close_position(
                symbol=self._symbol,
            )

            if result and result.success:
                logger.info(
                    f"Close order submitted: order_id={result.order_id} "
                    f"(PnL tracked by exchange)"
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
