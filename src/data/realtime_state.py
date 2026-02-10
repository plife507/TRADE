"""
Real-time state management for WebSocket-driven data.

This module provides a thread-safe, centralized store for real-time market
and account data received via WebSocket streams. It serves as the single
source of truth for live data across the trading system.

Architecture:
- Domain models: Normalized event and state types (in realtime_models.py)
- State containers: Thread-safe storage for each data type
- RealtimeState: Central manager that coordinates all state updates
- Event queue: Optional queue for event-driven processing

Usage:
    from src.data.realtime_state import get_realtime_state
    
    state = get_realtime_state()
    
    # Read current data
    ticker = state.get_ticker("BTCUSDT")
    positions = state.get_positions()
    
    # Check staleness
    if state.is_ticker_stale("BTCUSDT", max_age_seconds=5):
        # Fall back to REST
        pass
"""

import time
import threading
from collections.abc import Callable
from collections import defaultdict, deque
from queue import Queue, Empty
from typing import Any

import pandas as pd

from ..utils.logger import get_logger
from ..config.constants import DataEnv, validate_data_env

# Import all models from realtime_models
from .realtime_models import (
    # Enums
    EventType,
    ConnectionState,
    STALENESS_THRESHOLDS,
    # Market data models
    TickerData,
    OrderbookLevel,
    OrderbookData,
    TradeData,
    KlineData,
    BarRecord,
    BAR_BUFFER_SIZES,
    get_bar_buffer_size,
    # Account data models
    PositionData,
    OrderData,
    ExecutionData,
    WalletData,
    AccountMetrics,
    PortfolioRiskSnapshot,
    # Utility classes
    RealtimeEvent,
    ConnectionStatus,
)

__all__ = [
    # Main class
    "RealtimeState",
    "get_realtime_state",
    "reset_realtime_state",
    # Enums
    "EventType",
    "ConnectionState",
    "STALENESS_THRESHOLDS",
    # Market data models
    "TickerData",
    "OrderbookLevel",
    "OrderbookData",
    "TradeData",
    "KlineData",
    "BarRecord",
    "BAR_BUFFER_SIZES",
    "get_bar_buffer_size",
    # Account data models
    "PositionData",
    "OrderData",
    "ExecutionData",
    "WalletData",
    "AccountMetrics",
    "PortfolioRiskSnapshot",
    # Utility classes
    "RealtimeEvent",
    "ConnectionStatus",
]


