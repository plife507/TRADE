"""
Live adapters for PlayEngine.

These adapters connect to real exchange infrastructure:
- LiveDataProvider: WebSocket data + indicator cache
- LiveExchange: OrderExecutor + PositionManager

Integrates with existing RealtimeState/RealtimeBootstrap infrastructure.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

import numpy as np

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
                        # Initialize with historical data
                        self._indicators[feature.indicator_id] = np.full(n, np.nan)
                        for i in range(n):
                            if ind_type in ("atr",):
                                inc_ind.update(
                                    high=self._high[i],
                                    low=self._low[i],
                                    close=self._close[i],
                                )
                            else:
                                inc_ind.update(close=self._close[i])
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
        """
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
        for name, (inc_ind, feature) in self._incremental.items():
            ind_type = feature.indicator_type.lower()
            if ind_type in ("atr",):
                inc_ind.update(
                    high=float(candle.high),
                    low=float(candle.low),
                    close=float(candle.close),
                )
            else:
                inc_ind.update(close=float(candle.close))

            # Append new value
            self._indicators[name] = np.append(self._indicators[name], inc_ind.value)

        # Recompute vectorized indicators (still O(n) but only for non-incremental)
        if self._vectorized_specs:
            self._compute_vectorized()

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
        """Get indicator value at index."""
        if name not in self._indicators:
            raise KeyError(f"Indicator '{name}' not found")

        arr = self._indicators[name]
        if index < 0:
            index = len(arr) + index

        if index < 0 or index >= len(arr):
            raise IndexError(f"Index {index} out of bounds")

        return float(arr[index])

    def has_indicator(self, name: str) -> bool:
        """Check if indicator exists."""
        return name in self._indicators

    @property
    def length(self) -> int:
        """Number of bars in cache."""
        return self._bar_count