class RealtimeState:
    """
    Thread-safe centralized state manager for real-time data.
    
    This is the single source of truth for all WebSocket-delivered data.
    It provides:
    - Thread-safe read/write access to all state
    - Staleness detection for all data types
    - Event queue for event-driven processing
    - Connection status tracking
    - Callbacks for state changes
    
    Usage:
        state = RealtimeState()
        
        # Update from WebSocket callback
        state.update_ticker(TickerData.from_bybit(msg["data"]))
        
        # Read current state
        ticker = state.get_ticker("BTCUSDT")
        
        # Check staleness
        if state.is_ticker_stale("BTCUSDT"):
            # Fall back to REST
            pass
        
        # Register callbacks
        state.on_ticker_update(lambda t: print(f"New price: {t.last_price}"))
    """
    
    def __init__(self, enable_event_queue: bool = True):
        """
        Initialize realtime state manager.
        
        Args:
            enable_event_queue: Enable event queue for event-driven processing
        """
        self.logger = get_logger()
        
        # Locks for thread-safety
        self._lock = threading.RLock()
        self._callback_lock = threading.Lock()
        
        # Public market data state
        self._tickers: dict[str, TickerData] = {}
        self._orderbooks: dict[str, OrderbookData] = {}
        self._klines: dict[str, dict[str, KlineData]] = defaultdict(dict)  # {symbol: {interval: kline}}
        self._recent_trades: dict[str, deque[TradeData]] = defaultdict(lambda: deque(maxlen=100))

        # Private account data state
        self._positions: dict[str, PositionData] = {}  # {symbol: position}
        self._orders: dict[str, OrderData] = {}  # {order_id: order}
        self._executions: deque[ExecutionData] = deque(maxlen=500)
        self._wallet: dict[str, WalletData] = {}  # {coin: wallet}
        self._account_metrics: AccountMetrics | None = None  # Unified account-level metrics
        
        # Connection status
        self._public_ws_status = ConnectionStatus()
        self._private_ws_status = ConnectionStatus()
        
        self._event_queue_enabled = enable_event_queue
        self._event_queue: Queue = Queue(maxsize=10000) if enable_event_queue else None
        
        # Callbacks
        self._ticker_callbacks: list[Callable[[TickerData], None]] = []
        self._orderbook_callbacks: list[Callable[[OrderbookData], None]] = []
        self._trade_callbacks: list[Callable[[TradeData], None]] = []
        self._kline_callbacks: list[Callable[[KlineData], None]] = []
        self._position_callbacks: list[Callable[[PositionData], None]] = []
        self._order_callbacks: list[Callable[[OrderData], None]] = []
        self._execution_callbacks: list[Callable[[ExecutionData], None]] = []
        self._wallet_callbacks: list[Callable[[WalletData], None]] = []
        self._account_metrics_callbacks: list[Callable[[AccountMetrics], None]] = []

        # Stats
        self._update_counts: dict[str, int] = defaultdict(int)
        self._started_at = time.time()
        
        # Configuration
        self._max_recent_trades = 100
        self._max_executions = 500
        
        # ==============================================================================
        # Bar Buffers - Environment-scoped bar storage for any timeframe
        # ==============================================================================
        # Structure: env -> symbol -> timeframe -> deque[BarRecord]
        # Used for strategy warm-up and lookback during live execution
        self._bar_buffers: dict[str, dict[str, dict[str, deque[BarRecord]]]] = {
            "live": defaultdict(lambda: defaultdict(deque)),
            "demo": defaultdict(lambda: defaultdict(deque)),
        }
    
    # ==========================================================================
    # Public Data - Tickers
    # ==========================================================================
    
    def update_ticker(self, ticker: TickerData):
        """Update ticker state (thread-safe)."""
        with self._lock:
            self._tickers[ticker.symbol] = ticker
            self._update_counts["ticker"] += 1
        
        self._emit_event(EventType.TICKER_UPDATE, ticker, ticker.symbol)
        self._invoke_callbacks(self._ticker_callbacks, ticker)
    
    def get_ticker(self, symbol: str) -> TickerData | None:
        """Get ticker for a symbol (thread-safe)."""
        with self._lock:
            return self._tickers.get(symbol)

    def get_all_tickers(self) -> dict[str, TickerData]:
        """Get all tickers (thread-safe copy)."""
        with self._lock:
            return dict(self._tickers)
    
    def is_ticker_stale(self, symbol: str, max_age_seconds: float | None = None) -> bool:
        """Check if ticker is stale."""
        max_age = max_age_seconds or STALENESS_THRESHOLDS["ticker"]
        with self._lock:
            ticker = self._tickers.get(symbol)
            if not ticker:
                return True
            return (time.time() - ticker.timestamp) > max_age
    
    def on_ticker_update(self, callback: Callable[[TickerData], None]):
        """Register callback for ticker updates."""
        with self._callback_lock:
            self._ticker_callbacks.append(callback)
    
    # ==========================================================================
    # Public Data - Orderbooks
    # ==========================================================================
    
    def update_orderbook(self, orderbook: OrderbookData, is_snapshot: bool = True):
        """Update orderbook state (thread-safe)."""
        with self._lock:
            if is_snapshot:
                self._orderbooks[orderbook.symbol] = orderbook
            else:
                # Apply delta to existing orderbook
                existing = self._orderbooks.get(orderbook.symbol)
                if existing:
                    existing.apply_delta({
                        "b": [[l.price, l.size] for l in orderbook.bids],
                        "a": [[l.price, l.size] for l in orderbook.asks],
                        "u": orderbook.update_id,
                    })
                else:
                    self._orderbooks[orderbook.symbol] = orderbook
            
            self._update_counts["orderbook"] += 1
        
        event_type = EventType.ORDERBOOK_SNAPSHOT if is_snapshot else EventType.ORDERBOOK_DELTA
        self._emit_event(event_type, orderbook, orderbook.symbol)
        self._invoke_callbacks(self._orderbook_callbacks, self._orderbooks.get(orderbook.symbol))
    
    def apply_orderbook_delta(self, symbol: str, delta: dict):
        """Apply delta update to orderbook."""
        with self._lock:
            existing = self._orderbooks.get(symbol)
            if existing:
                existing.apply_delta(delta)
                self._update_counts["orderbook"] += 1
                self._emit_event(EventType.ORDERBOOK_DELTA, existing, symbol)
                self._invoke_callbacks(self._orderbook_callbacks, existing)
    
    def get_orderbook(self, symbol: str) -> OrderbookData | None:
        """Get orderbook for a symbol (thread-safe)."""
        with self._lock:
            return self._orderbooks.get(symbol)
    
    def is_orderbook_stale(self, symbol: str, max_age_seconds: float | None = None) -> bool:
        """Check if orderbook is stale."""
        max_age = max_age_seconds or STALENESS_THRESHOLDS["orderbook"]
        with self._lock:
            ob = self._orderbooks.get(symbol)
            if not ob:
                return True
            return (time.time() - ob.timestamp) > max_age
    
    def on_orderbook_update(self, callback: Callable[[OrderbookData], None]):
        """Register callback for orderbook updates."""
        with self._callback_lock:
            self._orderbook_callbacks.append(callback)
    
    # ==========================================================================
    # Public Data - Klines
    # ==========================================================================
    
    def update_kline(self, kline: KlineData):
        """Update kline state (thread-safe)."""
        with self._lock:
            self._klines[kline.symbol][kline.interval] = kline
            self._update_counts["kline"] += 1
        
        event_type = EventType.KLINE_CLOSED if kline.is_closed else EventType.KLINE_UPDATE
        self._emit_event(event_type, kline, kline.symbol)
        self._invoke_callbacks(self._kline_callbacks, kline)
    
    def get_kline(self, symbol: str, interval: str) -> KlineData | None:
        """Get latest kline for symbol and interval."""
        with self._lock:
            return self._klines.get(symbol, {}).get(interval)

    def get_all_klines(self, symbol: str) -> dict[str, KlineData]:
        """Get all klines for a symbol."""
        with self._lock:
            return dict(self._klines.get(symbol, {}))
    
    def is_kline_stale(self, symbol: str, interval: str, max_age_seconds: float | None = None) -> bool:
        """Check if kline is stale."""
        max_age = max_age_seconds or STALENESS_THRESHOLDS["kline"]
        with self._lock:
            kline = self._klines.get(symbol, {}).get(interval)
            if not kline:
                return True
            return (time.time() - kline.timestamp) > max_age
    
    def on_kline_update(self, callback: Callable[[KlineData], None]):
        """Register callback for kline updates."""
        with self._callback_lock:
            self._kline_callbacks.append(callback)
    
    # ==========================================================================
    # Bar Buffers - Environment-scoped bar storage for any timeframe
    # ==========================================================================

    def init_bar_buffer(
        self,
        env: DataEnv,
        symbol: str,
        timeframe: str,
        bars_df: pd.DataFrame,
        max_size: int | None = None,
    ) -> int:
        """
        Initialize a bar ring buffer from historical DataFrame.

        Args:
            env: Data environment ("live" or "demo")
            symbol: Trading symbol (e.g., "BTCUSDT")
            timeframe: Bar timeframe (e.g., "15m", "1h", "4h")
            bars_df: DataFrame with OHLCV data
            max_size: Maximum buffer size (default: auto-sized based on timeframe)

        Returns:
            Number of bars loaded into the buffer
        """
        env = validate_data_env(env)
        symbol = symbol.upper()

        if max_size is None:
            max_size = get_bar_buffer_size(timeframe)

        with self._lock:
            buffer: deque[BarRecord] = deque(maxlen=max_size)

            count = 0
            for _, row in bars_df.iterrows():
                try:
                    bar = BarRecord.from_df_row(row)
                    buffer.append(bar)
                    count += 1
                except (KeyError, ValueError, TypeError) as e:
                    self.logger.debug(f"Skipping malformed row in bar buffer init: {e}")
                    continue

            self._bar_buffers[env][symbol][timeframe] = buffer

            self.logger.debug(
                f"Initialized bar buffer: env={env}, symbol={symbol}, "
                f"tf={timeframe}, bars={count}, max_size={max_size}"
            )

            return count

    def append_bar(
        self,
        env: DataEnv,
        symbol: str,
        timeframe: str,
        bar: BarRecord,
    ) -> bool:
        """Append a closed bar to a ring buffer."""
        env = validate_data_env(env)
        symbol = symbol.upper()

        with self._lock:
            if symbol not in self._bar_buffers[env]:
                return False
            if timeframe not in self._bar_buffers[env][symbol]:
                return False

            buffer = self._bar_buffers[env][symbol][timeframe]
            buffer.append(bar)

            return True

    def get_bar_buffer(
        self,
        env: DataEnv,
        symbol: str,
        timeframe: str,
        limit: int | None = None,
    ) -> list[BarRecord]:
        """Get bars from a ring buffer."""
        env = validate_data_env(env)
        symbol = symbol.upper()

        with self._lock:
            if symbol not in self._bar_buffers[env]:
                return []
            if timeframe not in self._bar_buffers[env][symbol]:
                return []

            buffer = self._bar_buffers[env][symbol][timeframe]

            if limit is None:
                return list(buffer)
            else:
                return list(buffer)[-limit:]

    def get_bar_buffer_as_df(
        self,
        env: DataEnv,
        symbol: str,
        timeframe: str,
        limit: int | None = None,
    ) -> pd.DataFrame:
        """Get bar buffer as a pandas DataFrame (OHLCV format)."""
        bars = self.get_bar_buffer(env, symbol, timeframe, limit)

        if not bars:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        data = [
            {
                "timestamp": b.timestamp,
                "open": b.open, "high": b.high, "low": b.low,
                "close": b.close, "volume": b.volume,
            }
            for b in bars
        ]

        return pd.DataFrame(data)

    def get_bar_buffer_stats(self, env: DataEnv | None = None) -> dict[str, Any]:
        """Get statistics about bar buffers."""
        with self._lock:
            stats = {}
            envs = [env] if env else ["live", "demo"]

            for e in envs:
                stats[e] = {}
                for symbol, tf_buffers in self._bar_buffers[e].items():
                    stats[e][symbol] = {}
                    for tf, buffer in tf_buffers.items():
                        if len(buffer) > 0:
                            stats[e][symbol][tf] = {
                                "count": len(buffer),
                                "max_size": buffer.maxlen,
                                "oldest": buffer[0].timestamp.isoformat() if buffer else None,
                                "newest": buffer[-1].timestamp.isoformat() if buffer else None,
                            }

            return stats

    def clear_bar_buffers(self, env: DataEnv | None = None, symbol: str | None = None):
        """Clear bar buffers."""
        with self._lock:
            if env is None:
                self._bar_buffers = {
                    "live": defaultdict(lambda: defaultdict(deque)),
                    "demo": defaultdict(lambda: defaultdict(deque)),
                }
            elif symbol is None:
                self._bar_buffers[env] = defaultdict(lambda: defaultdict(deque))
            else:
                symbol = symbol.upper()
                if symbol in self._bar_buffers[env]:
                    del self._bar_buffers[env][symbol]
    
    # ==========================================================================
    # Public Data - Trades
    # ==========================================================================
    
    def add_trade(self, trade: TradeData):
        """Add a public trade (thread-safe)."""
        with self._lock:
            self._recent_trades[trade.symbol].append(trade)
            self._update_counts["trade"] += 1
        
        self._emit_event(EventType.TRADE, trade, trade.symbol)
        self._invoke_callbacks(self._trade_callbacks, trade)
    
    def get_recent_trades(self, symbol: str, limit: int = 50) -> list[TradeData]:
        """Get recent trades for a symbol."""
        with self._lock:
            trades = self._recent_trades.get(symbol, [])
            return list(trades[-limit:])
    
    def on_trade(self, callback: Callable[[TradeData], None]):
        """Register callback for trades."""
        with self._callback_lock:
            self._trade_callbacks.append(callback)
    
    # ==========================================================================
    # Private Data - Positions
    # ==========================================================================
    
    def update_position(self, position: PositionData):
        """Update position state (thread-safe)."""
        with self._lock:
            if position.is_open:
                self._positions[position.symbol] = position
            else:
                self._positions.pop(position.symbol, None)
            self._update_counts["position"] += 1
        
        self._emit_event(EventType.POSITION_UPDATE, position, position.symbol)
        self._invoke_callbacks(self._position_callbacks, position)
    
    def get_position(self, symbol: str) -> PositionData | None:
        """Get position for a symbol."""
        with self._lock:
            return self._positions.get(symbol)

    def get_all_positions(self) -> dict[str, PositionData]:
        """Get all open positions."""
        with self._lock:
            return dict(self._positions)
    
    def is_position_stale(self, symbol: str, max_age_seconds: float | None = None) -> bool:
        """Check if position data is stale."""
        max_age = max_age_seconds or STALENESS_THRESHOLDS["position"]
        with self._lock:
            pos = self._positions.get(symbol)
            if not pos:
                return True
            return (time.time() - pos.timestamp) > max_age
    
    def on_position_update(self, callback: Callable[[PositionData], None]):
        """Register callback for position updates."""
        with self._callback_lock:
            self._position_callbacks.append(callback)
    
    # ==========================================================================
    # Private Data - Orders
    # ==========================================================================
    
    def update_order(self, order: OrderData):
        """Update order state (thread-safe)."""
        with self._lock:
            if order.is_open:
                self._orders[order.order_id] = order
            else:
                self._orders.pop(order.order_id, None)
            self._update_counts["order"] += 1
        
        self._emit_event(EventType.ORDER_UPDATE, order, order.symbol)
        self._invoke_callbacks(self._order_callbacks, order)
    
    def get_order(self, order_id: str) -> OrderData | None:
        """Get order by ID."""
        with self._lock:
            return self._orders.get(order_id)

    def get_open_orders(self, symbol: str | None = None) -> list[OrderData]:
        """Get open orders, optionally filtered by symbol."""
        with self._lock:
            orders = list(self._orders.values())
            if symbol:
                orders = [o for o in orders if o.symbol == symbol]
            return orders
    
    def on_order_update(self, callback: Callable[[OrderData], None]):
        """Register callback for order updates."""
        with self._callback_lock:
            self._order_callbacks.append(callback)
    
    # ==========================================================================
    # Private Data - Executions
    # ==========================================================================
    
    def add_execution(self, execution: ExecutionData):
        """Add an execution (thread-safe)."""
        with self._lock:
            self._executions.append(execution)
            self._update_counts["execution"] += 1
        
        self._emit_event(EventType.EXECUTION, execution, execution.symbol)
        self._invoke_callbacks(self._execution_callbacks, execution)
    
    def get_recent_executions(self, symbol: str | None = None, limit: int = 50) -> list[ExecutionData]:
        """Get recent executions, optionally filtered by symbol."""
        with self._lock:
            execs = list(self._executions)
            if symbol:
                execs = [e for e in execs if e.symbol == symbol]
            return execs[-limit:]
    
    def on_execution(self, callback: Callable[[ExecutionData], None]):
        """Register callback for executions."""
        with self._callback_lock:
            self._execution_callbacks.append(callback)
    
    # ==========================================================================
    # Private Data - Wallet
    # ==========================================================================
    
    def update_wallet(self, wallet: WalletData):
        """Update wallet state (thread-safe)."""
        with self._lock:
            self._wallet[wallet.coin] = wallet
            self._update_counts["wallet"] += 1
        
        self._emit_event(EventType.WALLET_UPDATE, wallet, wallet.coin)
        self._invoke_callbacks(self._wallet_callbacks, wallet)
    
    def get_wallet(self, coin: str = "USDT") -> WalletData | None:
        """Get wallet for a coin."""
        with self._lock:
            return self._wallet.get(coin)

    def get_all_wallets(self) -> dict[str, WalletData]:
        """Get all wallet balances."""
        with self._lock:
            return dict(self._wallet)
    
    def is_wallet_stale(self, coin: str = "USDT", max_age_seconds: float | None = None) -> bool:
        """Check if wallet data is stale."""
        max_age = max_age_seconds or STALENESS_THRESHOLDS["wallet"]
        with self._lock:
            wallet = self._wallet.get(coin)
            if not wallet:
                return True
            return (time.time() - wallet.timestamp) > max_age
    
    def on_wallet_update(self, callback: Callable[[WalletData], None]):
        """Register callback for wallet updates."""
        with self._callback_lock:
            self._wallet_callbacks.append(callback)
    
    # ==========================================================================
    # Private Data - Account Metrics (Unified Account-Level)
    # ==========================================================================
    
    def update_account_metrics(self, metrics: AccountMetrics):
        """Update unified account metrics (thread-safe)."""
        with self._lock:
            self._account_metrics = metrics
            self._update_counts["account_metrics"] += 1
        
        self._emit_event(EventType.WALLET_UPDATE, metrics, "account")
        self._invoke_callbacks(self._account_metrics_callbacks, metrics)
    
    def get_account_metrics(self) -> AccountMetrics | None:
        """Get unified account metrics."""
        with self._lock:
            return self._account_metrics
    
    def is_account_metrics_stale(self, max_age_seconds: float | None = None) -> bool:
        """Check if account metrics are stale."""
        max_age = max_age_seconds or STALENESS_THRESHOLDS["wallet"]
        with self._lock:
            if not self._account_metrics:
                return True
            return (time.time() - self._account_metrics.timestamp) > max_age
    
    def on_account_metrics_update(self, callback: Callable[[AccountMetrics], None]):
        """Register callback for account metrics updates."""
        with self._callback_lock:
            self._account_metrics_callbacks.append(callback)
    
    # ==========================================================================
    # Connection Status
    # ==========================================================================
    
    def set_public_ws_connected(self):
        """Mark public WebSocket as connected."""
        self._public_ws_status.state = ConnectionState.CONNECTED
        self._public_ws_status.connected_at = time.time()
        self._emit_event(EventType.CONNECTED, {"stream": "public"})
    
    def set_public_ws_disconnected(self, error: str | None = None):
        """Mark public WebSocket as disconnected."""
        self._public_ws_status.state = ConnectionState.DISCONNECTED
        self._public_ws_status.disconnected_at = time.time()
        if error:
            self._public_ws_status.last_error = error
        self._emit_event(EventType.DISCONNECTED, {"stream": "public", "error": error})
    
    def set_public_ws_reconnecting(self):
        """Mark public WebSocket as reconnecting."""
        self._public_ws_status.state = ConnectionState.RECONNECTING
        self._public_ws_status.reconnect_count += 1
        self._emit_event(EventType.RECONNECTING, {"stream": "public"})
    
    def set_private_ws_connected(self):
        """Mark private WebSocket as connected."""
        self._private_ws_status.state = ConnectionState.CONNECTED
        self._private_ws_status.connected_at = time.time()
        self._emit_event(EventType.CONNECTED, {"stream": "private"})
    
    def set_private_ws_disconnected(self, error: str | None = None):
        """Mark private WebSocket as disconnected."""
        self._private_ws_status.state = ConnectionState.DISCONNECTED
        self._private_ws_status.disconnected_at = time.time()
        if error:
            self._private_ws_status.last_error = error
        self._emit_event(EventType.DISCONNECTED, {"stream": "private", "error": error})
    
    def set_private_ws_reconnecting(self):
        """Mark private WebSocket as reconnecting."""
        self._private_ws_status.state = ConnectionState.RECONNECTING
        self._private_ws_status.reconnect_count += 1
        self._emit_event(EventType.RECONNECTING, {"stream": "private"})
    
    def get_public_ws_status(self) -> ConnectionStatus:
        """Get public WebSocket status."""
        return self._public_ws_status
    
    def get_private_ws_status(self) -> ConnectionStatus:
        """Get private WebSocket status."""
        return self._private_ws_status
    
    @property
    def is_public_ws_connected(self) -> bool:
        return self._public_ws_status.is_connected
    
    @property
    def is_private_ws_connected(self) -> bool:
        return self._private_ws_status.is_connected

    def is_websocket_healthy(self, max_stale_seconds: float = 30.0) -> bool:
        """
        G1-4: Check if WebSocket connections are healthy.

        Healthy means:
        - Private WebSocket is connected (for account data)
        - Account metrics are not stale

        Args:
            max_stale_seconds: Max age before data is considered stale

        Returns:
            True if WebSocket is healthy and receiving data
        """
        # Check private WebSocket connection (needed for trading)
        if not self.is_private_ws_connected:
            return False

        # Check if we're receiving account data
        if self.is_account_metrics_stale(max_stale_seconds):
            return False

        # Check if wallet data is stale
        if self.is_wallet_stale(max_age_seconds=max_stale_seconds):
            return False

        return True

    # ==========================================================================
    # Event Queue
    # ==========================================================================
    
    def _emit_event(self, event_type: EventType, data, symbol: str = ""):
        """Emit event to the queue if enabled."""
        if self._event_queue_enabled and self._event_queue:
            event = RealtimeEvent(
                event_type=event_type,
                data=data,
                symbol=symbol,
            )
            self._event_queue.put_nowait(event)
    
    def get_event(self, timeout: float | None = None) -> RealtimeEvent | None:
        """Get next event from queue (blocking)."""
        if not self._event_queue:
            return None
        try:
            return self._event_queue.get(timeout=timeout)
        except Empty:
            return None

    def get_event_nowait(self) -> RealtimeEvent | None:
        """Get next event from queue (non-blocking)."""
        if not self._event_queue:
            return None
        try:
            return self._event_queue.get_nowait()
        except Empty:
            return None
    
    def event_queue_size(self) -> int:
        """Get current event queue size."""
        return self._event_queue.qsize() if self._event_queue else 0
    
    def clear_event_queue(self):
        """Clear all pending events."""
        if self._event_queue:
            while not self._event_queue.empty():
                try:
                    self._event_queue.get_nowait()
                except Empty:
                    break
    
    # ==========================================================================
    # Callbacks
    # ==========================================================================
    
    def _invoke_callbacks(self, callbacks: list[Callable], data):
        """Invoke all registered callbacks (copy-under-lock for thread safety)."""
        with self._callback_lock:
            callbacks_copy = list(callbacks)
        for callback in callbacks_copy:
            try:
                callback(data)
            except Exception as e:
                self.logger.error(f"Callback error: {e}")
    
    def clear_callbacks(self):
        """Clear all registered callbacks."""
        with self._callback_lock:
            self._ticker_callbacks.clear()
            self._orderbook_callbacks.clear()
            self._trade_callbacks.clear()
            self._kline_callbacks.clear()
            self._position_callbacks.clear()
            self._order_callbacks.clear()
            self._execution_callbacks.clear()
            self._wallet_callbacks.clear()
    
    # ==========================================================================
    # State Management
    # ==========================================================================
    
    def clear_all(self):
        """Clear all state data."""
        with self._lock:
            self._tickers.clear()
            self._orderbooks.clear()
            self._klines.clear()
            self._recent_trades.clear()
            self._positions.clear()
            self._orders.clear()
            self._executions.clear()
            self._wallet.clear()
            self._update_counts.clear()
        
        self.clear_event_queue()
        self.logger.info("RealtimeState cleared")
    
    def clear_market_data(self):
        """Clear only market data (public streams)."""
        with self._lock:
            self._tickers.clear()
            self._orderbooks.clear()
            self._klines.clear()
            self._recent_trades.clear()
    
    def clear_account_data(self):
        """Clear only account data (private streams)."""
        with self._lock:
            self._positions.clear()
            self._orders.clear()
            self._executions.clear()
            self._wallet.clear()
    
    # ==========================================================================
    # Portfolio Risk Snapshot
    # ==========================================================================
    
    def build_portfolio_snapshot(self, config=None) -> PortfolioRiskSnapshot:
        """
        Build a comprehensive portfolio risk snapshot.
        
        This aggregates all position and account data into a single,
        point-in-time view suitable for risk analysis and agent consumption.
        """
        with self._lock:
            return PortfolioRiskSnapshot.from_state(
                account_metrics=self._account_metrics,
                positions=dict(self._positions),
                config=config,
            )
    
    # ==========================================================================
    # Statistics and Status
    # ==========================================================================
    
    def get_stats(self) -> dict:
        """Get state statistics."""
        with self._lock:
            return {
                "uptime_seconds": time.time() - self._started_at,
                "ticker_count": len(self._tickers),
                "orderbook_count": len(self._orderbooks),
                "position_count": len(self._positions),
                "open_order_count": len(self._orders),
                "execution_count": len(self._executions),
                "update_counts": dict(self._update_counts),
                "event_queue_size": self.event_queue_size(),
                "public_ws": self._public_ws_status.to_dict(),
                "private_ws": self._private_ws_status.to_dict(),
            }
    
    def get_summary(self) -> dict:
        """Get a summary of current state."""
        with self._lock:
            total_unrealized_pnl = sum(p.unrealized_pnl for p in self._positions.values())
            usdt_wallet = self._wallet.get("USDT")
            
            return {
                "connected": {
                    "public": self.is_public_ws_connected,
                    "private": self.is_private_ws_connected,
                },
                "market_data": {
                    "symbols_tracked": list(self._tickers.keys()),
                    "ticker_count": len(self._tickers),
                },
                "account": {
                    "positions": len(self._positions),
                    "open_orders": len(self._orders),
                    "unrealized_pnl": total_unrealized_pnl,
                    "balance": usdt_wallet.wallet_balance if usdt_wallet else 0,
                    "available": usdt_wallet.available_balance if usdt_wallet else 0,
                },
                "updates": dict(self._update_counts),
            }


# ==============================================================================
# Singleton Instance
# ==============================================================================

_realtime_state: RealtimeState | None = None
_state_lock = threading.Lock()


def get_realtime_state() -> RealtimeState:
    """Get or create the global RealtimeState instance."""
    global _realtime_state
    with _state_lock:
        if _realtime_state is None:
            _realtime_state = RealtimeState()
        return _realtime_state


def reset_realtime_state():
    """Reset the global RealtimeState instance (for testing)."""
    global _realtime_state
    with _state_lock:
        if _realtime_state:
            _realtime_state.clear_all()
        _realtime_state = None