class LiveDataProvider:
    """
    DataProvider that uses WebSocket streams and indicator cache.

    Provides real-time access to:
    - Live candles from WebSocket via RealtimeState
    - Incrementally computed indicators via LiveIndicatorCache
    - Structure state (swing, trend, zones) via TFIncrementalState

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
        self._timeframe = play.execution_tf

        # RealtimeState integration (set during connect)
        self._realtime_state: "RealtimeState | None" = None
        self._bootstrap: "RealtimeBootstrap | None" = None

        # Indicator cache
        self._indicator_cache = LiveIndicatorCache(play)

        # Structure state (incremental detection)
        self._structure_state: "TFIncrementalState | None" = None

        # Candle buffer (use BarRecord from RealtimeState)
        self._candle_buffer: list[Candle] = []
        self._buffer_size = 500

        # Tracking
        self._ready = False
        self._warmup_bars = 100  # Minimum bars before ready
        self._current_bar_index: int = -1

        # Environment for MTF buffer lookup
        self._env = "demo" if demo else "live"

        logger.info(
            f"LiveDataProvider initialized: {self._symbol} {self._timeframe} "
            f"env={self._env}"
        )

    @property
    def num_bars(self) -> int:
        """Number of bars in buffer."""
        return len(self._candle_buffer)

    @property
    def symbol(self) -> str:
        return self._symbol

    @property
    def timeframe(self) -> str:
        return self._timeframe

    @property
    def current_bar_index(self) -> int:
        """Current bar index for structure access."""
        return self._current_bar_index

    @current_bar_index.setter
    def current_bar_index(self, value: int) -> None:
        """Set current bar index (called by runner each bar)."""
        self._current_bar_index = value

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
        """Load initial bars from bar buffer, DuckDB, or REST API."""
        if self._realtime_state is None:
            return

        # Try to get from bar buffer first (hot in-memory cache)
        bars = self._realtime_state.get_bar_buffer(
            env=self._env,
            symbol=self._symbol,
            timeframe=self._timeframe,
            limit=self._buffer_size,
        )

        # Fall back to DuckDB if bar buffer is empty
        if not bars:
            bars = await self._load_bars_from_db()

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
                self._candle_buffer.append(candle)

            # Initialize indicators from historical data
            self._indicator_cache.initialize_from_history(
                bars,
                self._play.features if self._play.features else [],
            )

            logger.info(f"Loaded {len(bars)} bars for warm-up")

        # Initialize structure state if Play has structures
        if self._play.structures:
            self._init_structure_state()

        # Check warmup
        if len(self._candle_buffer) >= self._warmup_bars:
            self._ready = True
            logger.info("LiveDataProvider ready (warmup complete)")

    async def _load_bars_from_db(self) -> list:
        """
        Load bars from DuckDB for warm-up.

        Fallback when in-memory buffer is empty (e.g., bot restart).
        """
        from ...data.historical_data_store import get_historical_store
        from ...data.realtime_state import BarRecord
        from datetime import datetime, timedelta

        try:
            store = get_historical_store(env=self._env)

            # Calculate time range (last N bars based on timeframe)
            end = datetime.utcnow()
            tf_minutes = self._parse_timeframe_minutes(self._timeframe)
            start = end - timedelta(minutes=tf_minutes * self._buffer_size)

            # Query DuckDB
            df = store.query_ohlcv(
                symbol=self._symbol,
                timeframe=self._timeframe,
                start=start,
                end=end,
            )

            if df is None or df.empty:
                logger.info(f"No bars in DuckDB for {self._symbol} {self._timeframe}")
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

            logger.info(f"Loaded {len(bars)} bars from DuckDB ({self._env})")
            return bars

        except Exception as e:
            logger.warning(f"Failed to load bars from DuckDB: {e}")
            return []

    def _parse_timeframe_minutes(self, tf: str) -> int:
        """Parse timeframe string to minutes."""
        tf_map = {
            "1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
            "1h": 60, "2h": 120, "4h": 240, "6h": 360, "12h": 720,
            "D": 1440, "W": 10080, "M": 43200,
        }
        return tf_map.get(tf, 60)  # Default to 1h

    def _init_structure_state(self) -> None:
        """Initialize incremental structure state from Play specs."""
        from src.structures import TFIncrementalState

        if not self._play.structures:
            return

        # Get exec TF structures
        exec_specs = self._play.structures.get("exec", [])
        if exec_specs:
            try:
                self._structure_state = TFIncrementalState(
                    self._timeframe,
                    exec_specs,
                )
                logger.info(f"Initialized structure state with {len(exec_specs)} specs")
            except Exception as e:
                logger.warning(f"Failed to initialize structure state: {e}")

    def get_candle(self, index: int) -> Candle:
        """
        Get candle at index.

        Args:
            index: Negative index for live (-1 = latest, -2 = previous, etc.)

        Returns:
            Candle data
        """
        if not self._candle_buffer:
            raise RuntimeError("No candles in buffer. Is WebSocket connected?")

        # Support both positive (backtest-style) and negative (live-style) indexing
        if index < 0:
            # Live-style: -1 = latest
            actual_idx = index
        else:
            # Backtest-style: positive index
            actual_idx = index

        if abs(actual_idx) > len(self._candle_buffer) if actual_idx < 0 else actual_idx >= len(self._candle_buffer):
            raise IndexError(f"Index {index} out of buffer bounds (buffer size: {len(self._candle_buffer)})")

        return self._candle_buffer[actual_idx]

    def get_indicator(self, name: str, index: int) -> float:
        """Get indicator value at index."""
        return self._indicator_cache.get(name, index)

    def get_structure(self, key: str, field: str) -> float:
        """Get current structure field value."""
        if self._structure_state is None:
            raise RuntimeError("Structure state not initialized")

        return self._structure_state.get_value(key, field)

    def get_structure_at(self, key: str, field: str, index: int) -> float:
        """Get structure field at specific index."""
        if self._structure_state is None:
            raise RuntimeError("Structure state not initialized")

        # For now, just return current value (full history not tracked in live)
        # P3: Track structure history for lookback (ring buffer per structure field)
        return self._structure_state.get_value(key, field)

    def has_indicator(self, name: str) -> bool:
        """Check if indicator exists."""
        return self._indicator_cache.has_indicator(name)

    def is_ready(self) -> bool:
        """Check if data provider is ready."""
        return self._ready

    def on_candle_close(self, candle: Candle) -> None:
        """
        Called when a new candle closes.

        Updates buffer, computes indicators, updates structures.
        """
        # Add to buffer
        self._candle_buffer.append(candle)

        # Trim buffer if needed
        if len(self._candle_buffer) > self._buffer_size:
            self._candle_buffer = self._candle_buffer[-self._buffer_size:]

        # Update indicators
        self._indicator_cache.update(candle)

        # Update structure state
        if self._structure_state is not None:
            self._update_structure_state(len(self._candle_buffer) - 1)

        # Check warmup
        if not self._ready and len(self._candle_buffer) >= self._warmup_bars:
            self._ready = True
            logger.info("LiveDataProvider ready (warmup complete)")

    def _update_structure_state(self, bar_idx: int) -> None:
        """Update structure state with latest candle."""
        if self._structure_state is None:
            return

        from src.structures import BarData

        candle = self._candle_buffer[-1]

        # Get indicator values for structure computation
        indicator_values: dict[str, float] = {}
        for name in self._indicator_cache._indicators.keys():
            try:
                val = self._indicator_cache.get(name, -1)
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
            self._structure_state.update(bar_data)
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
            risk_config = self._build_risk_config()
            self._risk_manager = RiskManager(
                position_manager=self._position_manager,
                config=risk_config,
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

        config.max_position_value = account.starting_equity_usdt * (
            self._config.max_position_pct / 100.0
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

    @property
    def has_position(self) -> bool:
        """Check if there's an open position."""
        pos = self.get_position(self._symbol)
        return pos is not None

    @property
    def is_connected(self) -> bool:
        """Check if connected to exchange."""
        return self._connected
